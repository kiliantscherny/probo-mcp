# Claude Code

## From GitHub (no checkout)

First save your password in the system keychain. Do this in your own terminal, not through Claude:

```sh
uvx --from git+https://github.com/kiliantscherny/probo-mcp probo-mcp --set-password
```

Then register the server **without** a password:

```sh
claude mcp add probo -s user \
  -e PROBO_BASE_URL=https://<association>.probo.dk \
  -e PROBO_USERNAME=you@example.com \
  -- uvx --from git+https://github.com/kiliantscherny/probo-mcp probo-mcp
```

`-s user` makes the server available in every project. Leave it out to register it only for the
current directory.

When the server first logs in, macOS asks whether `security` may use the item: choose **Allow**
(not "Always Allow"). If you use 1Password, add `-e PROBO_PASSWORD='op://Private/ProBo/password'`
instead of saving to the keychain; see [Your password](../configuration.md#your-password).

!!! warning "Don't put the password itself in `-e PROBO_PASSWORD=…`"
    `claude mcp add` stores `-e` values in plain text in `~/.claude.json`, which Claude can read.

## From a local checkout

Use this if you're working on the server. With the password in the keychain:

```sh
git clone https://github.com/kiliantscherny/probo-mcp && cd probo-mcp
uv sync
PROBO_BASE_URL=https://<association>.probo.dk PROBO_USERNAME=you@example.com uv run probo-mcp --set-password

claude mcp add probo -s user \
  -e PROBO_BASE_URL=https://<association>.probo.dk \
  -e PROBO_USERNAME=you@example.com \
  -- uv --directory "$PWD" run probo-mcp
```

Or, with 1Password, settings from an `.env` file of `op://` references, which the server resolves itself:

```sh
git clone https://github.com/kiliantscherny/probo-mcp && cd probo-mcp
uv sync
cp .env.example .env    # set PROBO_BASE_URL and op:// references, never the password itself

claude mcp add probo -s user -- \
  uv --directory "$PWD" run --env-file "$PWD/.env" probo-mcp
```

## Check it's working

```sh
claude mcp get probo     # should say "✔ Connected"
```

Start a new session and ask *"what's new in ProBo?"*. Sessions that were already open don't pick up
new servers.
