"""The ProBo password in the operating system's keychain, out of files and environment variables.

Save it once with ``probo-mcp --set-password`` in a terminal. The server reads it when it first
logs in and keeps it only in memory.

On macOS the item is created with no trusted applications (``security ... -T ""``), so every read
shows a system dialog that you have to approve. An AI agent running commands as your user can't
read it silently, as long as you never choose "Always Allow". You also type the password into
``security`` itself, so it never passes through this program or its command line.

On Windows and Linux it goes in the Credential Manager / Secret Service via ``keyring``. Those don't
ask per read: any program running as your user can read an unlocked keychain.
"""

from __future__ import annotations

import subprocess
import sys
from urllib.parse import urlparse

SERVICE = "probo-mcp"
SECURITY = "/usr/bin/security"
_NOT_FOUND = 44  # `security` exit status for "The specified item could not be found in the keychain."


class CredentialError(RuntimeError):
    """The keychain could not be read or written."""


def account(base_url: str, username: str) -> str:
    """Keychain account name: one entry per login per site (``you@example.com@x.probo.dk``)."""
    return f"{username}@{urlparse(base_url).netloc}"


def get_password(base_url: str, username: str) -> str | None:
    """The saved password, or None if there is none. On macOS this shows an approval dialog."""
    name = account(base_url, username)
    if sys.platform == "darwin":
        try:
            result = subprocess.run(  # fixed argv, no shell
                [SECURITY, "find-generic-password", "-s", SERVICE, "-a", name, "-w"],
                capture_output=True,
                text=True,
                timeout=300,  # time for you to answer the dialog
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise CredentialError("Timed out waiting for the keychain prompt to be answered") from e
        if result.returncode == _NOT_FOUND:
            return None
        if result.returncode != 0:
            raise CredentialError(f"The keychain refused access ({result.stderr.strip() or result.returncode})")
        return result.stdout.rstrip("\n")
    keyring = _keyring()
    try:
        return keyring.get_password(SERVICE, name)
    except keyring.errors.KeyringError as e:
        raise CredentialError(f"Could not read the system keychain: {e}") from e


def set_password(base_url: str, username: str) -> None:
    """Ask for the password on the terminal and save it. Run by a person, never by the server."""
    name = account(base_url, username)
    if sys.platform == "darwin":
        # Replace any existing item, so its access list is the strict one below.
        subprocess.run(
            [SECURITY, "delete-generic-password", "-s", SERVICE, "-a", name], capture_output=True, check=False
        )
        result = subprocess.run(  # `security` prompts on the terminal: -w must be the last option
            [SECURITY, "add-generic-password", "-s", SERVICE, "-a", name, "-l", f"ProBo ({name})", "-T", "", "-w"],
            check=False,
        )
        if result.returncode != 0:
            raise CredentialError("The password was not saved")
        return
    import getpass

    password = getpass.getpass(f"ProBo password for {name}: ")
    if not password or password != getpass.getpass("Again: "):
        raise CredentialError("The passwords were empty or didn't match; nothing was saved")
    keyring = _keyring()
    try:
        keyring.set_password(SERVICE, name, password)
    except keyring.errors.KeyringError as e:
        raise CredentialError(f"Could not write to the system keychain: {e}") from e


def delete_password(base_url: str, username: str) -> bool:
    """Remove the saved password. Returns False if there was none."""
    name = account(base_url, username)
    if sys.platform == "darwin":
        result = subprocess.run(
            [SECURITY, "delete-generic-password", "-s", SERVICE, "-a", name], capture_output=True, check=False
        )
        return result.returncode == 0
    keyring = _keyring()
    try:
        keyring.delete_password(SERVICE, name)
    except keyring.errors.PasswordDeleteError:
        return False
    return True


def _keyring():
    try:
        import keyring  # ty: ignore[unresolved-import] - not installed on macOS, which doesn't need it
        import keyring.errors  # ty: ignore[unresolved-import]
    except ImportError as e:  # pragma: no cover - a dependency on Windows and Linux
        raise CredentialError("The 'keyring' package is needed to use the system keychain here") from e
    return keyring
