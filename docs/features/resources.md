# Resources

Resources let a client attach ProBo content to a conversation directly, without the model calling a
tool. probo-mcp exposes four resource templates, each rendered as Markdown:

| URI template | Content |
|---|---|
| `probo://messages/{message_id}` | A message thread: each reply with sender, date, recipients and attachments. |
| `probo://news/{news_id}` | A news post and its comments. |
| `probo://documents/{document_id}` | A document's metadata and extracted text. |
| `probo://info-pages/{page_id}` | An information page. |

There's also one static resource, `ui://probo/browser.html`: the
[interactive browser](interactive-browser.md) (`text/html;profile=mcp-app`).

## Argument completion

The server implements `completion/complete` for every id parameter, so clients with a resource
picker can suggest values as you type. You can type a **name**, not just an id:

- `message_id` matches sender and subject in your inbox.
- `news_id` matches news subjects.
- `document_id` matches file names in the "recently added" widget and the archive root.
- `page_id` matches info-page titles.

Values are always the ids themselves. Document completion deliberately doesn't walk the whole archive,
because completion has to be instant. Use `find_documents` for that.

Prompt arguments named `language` complete too (`English`, `Dansk`, `Deutsch`, …).

## Unknown ids

Reading a resource with an unknown or malformed id returns JSON-RPC error `-32602` (resource not found).
