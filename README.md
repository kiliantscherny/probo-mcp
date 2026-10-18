<p align="center">
  <img src="docs/assets/logo.svg" width="96" alt="">
</p>

<h1 align="center">probo-mcp</h1>

<p align="center">
  A read-only <a href="https://modelcontextprotocol.io">MCP</a> server for <a href="https://probo.dk">EG ProBo</a> owners' association portals.<br>
  Ask Claude what's new, summarise meeting papers, search the document archive, or browse it all in the chat.
</p>

<p align="center">
  <a href="https://github.com/kiliantscherny/probo-mcp/actions/workflows/ci.yml"><img src="https://github.com/kiliantscherny/probo-mcp/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://kiliantscherny.github.io/probo-mcp/"><img src="https://img.shields.io/badge/docs-zensical-c4512b" alt="Docs"></a>
  <img src="https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue" alt="Python">
  <img src="https://img.shields.io/badge/MCP-2026--07--28%20%2B%202025--11--25-6e56cf" alt="MCP protocol">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
</p>

<p align="center"><img src="docs/assets/browser.png" alt="The interactive ProBo browser" width="820"></p>

**[📖 Documentation](https://kiliantscherny.github.io/probo-mcp/)** ·
[Claude Desktop](https://kiliantscherny.github.io/probo-mcp/get-started/claude-desktop/) ·
[Claude Code](https://kiliantscherny.github.io/probo-mcp/get-started/claude-code/) ·
[How it works](https://kiliantscherny.github.io/probo-mcp/how-it-works/) ·
[MCP 2.0 showcase](https://kiliantscherny.github.io/probo-mcp/mcp-showcase/)

## Features

- **Messages, news, documents and info pages** as tools with structured output, plus `probo://` resources with argument completion.
- **Search the whole document archive** by upload date or name, with progress updates, and read PDFs as text.
- **An interactive ProBo browser** (an MCP App) right inside Claude Desktop.
- **Prompts** for "what's new", summarising a document, and preparing for the general meeting.
- **Read-only by construction**: an allowlist of routes is checked before every request, and the only thing ever submitted is the login form.
- **1Password-friendly**: any setting can be an `op://` reference.
- **One-click Claude Desktop extension** (`.mcpb`).

## Quick start

**Claude Desktop:** download the `.mcpb` from the [latest release](https://github.com/kiliantscherny/probo-mcp/releases/latest), double-click it, and enter your ProBo address and login.

**Claude Code:**

```sh
claude mcp add probo -s user \
  -e PROBO_BASE_URL=https://<association>.probo.dk \
  -e PROBO_USERNAME=you@example.com \
  -e PROBO_PASSWORD='op://Private/ProBo/password' \
  -- uvx --from git+https://github.com/kiliantscherny/probo-mcp probo-mcp
```

Then ask: *"What's new in ProBo this week?"*

## Development

```sh
uv sync
uv run tox          # tests on 3.12–3.14, ruff, ty, docs
```

See the [development guide](https://kiliantscherny.github.io/probo-mcp/development/).

---

Unofficial; not affiliated with or endorsed by EG A/S. It reads the same pages you see in your browser,
so a ProBo redesign can temporarily break individual tools.
