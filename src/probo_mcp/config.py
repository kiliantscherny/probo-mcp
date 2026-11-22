"""Settings read from environment variables; the password from the system keychain or 1Password.

Where the password comes from, in order:

1. ``PROBO_PASSWORD``, if set: a 1Password ``op://`` reference (resolved with the ``op`` CLI) or,
   discouraged, the password itself in plain text.
2. The system keychain, where ``probo-mcp --set-password`` saved it (see `credentials`).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

OP_PREFIX = "op://"

# GUI apps (e.g. Claude Desktop launched from the Dock) get a minimal PATH, so also
# look where the 1Password CLI is normally installed.
OP_FALLBACK_LOCATIONS = ("/opt/homebrew/bin/op", "/usr/local/bin/op", "/usr/bin/op")


logger = logging.getLogger(__name__)

#: ProBo sites live under this domain. The login is only ever sent to a host under it, so changing the
#: configuration (by mistake, or by a manipulated AI agent) can't send your password anywhere else.
PROBO_DOMAIN = ".probo.dk"


class ConfigError(RuntimeError):
    """Raised when the server is missing or has invalid configuration."""


def resolve_secret(value: str, *, op_binary: str = "op") -> str:
    """Return ``value``, or the secret it references if it is a 1Password ``op://`` reference.

    This lets any config source (environment, ``.env``, a Claude Desktop extension's
    settings form) hold a reference instead of the secret itself. Resolution uses the
    1Password CLI, so the desktop app's biometric unlock applies.
    """
    if not value.startswith(OP_PREFIX):
        return value
    binary = shutil.which(op_binary) or next(
        (path for path in OP_FALLBACK_LOCATIONS if op_binary == "op" and shutil.which(path)), None
    )
    if binary is None:
        raise ConfigError(f"{value!r} is a 1Password reference, but the 1Password CLI ('op') is not installed")
    try:
        result = subprocess.run(  # fixed argv, no shell
            [binary, "read", "--no-newline", value],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise ConfigError(
            f"Timed out resolving {value!r} with the 1Password CLI (was the unlock prompt approved?)"
        ) from e
    if result.returncode != 0:
        raise ConfigError(f"1Password CLI could not read {value!r}: {result.stderr.strip()}")
    return result.stdout


def _normalise_base_url(raw: str) -> str:
    raw = raw.strip()
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not host.endswith(PROBO_DOMAIN)
        or not host[: -len(PROBO_DOMAIN)]
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ConfigError(f"PROBO_BASE_URL must be https://<association>.probo.dk, got {raw!r}")
    return f"https://{host}"


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from e


def _password(env: Mapping[str, str], base_url: str, username: str) -> str:
    raw = env.get("PROBO_PASSWORD", "")
    if raw.strip():
        if not raw.startswith(OP_PREFIX):
            logger.warning(
                "PROBO_PASSWORD holds the password in plain text, where other programs (and AI agents) can read it. "
                "Save it in the system keychain with `probo-mcp --set-password` and unset PROBO_PASSWORD."
            )
        return resolve_secret(raw)
    from . import credentials

    try:
        password = credentials.get_password(base_url, username)
    except credentials.CredentialError as e:
        raise ConfigError(str(e)) from e
    if not password:
        raise ConfigError(
            f"No ProBo password saved for {username}. Run `probo-mcp --set-password` in a terminal "
            "(not through an AI agent), or set PROBO_PASSWORD to a 1Password op:// reference. "
            "See https://kiliantscherny.github.io/probo-mcp/configuration/"
        )
    return password


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for the server."""

    base_url: str
    username: str = field(repr=False)  # an e-mail address: kept out of logs too
    password: str = field(repr=False)  # never in reprs, logs or tracebacks
    download_dir: Path = field(default_factory=lambda: Path("~/Downloads/probo").expanduser())
    archive_dir: Path = field(default_factory=lambda: Path("~/Documents/probo").expanduser())
    max_document_chars: int = 50_000
    cache_seconds: int = 60
    confirm_download_mb: int = 10
    max_download_mb: int = 200

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Build settings from environment variables (``PROBO_*``)."""
        env = os.environ if env is None else env
        missing = [k for k in ("PROBO_BASE_URL", "PROBO_USERNAME") if not env.get(k, "").strip()]
        if missing:
            raise ConfigError(
                f"Missing required setting(s): {', '.join(missing)}. "
                "See https://kiliantscherny.github.io/probo-mcp/configuration/"
            )
        base_url = _normalise_base_url(env["PROBO_BASE_URL"])
        username = resolve_secret(env["PROBO_USERNAME"].strip())
        return cls(
            base_url=base_url,
            username=username,
            password=_password(env, base_url, username),
            download_dir=Path(env.get("PROBO_DOWNLOAD_DIR") or "~/Downloads/probo").expanduser(),
            archive_dir=Path(env.get("PROBO_ARCHIVE_DIR") or "~/Documents/probo").expanduser(),
            max_document_chars=_int(env, "PROBO_MAX_DOCUMENT_CHARS", 50_000),
            cache_seconds=_int(env, "PROBO_CACHE_SECONDS", 60),
            confirm_download_mb=_int(env, "PROBO_CONFIRM_DOWNLOAD_MB", 10),
            max_download_mb=_int(env, "PROBO_MAX_DOWNLOAD_MB", 200),
        )
