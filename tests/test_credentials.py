import subprocess
import sys
import types

import pytest

from probo_mcp import credentials

BASE = "https://example.probo.dk"
USER = "me@example.com"
ACCOUNT = "me@example.com@example.probo.dk"


class FakeRun:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.calls: list[list[str]] = []
        self.result = subprocess.CompletedProcess([], returncode, stdout, stderr)

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        return self.result


@pytest.fixture
def mac(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")


def test_account_is_per_login_and_site() -> None:
    assert credentials.account(BASE, USER) == ACCOUNT


def test_macos_read(mac, monkeypatch: pytest.MonkeyPatch) -> None:
    run = FakeRun(stdout="s3cret\n")
    monkeypatch.setattr(subprocess, "run", run)
    assert credentials.get_password(BASE, USER) == "s3cret"
    assert run.calls == [["/usr/bin/security", "find-generic-password", "-s", "probo-mcp", "-a", ACCOUNT, "-w"]]


def test_macos_missing_and_refused(mac, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", FakeRun(returncode=44))
    assert credentials.get_password(BASE, USER) is None
    monkeypatch.setattr(subprocess, "run", FakeRun(returncode=128, stderr="User canceled the operation."))
    with pytest.raises(credentials.CredentialError, match="User canceled"):
        credentials.get_password(BASE, USER)


def test_macos_save_trusts_no_app_and_prompts_itself(mac, monkeypatch: pytest.MonkeyPatch) -> None:
    run = FakeRun()
    monkeypatch.setattr(subprocess, "run", run)
    credentials.set_password(BASE, USER)
    delete, add = run.calls
    assert delete[:2] == ["/usr/bin/security", "delete-generic-password"]
    # -T "" removes the default trust, so every read asks; -w last makes `security` prompt for the password.
    assert add[add.index("-T") + 1] == ""
    assert add[-1] == "-w"
    assert "-A" not in add


class FakeKeyring(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("keyring")
        self.store: dict[tuple[str, str], str] = {}
        errors = types.ModuleType("keyring.errors")
        errors.KeyringError = type("KeyringError", (Exception,), {})  # ty: ignore[unresolved-attribute]
        errors.PasswordDeleteError = type("PasswordDeleteError", (errors.KeyringError,), {})  # ty: ignore[unresolved-attribute]
        self.errors = errors

    def get_password(self, service: str, name: str) -> str | None:
        return self.store.get((service, name))

    def set_password(self, service: str, name: str, password: str) -> None:
        self.store[(service, name)] = password

    def delete_password(self, service: str, name: str) -> None:
        if self.store.pop((service, name), None) is None:
            raise self.errors.PasswordDeleteError()


def test_other_platforms_use_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeKeyring()
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setitem(sys.modules, "keyring", fake)
    monkeypatch.setitem(sys.modules, "keyring.errors", fake.errors)
    answers = iter(["s3cret", "s3cret"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))

    assert credentials.get_password(BASE, USER) is None
    credentials.set_password(BASE, USER)
    assert fake.store == {("probo-mcp", ACCOUNT): "s3cret"}
    assert credentials.get_password(BASE, USER) == "s3cret"
    assert credentials.delete_password(BASE, USER) is True
    assert credentials.delete_password(BASE, USER) is False

    mismatched = iter(["one", "two"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(mismatched))
    with pytest.raises(credentials.CredentialError, match="didn't match"):
        credentials.set_password(BASE, USER)
