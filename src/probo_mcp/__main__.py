"""Command-line entry point: ``probo-mcp`` / ``python -m probo_mcp``."""

import argparse
import logging
import os
import sys

from . import __version__


def main(argv: list[str] | None = None) -> None:
    """Run the server over stdio (default) or streamable HTTP."""
    parser = argparse.ArgumentParser(prog="probo-mcp", description="Read-only MCP server for EG ProBo.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host (streamable-http only)")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (streamable-http only)")
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Allow --host to be reachable from other computers. The HTTP transport has no authentication: "
        "anyone who can reach it can read your ProBo.",
    )
    parser.add_argument(
        "--fetch-history",
        nargs="*",
        choices=["news", "document", "message"],
        metavar="SECTION",
        help="Save older items to the local archive and exit, instead of serving. "
        "Sections: news, document, message (default: news document).",
    )
    keychain = parser.add_mutually_exclusive_group()
    keychain.add_argument(
        "--set-password",
        action="store_true",
        help="Save your ProBo password in the system keychain (asks for it on this terminal) and exit.",
    )
    keychain.add_argument(
        "--forget-password", action="store_true", help="Remove the saved ProBo password from the keychain and exit."
    )
    args = parser.parse_args(argv)

    if args.set_password or args.forget_password:
        sys.exit(_keychain_command(forget=args.forget_password))

    # stdout carries the MCP protocol over stdio, so logs must go to stderr.
    logging.basicConfig(
        level=os.environ.get("PROBO_LOG_LEVEL", "WARNING").upper(),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.fetch_history is not None:
        import anyio

        anyio.run(_fetch_all_history, tuple(args.fetch_history or ("news", "document")))
        return

    if args.transport == "streamable-http" and not args.allow_remote and not _is_loopback(args.host):
        parser.error(
            f"--host {args.host} would let other computers read your ProBo (there is no authentication). "
            "Use 127.0.0.1, or add --allow-remote if you really mean it."
        )

    from .server import mcp

    if args.transport == "stdio":
        mcp.run("stdio")
    else:
        mcp.run("streamable-http", host=args.host, port=args.port)


def _is_loopback(host: str) -> bool:
    import ipaddress

    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _keychain_command(*, forget: bool) -> int:
    """``--set-password`` / ``--forget-password``: for a person at a terminal, never an agent."""
    from . import credentials
    from .config import ConfigError, _normalise_base_url

    if not (sys.stdin.isatty() and sys.stderr.isatty()):
        print("Run this in your own terminal: it asks for your password interactively.", file=sys.stderr)
        return 2
    try:
        base_url = _normalise_base_url(
            os.environ.get("PROBO_BASE_URL") or input("ProBo site (https://<association>.probo.dk): ")
        )
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 2
    username = (os.environ.get("PROBO_USERNAME") or input("ProBo username (e-mail): ")).strip()
    if not username or username.startswith("op://"):
        print("Give the username itself (not an op:// reference).", file=sys.stderr)
        return 2
    name = credentials.account(base_url, username)
    try:
        if forget:
            removed = credentials.delete_password(base_url, username)
            print(f"Removed the saved password for {name}." if removed else f"No saved password for {name}.")
            return 0
        print(f"Saving the ProBo password for {name} in the system keychain.", file=sys.stderr)
        credentials.set_password(base_url, username)
    except credentials.CredentialError as e:
        print(e, file=sys.stderr)
        return 1
    print("Saved. Unset PROBO_PASSWORD in your MCP client's settings so the keychain is used.")
    if sys.platform == "darwin":
        print(
            "When the server first logs in, macOS asks whether `security` may use this item: choose Allow, "
            "never Always Allow. Deny any such prompt you didn't expect."
        )
    return 0


async def _fetch_all_history(sections: tuple) -> None:
    """Run fetch_history until nothing is left, printing what was saved."""
    from . import archive
    from .config import Settings
    from .service import ProboService

    service = ProboService.from_settings(Settings.from_env())
    try:
        while True:
            result = await archive.fetch_history(service, sections=sections, max_items=25)
            for entry in result.saved:
                print(f"saved  {entry.kind:8} {entry.date_text:22} {entry.title}")
            for error in result.errors:
                print(f"error  {error}", file=sys.stderr)
            if not result.remaining or not result.saved:  # done, or only failures left
                break
            print(f"... {result.remaining} to go", file=sys.stderr)
        print(f"Done: {result.remaining} left, archive at {result.archive_dir}", file=sys.stderr)
    finally:
        await service.aclose()


if __name__ == "__main__":
    main()
