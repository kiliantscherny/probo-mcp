# Configuration

All settings are environment variables. The Claude Desktop extension sets them from its settings form.

| Variable | Required | Default | Description |
|---|:---:|---|---|
| `PROBO_BASE_URL` | ✔ | | Your association's site, `https://<association>.probo.dk`. `https://` is added if missing. Only `*.probo.dk` sites are accepted, so your login can't be sent anywhere else. |
| `PROBO_USERNAME` | ✔ | | Login e-mail, or an `op://` reference. |
| `PROBO_PASSWORD` | | system keychain | Leave unset to use the password [saved in your keychain](#your-password). Or an `op://` 1Password reference. A plain password works but isn't recommended. |
| `PROBO_DOWNLOAD_DIR` | | `~/Downloads/probo` | Where `download_document` saves files. |
| `PROBO_ARCHIVE_DIR` | | `~/Documents/probo` | Where `whats_new` keeps its [local archive](features/tools.md#whats-new-and-the-local-archive) and the record of what it has seen. |
| `PROBO_MAX_DOCUMENT_CHARS` | | `50000` | Longest text `read_document` returns (it says when text was truncated). |
| `PROBO_CONFIRM_DOWNLOAD_MB` | | `10` | Ask before saving files larger than this, when the client supports elicitation. |
| `PROBO_CACHE_SECONDS` | | `60` | How long fetched pages are reused. Set `0` to disable. |
| `PROBO_LOG_LEVEL` | | `WARNING` | Log level for stderr (`DEBUG`, `INFO`, …). |
| `PROBO_HTTP_TOKEN` | | | Over [streamable HTTP](get-started/other-clients.md#streamable-http): the bearer token clients must send (32+ characters). Required with `--allow-remote`, where a random one is made if unset. |

If a required setting is missing, the server still starts. Every tool then returns an error explaining
what to set, which is easier to fix than a client reporting "server failed to start".

## Your password

The password should never sit where other programs can read it, AI agents included. An agent that
can run commands on your computer runs as **you**, so it can read anything you can: a `.env` file, an
MCP client's config, a script's output. Hiding a file doesn't help. What helps is a store that asks
**you** before each read.

There are three ways, from best to worst:

| | How | Who can read it |
|---|---|---|
| **System keychain** (default) | `probo-mcp --set-password` | macOS: only after you approve a system prompt. Windows and Linux: programs running as you, while you're logged in. |
| **1Password** | `PROBO_PASSWORD=op://…` | Only after Touch ID or your 1Password password. |
| **Plain text** | `PROBO_PASSWORD=…` | Any program running as you, including AI agents. Not recommended. |

### System keychain

Run this **in your own terminal**, not through an AI agent (it refuses to run without a terminal):

```sh
PROBO_BASE_URL=https://<association>.probo.dk PROBO_USERNAME=you@example.com probo-mcp --set-password
```

(or `uvx --from git+https://github.com/kiliantscherny/probo-mcp probo-mcp --set-password`, which asks for the site
and username). Then leave `PROBO_PASSWORD` unset. `probo-mcp --forget-password` removes it again.

- **macOS:** the password goes in your login keychain with no trusted apps. You type it into Apple's
  `security` tool itself, so it never passes through probo-mcp or a command line. Whenever the server
  logs in (once per start), macOS asks whether `security` may use the item. **Choose Allow, never
  Always Allow**: "Always Allow" would let any program read it silently from then on. Deny a prompt
  you didn't expect, for example if no ProBo server was just starting.
- **Windows and Linux:** the password goes in the Credential Manager or the Secret Service
  (GNOME Keyring, KWallet) via [`keyring`](https://pypi.org/project/keyring/). It's out of files and
  config, but these stores don't ask per read.

### 1Password

Any setting can hold a [secret reference](https://developer.1password.com/docs/cli/secret-reference-syntax/)
instead of a value:

```sh
PROBO_USERNAME=op://Private/ProBo/username
PROBO_PASSWORD=op://Private/ProBo/password
```

This keeps the password in 1Password and needs Touch ID (or your 1Password password) to read it. Note
that after you approve, the 1Password CLI stays unlocked for that app for a while, about 10 minutes by
default. During that window other commands started from the same app, an AI agent's included, could
read the item too.

When a value starts with `op://`, the server runs
`op read --no-newline <reference>` at start-up. This works anywhere you can set environment variables,
including the Claude Desktop settings form. It needs the [1Password CLI](https://developer.1password.com/docs/cli/get-started/)
with the desktop-app integration enabled, so that Touch ID can approve access. The server looks for
`op` on `PATH` and in the usual install locations (`/opt/homebrew/bin`, `/usr/local/bin`), because
desktop apps start with a minimal `PATH`.

To keep the references in an `.env` file, load it as it is, for example with `uv run --env-file .env probo-mcp`.
The server then resolves the references itself.

!!! warning "Don't use `op run` to start the server"
    `op run` resolves the references *before* starting the server and passes it the real password in
    its environment, where any program running as you (`ps eww`) can read it. Passing the `op://`
    reference and letting the server resolve it keeps the password out of the environment.

!!! tip "Find the references"
    In the 1Password app, open the item, click the field's dropdown and choose **Copy Secret Reference**.
    Or use `op item get "ProBo" --format json | jq '{vault: .vault.id, id}'` to reference by ID, which
    keeps working if the item is renamed.

## More than one association

Register one server per site under different names, e.g. `probo-home` and `probo-cabin`, each with its
own `PROBO_BASE_URL` and login.
