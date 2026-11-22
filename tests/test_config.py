import stat
import sys
from pathlib import Path

import pytest

from probo_mcp.config import ConfigError, Settings, resolve_secret

ENV = {"PROBO_BASE_URL": "example.probo.dk/member/", "PROBO_USERNAME": " me@example.com ", "PROBO_PASSWORD": "pw"}


def test_from_env_normalises_and_defaults() -> None:
    s = Settings.from_env(ENV)
    assert s.base_url == "https://example.probo.dk"
    assert s.username == "me@example.com"
    assert s.password == "pw"
    assert s.download_dir == Path("~/Downloads/probo").expanduser()
    assert s.archive_dir == Path("~/Documents/probo").expanduser()
    assert (s.max_document_chars, s.cache_seconds, s.confirm_download_mb) == (50_000, 60, 10)


def test_from_env_optional_overrides(tmp_path: Path) -> None:
    s = Settings.from_env(
        {
            **ENV,
            "PROBO_DOWNLOAD_DIR": str(tmp_path),
            "PROBO_ARCHIVE_DIR": str(tmp_path / "archive"),
            "PROBO_MAX_DOCUMENT_CHARS": "100",
            "PROBO_CACHE_SECONDS": "0",
            "PROBO_CONFIRM_DOWNLOAD_MB": "5",
        }
    )
    assert (s.download_dir, s.max_document_chars, s.cache_seconds, s.confirm_download_mb) == (tmp_path, 100, 0, 5)
    assert s.archive_dir == tmp_path / "archive"


def test_missing_settings_are_listed() -> None:
    with pytest.raises(ConfigError, match=r"setting\(s\): PROBO_BASE_URL, PROBO_USERNAME\."):
        Settings.from_env({"PROBO_USERNAME": "  "})


@pytest.mark.parametrize(
    "url",
    [
        "http://example.probo.dk",
        "https://",
        "ftp://example.probo.dk",
        # The login may only ever go to a ProBo site.
        "https://evil.example",
        "https://probo.dk",
        "https://evilprobo.dk",
        "https://example.probo.dk.evil.example",
        "https://example.probo.dk:8443",
        "https://someone:pw@example.probo.dk",
    ],
)
def test_rejects_anything_but_a_probo_site(url: str) -> None:
    with pytest.raises(ConfigError, match=r"must be https://<association>\.probo\.dk"):
        Settings.from_env({**ENV, "PROBO_BASE_URL": url})


def test_password_never_appears_in_repr() -> None:
    s = Settings.from_env({**ENV, "PROBO_PASSWORD": "hunter2-secret"})
    assert "hunter2-secret" not in repr(s)
    assert "hunter2-secret" not in str(s)


def test_plain_text_password_is_warned_about(caplog: pytest.LogCaptureFixture) -> None:
    Settings.from_env(ENV)
    assert "plain text" in caplog.text
    assert "pw" not in caplog.text.replace("PROBO_PASSWORD", "").replace("probo-mcp --set-password", "")


def test_password_from_the_keychain_when_not_in_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    from probo_mcp import credentials

    asked = []

    def fake_get(base_url: str, username: str) -> str | None:
        asked.append((base_url, username))
        return "from-keychain"

    monkeypatch.setattr(credentials, "get_password", fake_get)
    env = {k: v for k, v in ENV.items() if k != "PROBO_PASSWORD"}
    assert Settings.from_env(env).password == "from-keychain"
    assert asked == [("https://example.probo.dk", "me@example.com")]

    monkeypatch.setattr(credentials, "get_password", lambda *a: None)
    with pytest.raises(ConfigError, match="probo-mcp --set-password"):
        Settings.from_env(env)

    def refused(*a):
        raise credentials.CredentialError("The keychain refused access (user canceled)")

    monkeypatch.setattr(credentials, "get_password", refused)
    with pytest.raises(ConfigError, match="refused access"):
        Settings.from_env(env)


def test_rejects_non_integer_limits() -> None:
    with pytest.raises(ConfigError, match="PROBO_CACHE_SECONDS must be an integer"):
        Settings.from_env({**ENV, "PROBO_CACHE_SECONDS": "soon"})


# -- 1Password references --------------------------------------------------------


posix_only = pytest.mark.skipif(sys.platform == "win32", reason="fake `op` is a POSIX shell script")


def fake_op(tmp_path: Path, script: str) -> str:
    path = tmp_path / "op"
    path.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


def test_plain_values_pass_through() -> None:
    assert resolve_secret("hunter2", op_binary="/nonexistent/op") == "hunter2"


@posix_only
def test_op_reference_is_resolved_with_the_cli(tmp_path: Path) -> None:
    op = fake_op(tmp_path, 'test "$1 $2 $3" = "read --no-newline op://Private/Probo/password" && printf s3cret')
    assert resolve_secret("op://Private/Probo/password", op_binary=op) == "s3cret"


@posix_only
def test_op_failure_is_reported(tmp_path: Path) -> None:
    op = fake_op(tmp_path, 'echo "[ERROR] item not found" >&2; exit 1')
    with pytest.raises(ConfigError, match="item not found"):
        resolve_secret("op://Private/Missing/password", op_binary=op)


def test_op_missing_is_explained() -> None:
    with pytest.raises(ConfigError, match=r"CLI \('op'\) is not installed"):
        resolve_secret("op://Private/Probo/password", op_binary="/nonexistent/op")


@posix_only
def test_from_env_resolves_references(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_op(tmp_path, 'case "$3" in *username) printf me@example.com;; *) printf pw;; esac')
    monkeypatch.setenv("PATH", str(tmp_path), prepend=":")
    s = Settings.from_env({**ENV, "PROBO_USERNAME": "op://v/i/username", "PROBO_PASSWORD": "op://v/i/password"})
    assert (s.username, s.password) == ("me@example.com", "pw")
