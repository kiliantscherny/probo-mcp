# MCP 2.0 showcase

probo-mcp is built on the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) 2.x
(`MCPServer`, which replaced `FastMCP`). It's meant to be a small, real, readable example of most
of what a modern MCP server can do. This page maps each feature to the code that implements it.

Every feature here is covered by the end-to-end tests in `tests/test_server.py`, which run against an
in-process `mcp.Client` on **both protocol eras**: the stateless `2026-07-28` revision and the
`2025-11-25` initialize handshake.

## Server metadata

`server.py` gives the server a title, description, website and an SVG icon, plus `instructions`,
which tell the model how to use the tools (for example "use `find_documents`, not `recent_documents`,
for date ranges").

## Structured output

Tools return Pydantic models, and the SDK publishes their JSON Schema as the tool's `outputSchema` and
returns `structuredContent`:

```python title="src/probo_mcp/tools.py"
@user_errors
async def get_message(ctx: Context, message_id: str) -> MessageThread:
    """Get a full message thread: every reply as Markdown, plus attachment paths."""
    return await service_from(ctx).get_message(message_id)
```

When a tool also needs **extra content blocks**, the return type is `Annotated[CallToolResult, Model]`.
That keeps the output schema while adding `resource_link` blocks:

```python title="src/probo_mcp/tools.py"
async def find_documents(...) -> Annotated[CallToolResult, DocumentSearchResult]:
    ...
    return CallToolResult(
        content=[TextContent(type="text", text=summary), *(_document_link(d.id, d.name) for d in result.documents)],
        structured_content=result.model_dump(mode="json"),
    )
```

## Tool annotations and titles

Every tool has a human `title` and `ToolAnnotations`: `read_only_hint`, `destructive_hint=False`,
`idempotent_hint` and `open_world_hint`. `download_document` is the only tool that isn't read-only,
because it writes a local file. Clients use these hints when deciding what to ask permission for.

## Lifespan and shared state

`create_server()` builds an `AppState` that creates the `ProboClient` lazily. The lifespan exposes it
to handlers as `ctx.request_context.lifespan_context` and closes it on shutdown (`state.py`). The
state is created *outside* the lifespan so the completion handler, which gets no request context,
can share it too.

Creating the service lazily means a misconfigured server still starts, and every tool explains what
to set.

## Errors

The `user_errors` decorator turns expected failures (bad ids, missing configuration, login problems,
disallowed paths) into `ToolError`, which the client sees as `isError: true` with a readable message.
Anything else is a bug, and the SDK logs it with a traceback.

## Progress notifications

`find_documents` walks the archive and reports progress after each folder:

```python title="src/probo_mcp/tools.py"
async def progress(done: int, total: int, message: str) -> None:
    await ctx.report_progress(done, total, message)
```

## Elicitation with a resolver

`download_document` asks before saving large files. In 2.x the portable way to elicit is a
**resolver**: a parameter annotated `Annotated[T, Resolve(fn)]` is filled by running `fn` before the
tool body. The resolver can return a plain value, so it only asks when it needs to:

```python title="src/probo_mcp/tools.py"
async def confirm_large_download(document: str, ctx: Context) -> Elicit[DownloadConfirmation] | DownloadConfirmation:
    info = await service_from(ctx).file_info(document)  # HEAD request: name and size
    if not client_can_elicit or info.size_bytes <= limit:
        return DownloadConfirmation(filename=info.filename)  # no question asked
    return Elicit(f"{info.filename} is {size_mb:.0f} MB. Save it?", form)


async def download_document(
    ctx: Context,
    document: str,
    confirmation: Annotated[DownloadConfirmation, Resolve(confirm_large_download)],
) -> SavedFile: ...
```

The SDK chooses the transport: on `2026-07-28` it returns an `InputRequiredResult` and resumes when
the client retries, and on `2025-11-25` it sends `elicitation/create` mid-call. Declining aborts the
call. The `confirmation` parameter never appears in the tool's input schema.

## Resource templates

`resources.py` registers four `probo://` templates that return Markdown. Unknown ids raise
`ResourceNotFoundError` (JSON-RPC `-32602`).

## Completions

A single `@mcp.completion()` handler completes every id argument (matching names as well as id
prefixes) and the `language` prompt argument.

## Prompts

`prompts.py` defines three prompts with titles and typed, described arguments.

## MCP Apps (interactive UI)

`ui/__init__.py` uses the SDK's `Apps` extension:

```python title="src/probo_mcp/ui/__init__.py"
apps = Apps()

@apps.tool(resource_uri="ui://probo/browser.html", title="Open ProBo browser", annotations=READ_ONLY)
async def open_probo_browser(ctx: Context, view: ... = "overview") -> Overview: ...

apps.add_html_resource("ui://probo/browser.html", browser_html(), title="ProBo browser", prefers_border=True)

mcp = MCPServer("probo", extensions=[apps], ...)
```

See [Interactive browser](features/interactive-browser.md) for the HTML side.

## Cache hints and subscriptions

`cache_hints` (SEP-2549) let clients cache the catalogue for an hour and resource reads briefly.
`subscriptions=False`, because a read-only server that fetches on demand has nothing to push.

## Transports

`probo-mcp` runs over stdio by default and over streamable HTTP with `--transport streamable-http`.
Logs always go to stderr, because stdout carries the protocol.
