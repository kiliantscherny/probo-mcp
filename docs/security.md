# Privacy & security

## What goes where

- The server runs **on your computer** and talks only to the ProBo site you configure.
- What ProBo returns (messages, documents, and so on) goes to your MCP client, and from there to the AI
  model you use. Treat it as you would pasting the same content into a chat yourself.
- Nothing is sent anywhere else. There's no telemetry.

## Your neighbours' data

ProBo has a residents directory with names, e-mails and phone numbers. probo-mcp deliberately doesn't
expose it. Messages and documents can still mention people, so think before sharing a conversation.

## Credentials

The goal is that no AI agent can obtain your ProBo password, not even an agent that can run commands
on your computer.

- **Store it where reading it needs you:** the system keychain (`probo-mcp --set-password`, which on
  macOS asks before every read) or 1Password. See [Your password](configuration.md#your-password). A
  plain-text `PROBO_PASSWORD` works but logs a warning, because any program running as you can read it.
- **It's never exposed by the server.** No tool, resource, prompt or log contains it, and it's hidden
  from the settings' `repr()`, so tracebacks don't show it either. The server keeps it only in memory.
- **It only goes to ProBo.** `PROBO_BASE_URL` must be an `https://<association>.probo.dk` address with
  no port or user info, so changing the configuration can't send the login elsewhere. The login form
  is posted without following redirects, and a redirect to another host is refused.
- **What a manipulated agent could still do:** an agent with full shell access runs as you. It could
  change probo-mcp's code, or start it and wait for you to approve the keychain prompt. So only
  approve keychain or Touch ID prompts you expect. With Claude Code you can add
  [deny rules and the sandbox](https://code.claude.com/docs/en/sandboxing) as extra guards, but note
  that deny rules only cover commands Claude Code recognises, not arbitrary scripts.
- **Environment variables aren't private.** Any program running as you can read another program's
  environment (`ps eww` on macOS, `/proc/<pid>/environ` on Linux). So a password passed in
  `PROBO_PASSWORD`, whether typed into Claude Desktop's settings or injected by `op run`, can be read
  while the server runs. The keychain and a plain `op://` reference avoid this: the server fetches the
  password itself, so only the reference, or nothing, is in its environment.
- **Downloaded files are marked as from the internet** (macOS quarantine, Windows zone mark), so the
  OS warns before an attachment from another resident runs. Downloads stop at `PROBO_MAX_DOWNLOAD_MB`.
- **The HTTP transport has no authentication.** It only listens on this computer unless you pass
  `--allow-remote`.
- Accounts that use MitID or two-factor authentication aren't supported, because the server can't
  complete those logins.
- The session cookie only lives in the server's memory.

## Read-only guarantees

See [How it works](how-it-works.md#read-only-structurally). In short:

- Requests are limited to an allowlist of read-only routes, checked before any network call.
- The only form ever submitted is the login form.
- Ids are validated as UUIDs, and the server never follows links found in page content.
- Downloads are written only inside the configured download folder, and `whats_new` writes only inside
  the archive folder, with file names sanitised and every path checked to stay inside it.

One side effect remains: **opening a message thread may mark it as read** in ProBo, just as viewing it
in your browser would.

## Prompt injection

Messages and documents are written by other people, and a model reads them. probo-mcp limits what a
manipulated model could do, because there are no tools that send, change or delete anything. Still,
review what a model suggests before acting on it.

## Running over HTTP

`--transport streamable-http` has no authentication. Bind it to `127.0.0.1` only.

## Reporting a vulnerability

Please open a [private security advisory](https://github.com/kiliantscherny/probo-mcp/security/advisories/new)
rather than a public issue.
