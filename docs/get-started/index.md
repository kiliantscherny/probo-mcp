# Get started

You need:

- **A ProBo account** that logs in with an e-mail and password. Accounts that require MitID or
  two-factor authentication aren't supported.
- **Your association's ProBo address.** It's the site you log in to, of the form `https://<association>.probo.dk`.
- **An MCP client.** Pick yours:

<div class="grid cards" markdown>

-   :simple-claude:{ .lg .middle } [**Claude Desktop**](claude-desktop.md)

    One-click extension with a settings form and the interactive browser.

-   :material-console:{ .lg .middle } [**Claude Code**](claude-code.md)

    One command, with credentials from 1Password.

-   :material-connection:{ .lg .middle } [**Other clients**](other-clients.md)

    Any client that speaks MCP over stdio or streamable HTTP, plus the MCP Inspector.

</div>

The server runs on your own computer, talks only to your association's ProBo site, and needs
[uv](https://docs.astral.sh/uv/) (Claude Desktop extensions bring their own).
