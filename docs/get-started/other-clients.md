# Other clients

probo-mcp is a standard MCP server. It speaks **stdio** by default and **streamable HTTP** on request,
and supports both protocol eras: the stateless `2026-07-28` revision and the `2025-11-25` handshake.

## Generic stdio configuration

Most clients accept this shape:

```json
{
  "mcpServers": {
    "probo": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/kiliantscherny/probo-mcp", "probo-mcp"],
      "env": {
        "PROBO_BASE_URL": "https://<association>.probo.dk",
        "PROBO_USERNAME": "you@example.com",
        "PROBO_PASSWORD": "op://Private/ProBo/password"
      }
    }
  }
}
```

## Claude Desktop config file

This is an alternative to the [extension](claude-desktop.md). Edit
`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, or
`%APPDATA%\Claude\claude_desktop_config.json` on Windows. Use the JSON above, or this version, which
runs a local checkout through `op run`:

```json
{
  "mcpServers": {
    "probo": {
      "command": "op",
      "args": ["run", "--env-file", "/path/to/probo-mcp/.env", "--",
               "uv", "--directory", "/path/to/probo-mcp", "run", "probo-mcp"]
    }
  }
}
```

!!! warning "Use absolute paths"
    Desktop apps don't inherit your shell's `PATH`. If `uvx` or `op` aren't found, use their full
    paths (`which uvx`, `which op`).

## Streamable HTTP

```sh
probo-mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

The endpoint is then `http://127.0.0.1:8000/mcp`.

!!! danger "Keep it local"
    Over HTTP the server holds a logged-in ProBo session and has **no authentication of its own**.
    Bind it to `127.0.0.1` only. Never expose it to a network.

## MCP Inspector

Use the [MCP Inspector](https://github.com/modelcontextprotocol/inspector) to explore the tools,
resources, prompts and completions interactively:

```sh
op run --env-file .env -- npx @modelcontextprotocol/inspector uv run probo-mcp
```
