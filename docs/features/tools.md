# Tools

Every tool returns **structured output**, a JSON object described by a published output schema, and
every tool except `download_document` is annotated `readOnlyHint: true`. Items include a `url`
that opens the same page in your browser, where you're already logged in.

| Tool | What it does |
|---|---|
| `get_overview` | Latest inbox messages, news posts and recently added documents. |
| `list_messages` | Message threads in `inbox`, `sent`, `archive`, `archived_notifications` or `drafts`, with search and paging. |
| `get_message` | A full thread: each reply as Markdown, with recipients and attachment paths. |
| `list_news` / `get_news` | News posts, with comments. |
| `list_documents` | One folder of the document archive (`date`, `alphabetical` or `created` order). |
| `recent_documents` | ProBo's "recently added" widget. This usually shows only a handful of files. |
| `find_documents` | Walks **every** folder, filtering by upload date (`added_within_days`) and/or file name, and reports progress as it goes. |
| `read_document` | Extracts the text from a PDF or text file (by document id or attachment path). |
| `download_document` | Saves a file to your download folder. Large files ask first. |
| `list_info_pages` / `get_info_page` | The association's information pages (house rules, contacts, …). |
| `open_probo_browser` | Opens the [interactive browser](interactive-browser.md) in clients that support MCP Apps. |

## Paging and search

`list_messages` and `list_news` use ProBo's own paging: `page=1` is the newest. An empty list means
you've gone past the last page. `search` does the same as ProBo's search box.

## Finding documents by date

`recent_documents` shows what ProBo's archive page shows, which is often only the last four files.
For questions like *"what was uploaded this week?"*, use:

```json
{"name": "find_documents", "arguments": {"added_within_days": 7}}
```

It walks the archive breadth-first (a large archive takes a few seconds) and sends
`notifications/progress` after each folder, so clients can show a progress bar. The results also
contain `resource_link` content blocks pointing at
[`probo://documents/{id}`](resources.md), so a client can attach a document's text with one click.

## Large downloads ask first

When a file is bigger than `PROBO_CONFIRM_DOWNLOAD_MB` (10 MB by default) and the client supports
[elicitation](https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation), you get a
small form first:

> **Budget 2026.pdf is 48 MB. Save it to ~/Downloads/probo?**
> Save as: `Budget 2026.pdf`

You can accept, rename the file, or decline. Clients without elicitation support, and small files,
simply download.

## Errors

Expected problems come back as tool errors (`isError: true`) with a readable message: an invalid id, a
missing setting, a failed login, an unknown document, or a path outside the allowlist. The model sees
the message and can correct itself. Bugs are logged with a traceback on stderr.

!!! info "Reading a message may mark it as read"
    `get_message` opens the thread exactly as your browser does, and ProBo may mark it as read.
