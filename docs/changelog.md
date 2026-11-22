# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/)
and the project uses [semantic versioning](https://semver.org/).

## 0.1.0 (unreleased)

First release.

- Tools for messages, news, the document archive (including a full-archive search with progress) and
  info pages, with structured output and read-only annotations.
- `whats_new`: fetches everything not yet in a local archive (`PROBO_ARCHIVE_DIR`), saves it as Markdown
  and files, and remembers it, so the next call returns only what is new or changed.
- Dates are parsed from every format ProBo shows (English and Danish months) and returned in Danish
  local time with a UTC offset, as the `date-time` output schemas require.
- E-mail addresses hidden by Cloudflare's obfuscation are shown in message and news text.
- `fetch_history` and `probo-mcp --fetch-history`: save all past news, the whole document archive
  and optionally older messages to the local archive.
- PDF text keeps reading order and table rows (pypdf layout mode, with plain mode for rotated text).
- Security: the password comes from the system keychain by default (`probo-mcp --set-password`; on
  macOS every read needs approval), never appears in reprs or logs, and only goes to `*.probo.dk`
  sites. The login form isn't re-sent on redirects. Downloads are capped (`PROBO_MAX_DOWNLOAD_MB`),
  streamed, and marked as from the internet. Files are written atomically without following symlinks.
  The HTTP transport refuses non-local hosts without `--allow-remote`. CI actions are pinned to
  commits, and releases are built read-only and published with provenance and checksums.
- PDF text extraction, and downloads that ask before saving large files (elicitation).
- `probo://` resource templates with argument completion, plus three prompts.
- Interactive ProBo browser as an MCP App.
- `op://` 1Password references for any setting.
- Claude Desktop extension (`.mcpb`).
- Tests on both MCP protocol eras; ruff, ty and tox; documentation site.
