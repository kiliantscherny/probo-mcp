# Configuration

All settings are environment variables. The Claude Desktop extension sets them from its settings form.

| Variable | Required | Default | Description |
|---|:---:|---|---|
| `PROBO_BASE_URL` | ✔ | | Your association's site, e.g. `https://<association>.probo.dk`. `https://` is added if missing; plain `http` is rejected. |
| `PROBO_USERNAME` | ✔ | | Login e-mail, or an `op://` reference. |
| `PROBO_PASSWORD` | ✔ | | Password, or an `op://` reference. |
| `PROBO_DOWNLOAD_DIR` | | `~/Downloads/probo` | Where `download_document` saves files. |
| `PROBO_MAX_DOCUMENT_CHARS` | | `50000` | Longest text `read_document` returns (it says when text was truncated). |
| `PROBO_CONFIRM_DOWNLOAD_MB` | | `10` | Ask before saving files larger than this, when the client supports elicitation. |
| `PROBO_CACHE_SECONDS` | | `60` | How long fetched pages are reused. Set `0` to disable. |
| `PROBO_LOG_LEVEL` | | `WARNING` | Log level for stderr (`DEBUG`, `INFO`, …). |

If a required setting is missing, the server still starts. Every tool then returns an error explaining
what to set, which is easier to fix than a client reporting "server failed to start".

## 1Password

Any setting can hold a [secret reference](https://developer.1password.com/docs/cli/secret-reference-syntax/)
instead of a value:

```sh
PROBO_USERNAME=op://Private/ProBo/username
PROBO_PASSWORD=op://Private/ProBo/password
```

There are two ways to use them.

**Let the server resolve them.** When a value starts with `op://`, the server runs
`op read --no-newline <reference>` at start-up. This works anywhere you can set environment variables,
including the Claude Desktop settings form. It needs the [1Password CLI](https://developer.1password.com/docs/cli/get-started/)
with the desktop-app integration enabled, so that Touch ID can approve access. The server looks for
`op` on `PATH` and in the usual install locations (`/opt/homebrew/bin`, `/usr/local/bin`), because
desktop apps start with a minimal `PATH`.

**Or wrap the server with [`op run`](https://developer.1password.com/docs/cli/reference/commands/run/).**
1Password then resolves the references in an env file and starts the server with the real values:

```sh
op run --env-file .env -- uv run probo-mcp
```

!!! tip "Find the references"
    In the 1Password app, open the item, click the field's dropdown and choose **Copy Secret Reference**.
    Or use `op item get "ProBo" --format json | jq '{vault: .vault.id, id}'` to reference by ID, which
    keeps working if the item is renamed.

## More than one association

Register one server per site under different names, e.g. `probo-home` and `probo-cabin`, each with its
own `PROBO_BASE_URL` and login.
