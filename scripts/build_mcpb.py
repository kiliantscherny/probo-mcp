"""Build the Claude Desktop extension bundle (``dist/probo-mcp-<version>.mcpb``).

The manifest is generated from the running server, so the tool and prompt
lists shown in Claude Desktop always match the code.

    uv run scripts/build_mcpb.py            # stage + pack (needs Node for `npx @anthropic-ai/mcpb`)
    uv run scripts/build_mcpb.py --no-pack  # only stage dist/mcpb/ and write manifest.json
"""

import argparse
import asyncio
import json
import shutil
import subprocess
from pathlib import Path

from mcp import Client

from probo_mcp import __version__
from probo_mcp.server import mcp

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT / "dist" / "mcpb"
MCPB_CLI = "@anthropic-ai/mcpb@2.1.2"
DOCS = "https://kiliantscherny.github.io/probo-mcp/"
REPO = "https://github.com/kiliantscherny/probo-mcp"


async def catalogue() -> tuple[list[dict], list[dict]]:
    async with Client(mcp) as client:
        tools = (await client.list_tools()).tools
        prompts = (await client.list_prompts()).prompts
    return (
        [{"name": t.name, "description": (t.description or "").strip().splitlines()[0]} for t in tools],
        [{"name": p.name, "description": p.description or ""} for p in prompts],
    )


def manifest(tools: list[dict], prompts: list[dict]) -> dict:
    env = {
        "PROBO_BASE_URL": "${user_config.base_url}",
        "PROBO_USERNAME": "${user_config.username}",
        "PROBO_PASSWORD": "${user_config.password}",
        "PROBO_DOWNLOAD_DIR": "${user_config.download_dir}",
    }
    return {
        "manifest_version": "0.4",
        "name": "probo-mcp",
        "display_name": "ProBo",
        "version": __version__,
        "description": "Read messages, news, documents and info pages from your EG ProBo owners' association portal.",
        "long_description": (
            "Unofficial, read-only connector for EG ProBo (probo.dk), the portal used by Danish owners' "
            "associations and housing co-ops. Ask Claude what's new, summarise documents and meeting "
            "papers, search the document archive, or open an interactive ProBo browser in the chat. "
            "Nothing can be sent, changed or deleted in ProBo. The password can be a 1Password "
            "reference (op://vault/item/password) if the 1Password CLI is installed."
        ),
        "author": {"name": "Kilian Tscherny", "url": REPO},
        "repository": {"type": "git", "url": REPO},
        "homepage": DOCS,
        "documentation": DOCS,
        "support": f"{REPO}/issues",
        "icon": "icon.png",
        "server": {
            "type": "uv",
            "entry_point": "src/server.py",
            "mcp_config": {
                "command": "uv",
                "args": ["run", "--frozen", "--no-dev", "--directory", "${__dirname}", "src/server.py"],
                "env": env,
            },
        },
        "tools": tools,
        "prompts_generated": True,
        "keywords": ["probo", "ejerforening", "andelsforening", "housing", "documents", "denmark"],
        "license": "MIT",
        "privacy_policies": ["https://www.eg.dk/privatlivspolitik"],
        "compatibility": {
            "platforms": ["darwin", "linux", "win32"],
            "runtimes": {"python": ">=3.12"},
        },
        "user_config": {
            "base_url": {
                "type": "string",
                "title": "ProBo site",
                "description": "Your association's ProBo address, e.g. https://<association>.probo.dk",
                "required": True,
            },
            "username": {
                "type": "string",
                "title": "Username (e-mail)",
                "description": "The e-mail you log in to ProBo with, or a 1Password op:// reference.",
                "required": True,
            },
            "password": {
                "type": "string",
                "title": "Password",
                "description": "Stored in your system keychain. You can also enter a 1Password op:// reference.",
                "sensitive": True,
                "required": True,
            },
            "download_dir": {
                "type": "directory",
                "title": "Download folder",
                "description": "Where download_document saves files.",
                "default": "${HOME}/Downloads/probo",
                "required": False,
            },
        },
    }


def stage(manifest_data: dict) -> None:
    if STAGE.exists():
        shutil.rmtree(STAGE)
    (STAGE / "src").mkdir(parents=True)
    for name in ("pyproject.toml", "uv.lock", "README.md", "LICENSE"):
        shutil.copy2(ROOT / name, STAGE / name)
    shutil.copytree(
        ROOT / "src" / "probo_mcp", STAGE / "src" / "probo_mcp", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copy2(ROOT / "packaging" / "mcpb" / "server.py", STAGE / "src" / "server.py")
    shutil.copy2(ROOT / "packaging" / "mcpb" / ".mcpbignore", STAGE / ".mcpbignore")
    shutil.copy2(ROOT / "src" / "probo_mcp" / "assets" / "icon.png", STAGE / "icon.png")
    (STAGE / "manifest.json").write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False) + "\n")


def pack() -> Path:
    out = ROOT / "dist" / f"probo-mcp-{__version__}.mcpb"
    npx = shutil.which("npx")
    if npx is None:
        raise SystemExit("npx not found: install Node.js to pack the bundle")
    subprocess.run([npx, "--yes", MCPB_CLI, "validate", str(STAGE / "manifest.json")], check=True)
    subprocess.run([npx, "--yes", MCPB_CLI, "pack", str(STAGE), str(out)], check=True)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-pack", action="store_true", help="only stage files and write manifest.json")
    args = parser.parse_args()
    tools, prompts = asyncio.run(catalogue())
    stage(manifest(tools, prompts))
    print(f"Staged {STAGE.relative_to(ROOT)} ({len(tools)} tools, {len(prompts)} prompts)")
    if not args.no_pack:
        print(f"Built {pack().relative_to(ROOT)}")


if __name__ == "__main__":
    main()
