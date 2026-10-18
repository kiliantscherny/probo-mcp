# Claude Code

## From GitHub (no checkout)

```sh
claude mcp add probo -s user \
  -e PROBO_BASE_URL=https://<association>.probo.dk \
  -e PROBO_USERNAME=you@example.com \
  -e PROBO_PASSWORD='op://Private/ProBo/password' \
  -- uvx --from git+https://github.com/kiliantscherny/probo-mcp probo-mcp
```

`-s user` makes the server available in every project. Leave it out to register it only for the
current directory.

Here `PROBO_PASSWORD` is a [1Password reference](../configuration.md#1password). The server resolves it
when it starts, so the secret isn't stored in `~/.claude.json`. A plain password works too.

## From a local checkout

Use this if you're working on the server, or want everything resolved through an `.env` file with
[`op run`](https://developer.1password.com/docs/cli/reference/commands/run/):

```sh
git clone https://github.com/kiliantscherny/probo-mcp && cd probo-mcp
uv sync
cp .env.example .env    # set PROBO_BASE_URL and the op:// references

claude mcp add probo -s user -- \
  op run --env-file "$PWD/.env" -- \
  uv --directory "$PWD" run probo-mcp
```

## Check it's working

```sh
claude mcp get probo     # should say "✔ Connected"
```

Start a new session and ask *"what's new in ProBo?"*. Sessions that were already open don't pick up
new servers.
