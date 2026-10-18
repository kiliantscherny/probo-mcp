"""Settings read from environment variables, with optional 1Password secret references."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

OP_PREFIX = "op://"

# GUI apps (e.g. Claude Desktop launched from the Dock) get a minimal PATH, so also
# look where the 1Password CLI is normally installed.
OP_FALLBACK_LOCATIONS = ("/opt/homebrew/bin/op", "/usr/local/bin/op", "/usr/bin/op")


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
    if parsed.scheme != "https" or not parsed.netloc:
        raise ConfigError(f"PROBO_BASE_URL must be an https URL like https://<association>.probo.dk, got {raw!r}")
    return f"https://{parsed.netloc}"


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from e


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for the server."""

    base_url: str
    username: str
    password: str
    download_dir: Path
    max_document_chars: int = 50_000
    cache_seconds: int = 60
    confirm_download_mb: int = 10

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Build settings from environment variables (``PROBO_*``)."""
        env = os.environ if env is None else env
        missing = [k for k in ("PROBO_BASE_URL", "PROBO_USERNAME", "PROBO_PASSWORD") if not env.get(k, "").strip()]
        if missing:
            raise ConfigError(
                f"Missing required setting(s): {', '.join(missing)}. "
                "See https://kiliantscherny.github.io/probo-mcp/configuration/"
            )
        return cls(
            base_url=_normalise_base_url(env["PROBO_BASE_URL"]),
            username=resolve_secret(env["PROBO_USERNAME"].strip()),
            password=resolve_secret(env["PROBO_PASSWORD"]),
            download_dir=Path(env.get("PROBO_DOWNLOAD_DIR") or "~/Downloads/probo").expanduser(),
            max_document_chars=_int(env, "PROBO_MAX_DOCUMENT_CHARS", 50_000),
            cache_seconds=_int(env, "PROBO_CACHE_SECONDS", 60),
            confirm_download_mb=_int(env, "PROBO_CONFIRM_DOWNLOAD_MB", 10),
        )
