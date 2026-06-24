# CF_GPTCodingMCP_Auto

A Windows-friendly local launcher for `coding-tools-mcp`, designed to connect local projects to Codex or ChatGPT Web MCP with project-local runtime files.

The launcher wraps the original terminal workflow in a small Tkinter desktop UI. It can create a project-local Python environment, install and run `coding-tools-mcp`, switch workspaces, configure proxy settings, start a Cloudflare quick tunnel for ChatGPT Web, and show the OAuth values needed during connection.

## Goals

- Keep everything inside the current project
- Avoid writing runtime files to `C:` by default
- Run the local MCP service first, then connect Codex
- Provide a safer GUI flow for ChatGPT Web MCP + OAuth + Cloudflare Tunnel
- Make project switching easier than repeatedly editing command-line arguments

## Features

- Project-local `.venv` and `.runtime` directories
- Tkinter GUI with project switching
- Local Codex MCP URL snippet generation
- ChatGPT Web OAuth mode
- Optional local `cloudflared.exe` download into `.runtime/bin`
- Configurable proxy panel, including a `127.0.0.1:20100` preset
- Stable OAuth password, Client ID, and Client Secret storage under `.runtime/state`
- Tunnel URL and OAuth metadata validation to avoid stale quick-tunnel URLs

## Layout

- `.venv/`: project virtual environment
- `.runtime/`: logs, PID, snippet, proxy settings, local helper binaries

## Manual steps

### 1. Create the project venv

From the project root:

```powershell
uv venv .venv
```

### 2. Activate it

```powershell
.venv\Scripts\Activate.ps1
```

### 3. Start the launcher

CLI:

```powershell
python launcher.py
```

Desktop GUI:

```powershell
python app.py
```

Double-click launcher:

```powershell
start_launcher.bat
```

## Menu

- `1`: check environment
- `2`: create `.venv`
- `3`: install/upgrade `coding-tools-mcp`
- `4`: start the local MCP server
- `5`: stop the server
- `6`: generate a Codex config snippet
- `7`: show Codex config candidates
- `8`: set or clear proxy
- `9`: bootstrap all

## Notes

- The GUI has a left-side project list.
- Use `Add` to save a workspace.
- Use `Switch` to stop the current server/tunnel and start the selected project.
- `4` asks for workspace, port, tool profile, permission mode, and network access.
- `6` writes a snippet to `.runtime/codex-mcp-snippet.toml`.
- `7` shows likely Codex config locations and highlights existing files.
- `8` stores proxy settings in `.runtime/proxy.env` so installs and launches can reuse them.
- The GUI proxy panel can enable/disable proxy, choose `http` or `socks5`, set host/port, or use the `127.0.0.1:20100` preset.
- `9` runs create venv -> install package -> start server -> write snippet.

If you are unsure which Codex config file to edit, use `7` first and save the snippet before modifying anything.

## ChatGPT Web Mode

The GUI includes a `ChatGPT Web Mode` panel for the workflow where ChatGPT connects to your local project through a public Cloudflare Tunnel.

### What the app does

- Starts `coding-tools-mcp` with `--oauth-mode`
- Uses `full` tool profile and `trusted` permission mode for this mode
- Starts `cloudflared tunnel --url http://127.0.0.1:<port>`
- Extracts the public tunnel URL from the Cloudflare log
- Shows and copies the final MCP URL: `<tunnel-url>/mcp`
- Generates, stores, shows, and copies the OAuth password
- Generates, stores, shows, and copies the OAuth Client ID and Client Secret

### Manual steps

1. Start the desktop GUI with `start_launcher.bat` or `python app.py`.
2. Use `Install MCP` if the package is not ready.
3. In `ChatGPT Web Mode`, click `Start OAuth MCP + Tunnel`.
4. If `cloudflared` is not available, the launcher downloads it into `.runtime/bin`.
5. Copy the URL from `Copy MCP URL`.
6. Open ChatGPT web settings and create/connect an MCP app.
7. Paste the copied URL as the MCP server URL.
8. If ChatGPT asks for OAuth Client ID, click `Copy Client ID` in the launcher and paste it.
9. If ChatGPT asks for OAuth Client Secret, click `Copy Secret` in the launcher and paste it.
10. When OAuth opens, click `Copy Password` in the launcher and paste it.
11. Return to the app details page and refresh until tools are listed.
12. Stop the tunnel when finished.

### Named Tunnel mode

Quick tunnels generate a new `trycloudflare.com` URL whenever the tunnel is restarted. Use Named Tunnel mode if you want ChatGPT to keep one stable MCP app URL.

Recommended setup:

1. In Cloudflare Zero Trust, create a Cloudflare Tunnel.
2. Choose the `cloudflared` connector and copy the tunnel token.
3. Add a public hostname for the tunnel, for example `mcp.example.com`.
4. Set the public hostname service to `http://127.0.0.1:<port>`, using the same port shown in the launcher.
5. In the launcher, set `Tunnel mode` to `named`.
6. Paste the fixed public URL, for example `https://mcp.example.com`, into `Tunnel URL`.
7. Paste the Cloudflare tunnel token into `Named token`.
8. Click `Start OAuth MCP + Tunnel`.
9. Configure ChatGPT with `https://mcp.example.com/mcp`.

The token is stored in `.runtime/state/named-tunnel-token.txt`, which is ignored by Git. Treat it as a secret.

If you do not want to use the Zero Trust dashboard token flow, you can manage the tunnel locally with `cloudflared` CLI and keep the run config inside `.runtime/cloudflared`.

Local runtime config flow:

1. Run `cloudflared tunnel login` once to authorize your Cloudflare account.
2. Create credentials inside this project:
   ```powershell
   .runtime\bin\cloudflared.exe tunnel create CF_GPTCodingMCP_Auto --credentials-file .runtime\cloudflared\CF_GPTCodingMCP_Auto.json
   ```
3. Route your fixed hostname:
   ```powershell
   .runtime\bin\cloudflared.exe tunnel route dns CF_GPTCodingMCP_Auto mcp.example.com
   ```
4. Create `.runtime/cloudflared/config.yml`:
   ```yaml
   tunnel: CF_GPTCodingMCP_Auto
   credentials-file: .runtime/cloudflared/CF_GPTCodingMCP_Auto.json
   ingress:
     - hostname: mcp.example.com
       service: http://127.0.0.1:48010
     - service: http_status:404
   ```
5. In the launcher, set `Tunnel mode` to `named`, leave `Named token` empty, and set `Tunnel URL` to `https://mcp.example.com`.

This still uses a Cloudflare account and a Cloudflare-managed DNS hostname, but the connector runtime config and credentials stay in the project `.runtime` directory.

### Safety defaults

- This mode exposes the local MCP server through a public tunnel.
- Use it only for trusted workspaces.
- Close the tunnel when you finish.
- Prefer the normal local Codex mode for private or sensitive projects.
- Auto-installing `cloudflared` downloads the binary into `.runtime/bin`; it does not install a global Cloudflare app.
- Do not commit `.runtime/`; it may contain local OAuth values, logs, and process state.

### ChatGPT Web permission mode

The GUI starts ChatGPT Web Mode with `trusted` permission by default. This allows normal local development commands while keeping some safety gates enabled.

If ChatGPT Web must directly write project files through MCP tools, switch `Web permission` to `dangerous` before starting `Start OAuth MCP + Tunnel`. This maps to `coding-tools-mcp --permission-mode dangerous`.

Use `dangerous` only for trusted projects. It disables MCP permission gates, although direct file tools are still limited to the configured workspace.

The ChatGPT Web launcher always starts `coding-tools-mcp` with `tool-profile=full`, so the MCP server exposes `apply_patch`. If ChatGPT says the current MCP toolset has no write or patch tool, it is usually seeing an old cached tool list or a connection that was created while the server was not running in ChatGPT Web Mode.

To refresh the writable tool list:

1. In the launcher, stop the tunnel and server.
2. Set `Web permission` to `dangerous` if you want ChatGPT to write files directly.
3. Start `Start OAuth MCP + Tunnel`.
4. Confirm the log says `profile=full`, `apply_patch=enabled`.
5. In ChatGPT, open the MCP app details page and click refresh until tools are listed again.
6. If it still shows read-only tools, disconnect and reconnect the MCP app with the current tunnel URL.

### OAuth reconnect checklist

If ChatGPT repeatedly asks you to reconnect or re-enter the OAuth password:

- Keep the launcher, MCP server, and Cloudflare tunnel running during the whole ChatGPT session.
- Do not click `Reset Password` or `Reset Client` unless you also update the ChatGPT MCP app configuration.
- Re-copy `Client Secret` into ChatGPT if the log shows `invalid_client`.
- Re-copy the MCP URL after every quick tunnel restart; quick tunnel URLs are temporary.
- Click `Test OAuth` and confirm the metadata issuer matches the current tunnel URL.
- If you stop and restart the MCP server, ChatGPT may need to reconnect because OAuth tokens are server-runtime state.

## Codex integration assessment

The best integration path is direct local MCP:

```toml
[mcp_servers.coding_tools]
url = "http://127.0.0.1:8010/mcp"
```

Assessment:

- Works well when the launcher is running the selected project.
- No Cloudflare Tunnel is needed for local Codex.
- Codex can switch projects if the launcher switches the active MCP workspace.
- Current limitation: one active project/server at a time.
- Advanced option: run one MCP server per project on different ports, then add multiple Codex MCP entries.
- Best near-term UX: use this launcher as the project switcher, then keep Codex pointed at the stable local URL.
