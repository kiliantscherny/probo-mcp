# Tools

Every tool returns **structured output**, a JSON object described by a published output schema, and
every tool except `download_document`, `whats_new` and `fetch_history` (which write to your own disk) is annotated
`readOnlyHint: true`. Items include a `url`
that opens the same page in your browser, where you're already logged in.

| Tool | What it does |
|---|---|
| `whats_new` | Everything new since you last asked, fetched in full and saved to your [local archive](#whats-new-and-the-local-archive). |
| `fetch_history` | Saves older items to the local archive: all past news, the whole document archive, and optionally older messages. |
| `get_overview` | A quick look at the latest inbox messages, news posts and recently added documents. It remembers nothing. |
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

## What's new and the local archive

`whats_new` is the tool to use for *"what's new?"* (or *"hvad er nyt i ejerforeningen?"*). It looks at
the inbox, the news list and the whole document archive. Anything the local archive hasn't saved yet
is fetched in full: the thread or post, its attachments, and each document along with its extracted text.
It saves everything under `PROBO_ARCHIVE_DIR` (`~/Documents/probo` by default) and remembers it:

```text
messages/2026-10-01 Indkaldelse til generalforsamling (aaaaaaaa)/thread.md   + attachments
news/2026-10-13 Heating off tomorrow (22222222)/post.md                      + attachments
documents/<archive folder>/<file>                                            + <file>.txt
.probo-mcp-seen.json                                                         what has been saved
.probo-mcp-last-run.json                                                     the last result
```

- **"New" means new to the archive**, not unread in ProBo. Something you already read in the browser
  or the app is still new here until `whats_new` has saved it.
- **A new reply or comment makes an item new again.** It comes back with `updated: true`, and the
  thread's folder is overwritten with the latest version.
- **The first run only fetches the last 30 days.** Anything older is recorded as history, so the
  first call isn't years of old news. [`fetch_history`](#older-items-fetch_history) saves the history.
  To start over, delete `.probo-mcp-seen.json`.
- **All three message folders are checked:** the inbox (*Indbakke*, which includes messages between
  residents) plus *Arkiver* and *Arkiverede notifikationer*, so a thread archived in the browser
  before `whats_new` saw it isn't missed.
- **Results come in batches** of `max_items` (15 by default). `remaining` says how many are still
  waiting, and calling again returns them.
- **Failures are retried.** An item that fails to download is listed in `errors` and stays new, so the
  next call tries it again.
- **Documents are saved once.** When a message announces new archive documents (ProBo's *"Nyt
  dokument"* notifications), its attachments link to the copy under `documents/` instead of being
  downloaded again.
- **Lost results can be repeated.** Items count as seen as soon as they're saved. If a result never
  reached the client, `whats_new(repeat_last=true)` returns it again from `.probo-mcp-last-run.json`
  without fetching anything.
- **Long recipient lists are shortened** to the first 10 names, *"and N more"*.
- **Files larger than `PROBO_CONFIRM_DOWNLOAD_MB` are not downloaded.** They're listed with a note so
  you can fetch them with `download_document`.

Because the files are plain Markdown, PDFs and text, you can also search them yourself, open them in
Obsidian, or ask Claude Code to compare them across months.

## Older items: `fetch_history`

`whats_new` is about what's new. To keep a complete local copy, `fetch_history` reads **every** page
of the news list and walks the whole document archive. It saves everything older than the first run
that isn't in the archive yet. With `sections: ["message"]` it does the same for older messages.

- It returns a short list of what it saved (title and file), not the content, so filling in years
  of history doesn't fill up the conversation. Repeat until `remaining` is 0.
- It never takes over `whats_new`'s job. Items newer than the first run, and changes to items
  already in the archive (a new reply or comment), are left for `whats_new` to report.
- For a big archive, the terminal is quicker. This runs it to the end and prints each file:

```sh
probo-mcp --fetch-history                     # news and documents
probo-mcp --fetch-history news document message
```

It reads the same settings as the server, e.g. `uv run --env-file .env probo-mcp --fetch-history` in a checkout.

## PDF text

PDFs are read with pypdf's layout mode, which follows the page's geometry. Text drawn word by word
doesn't come out one word per line, and table rows stay on one line
(`Fællesbidrag   kr.   5.340.000   5.193.000`). Runs of padding spaces are shortened to keep it compact.
Scanned PDFs have no text to extract.

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
