# Claude Desktop

The easiest way to use probo-mcp is as a Claude Desktop extension (an `.mcpb` bundle).

## Install the extension

1. Download `probo-mcp-<version>.mcpb` from the
   [latest GitHub release](https://github.com/kiliantscherny/probo-mcp/releases/latest).
2. Open it: double-click the file, or drag it onto the Claude Desktop window, or use
   **Settings → Extensions → Install extension…**.
3. Click **Install** and fill in the settings form:

    | Setting | What to enter |
    |---|---|
    | **ProBo site** | Your association's address, e.g. `https://<association>.probo.dk` |
    | **Username** | The e-mail you log in with |
    | **Password** | Your ProBo password. It is stored in the system keychain, not in a config file. |
    | **Download folder** | Where downloaded documents are saved (default `~/Downloads/probo`) |

4. Make sure the extension is **enabled**, then start a new chat.

Claude Desktop installs Python and the dependencies itself (the bundle uses its `uv` runtime), so
there is nothing else to install.

!!! tip "Keep the password in 1Password instead"
    If you use the [1Password CLI](https://developer.1password.com/docs/cli/), enter a secret
    reference such as `op://Private/ProBo/password` in the **Password** field. The server resolves it
    with `op read` when it starts, and the 1Password app asks you to approve with Touch ID.
    See [Configuration → 1Password](../configuration.md#1password).

## Try it

- *"What's new in ProBo?"*
- *"Open the ProBo browser."* This opens the [interactive browser](../features/interactive-browser.md) in the chat.
- Use the prompts from the **+** menu: **What's new**, **Summarise a document**,
  **Prepare for the general meeting**.

When Claude asks to use a tool for the first time, Claude Desktop shows a permission prompt. Every tool
except **Download document** is marked read-only. That one saves a file to your computer but changes
nothing in ProBo.

## Updating and removing

Install a newer `.mcpb` to update. To remove it, open **Settings → Extensions**, choose ProBo, and
click **Uninstall**.

## Without the extension

You can also add the server to `claude_desktop_config.json` by hand (for example to point at a local
checkout). See [Other clients](other-clients.md#claude-desktop-config-file).
