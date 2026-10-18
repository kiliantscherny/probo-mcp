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

- Prefer **1Password references** (`op://…`) or the Claude Desktop extension, which keeps the password
  in the system keychain. Either way the password isn't stored in a plain-text config file.
- Accounts that use MitID or two-factor authentication aren't supported, because the server can't
  complete those logins.
- The session cookie only lives in the server's memory.

## Read-only guarantees

See [How it works](how-it-works.md#read-only-structurally). In short:

- Requests are limited to an allowlist of read-only routes, checked before any network call.
- The only form ever submitted is the login form.
- Ids are validated as UUIDs, and the server never follows links found in page content.
- Downloads are written only inside the configured download folder, with file names sanitised.

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
