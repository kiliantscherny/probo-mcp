# Development

## Setup

```sh
git clone https://github.com/kiliantscherny/probo-mcp && cd probo-mcp
uv sync                      # installs the package plus the dev group (pytest, ruff, ty, tox, zensical)
uvx pre-commit install       # optional: ruff on every commit
```

## Everyday commands

| Task | Command |
|---|---|
| Tests (with coverage) | `uv run pytest --cov` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
| Type check | `uv run ty check` |
| Docs preview | `uv run zensical serve` |
| Everything, like CI | `uv run tox` |
| One tox env | `uv run tox -e 3.13` · `lint` · `type` · `docs` · `fix` |

tox uses [tox-uv](https://github.com/tox-dev/tox-uv) with the lock file (`uv-venv-lock-runner`). The
environments install the matching dependency groups: `test`, `lint`, `type` or `docs`. It runs the tests
on Python 3.12, 3.13 and 3.14, and coverage must stay at 90% or above.

## Tests

| File | What it covers |
|---|---|
| `test_parsers.py` | HTML → models, against the fixtures in `tests/fixtures/` |
| `test_dates.py` | ProBo's mixed date formats (`14 Oct 2026 - 18:22`, `15 Okt 2026`, `13. oktober 2026 12:01`, …) |
| `test_client.py` | Login, CSRF, session renewal, concurrent logins, caching, the allowlist |
| `test_config.py` | Settings and `op://` resolution (with a fake `op` binary) |
| `test_service.py` | Archive walking, date filtering, text extraction, safe file names |
| `test_server.py` | End-to-end through a real `mcp.Client`, on both protocol eras |
| `test_main.py` | The command line |

The fixtures are **synthetic**. They copy ProBo's markup (tags and class names) but contain made-up
content. `conftest.py` serves them from a fake site with [respx](https://lundberg.github.io/respx/),
including the login flow and a generated PDF, so no test touches the network.

### Testing against a real site

```sh
cp .env.example .env    # your site and op:// references
op run --env-file .env -- npx @modelcontextprotocol/inspector uv run probo-mcp
```

### Testing the UI

Run the server over HTTP and open it in the MCP Apps reference host
([`basic-host`](https://github.com/modelcontextprotocol/ext-apps/tree/main/examples/basic-host)):

```sh
op run --env-file .env -- uv run probo-mcp --transport streamable-http --port 3001
# in a checkout of modelcontextprotocol/ext-apps:
cd examples/basic-host && npm install && npm run build && npx tsx serve.ts
# open http://localhost:8080 and call open_probo_browser
```

The host runs in the browser, so the MCP endpoint must allow its origin (CORS). Wrap
`mcp.streamable_http_app()` in Starlette's `CORSMiddleware` for local testing.

## When ProBo changes its HTML

1. Find the page in your browser and inspect the elements a parser uses.
2. Update the fixture in `tests/fixtures/` to match the new markup. Keep the content synthetic: never
   commit real names, addresses or messages.
3. Fix the selector in `parsers.py` until `uv run pytest` passes.

## Claude Desktop bundle

```sh
uv run scripts/build_mcpb.py     # → dist/probo-mcp-<version>.mcpb (needs Node for npx)
```

The script generates `manifest.json` from the live server, so the tool list can't drift. It then
stages the package with a `uv` runtime shim, and validates and packs with
[`@anthropic-ai/mcpb`](https://github.com/modelcontextprotocol/mcpb).

## Releasing

1. Bump `version` in `pyproject.toml` (`uv version --bump minor`) and update the [changelog](changelog.md).
2. Commit, then tag and push: `git tag v0.2.0 && git push --tags`.
3. The **Release** workflow checks that the tag matches the version, runs the checks, builds the wheel,
   sdist and `.mcpb`, and publishes a GitHub release with them attached.

## Project layout

```text
src/probo_mcp/
├── __main__.py      CLI (stdio / streamable HTTP)
├── server.py        MCPServer assembly: metadata, lifespan, cache hints, extensions
├── tools.py         tools (+ elicitation resolver)
├── resources.py     probo:// templates + completions
├── prompts.py       prompts
├── ui/              MCP App: browser.html + vendored ext-apps SDK
├── state.py         lifespan state + error translation
├── service.py       ProBo operations (no MCP)
├── parsers.py       HTML → models (no I/O)
├── markdown.py      models → Markdown
├── client.py        HTTP: login, allowlist, cache
├── config.py        settings + op:// resolution
└── models.py        Pydantic output models
```
