# Linux systemwide installation

This manual source installation makes stash's commands available to all users. It requires a source checkout, Node.js 22.12+ with npm, Python 3.10+ with the `venv` module, and sudo access. On Debian/Ubuntu, the `venv` module may require installing `python3-venv` through your package manager.

For everyday use, you will start the server and use stash in your browser. The CLI and agent integrations are optional. After installation, continue with the [user guide](user-guide.md).

Standalone packaging and installation lifecycle verification remain TODOs (see [Contributing](../CONTRIBUTING.md)). These instructions describe the current source installation approach; they are not a prebuilt installer.

## Install

From your stash checkout, build the frontend as your normal user:

```bash
cd /path/to/stash
npm ci
npm run build
```

Create a dedicated Python environment and install the backend/CLI:

```bash
sudo python3 -m venv /opt/stash/venv
sudo /opt/stash/venv/bin/pip install .
sudo cp -r dist /opt/stash/frontend
```

Expose the three commands on PATH:

```bash
sudo ln -s /opt/stash/venv/bin/stash /usr/local/bin/stash
sudo ln -s /opt/stash/venv/bin/stash-server /usr/local/bin/stash-server
sudo ln -s /opt/stash/venv/bin/stash-mcp /usr/local/bin/stash-mcp
```

These commands assume a new installation and no existing files at those destinations. If a link already exists, inspect it before replacing it. Ensure `/usr/local/bin` is on PATH, and remove any old `stash` shell alias that points at a checkout's `.venv`.

## Start and verify

Start the server as your normal user:

```bash
STASH_FRONTEND=/opt/stash/frontend stash-server
```

Open **http://127.0.0.1:8000**. In another terminal, check the command and API:

```bash
command -v stash
stash --help
stash projects list
```

The API commands require the server to be running. `STASH_FRONTEND` selects the copied frontend so startup works from any directory. Stop the foreground server with Ctrl+C. This installation does not configure automatic startup or an application-menu shortcut.

Run the server without sudo so project access and data belong to your user. By default, shelf data lives in `$XDG_DATA_HOME/stash` or `~/.local/share/stash`; project records live in each project's `.stash/` folder. Installing commands for all users does not create a shared shelf. The server binds to `127.0.0.1:8000`; only one server can use that port at a time.

The portable agent skill is not installed by these commands. See [agent integration](agent-integration.md) for skill setup and [MCP setup](mcp.md) for connecting the bridge; a systemwide installation can use `/opt/stash/venv/bin/python` in place of the checkout's `.venv/bin/python`.

## Update

Stop the server and back up your shelf data and project `.stash/` folders first. From the updated source checkout:

```bash
npm ci
npm run build
sudo /opt/stash/venv/bin/pip install --upgrade .
sudo mv /opt/stash/frontend /opt/stash/frontend.previous
sudo cp -r dist /opt/stash/frontend
```

The backup destination `frontend.previous` must not already exist; choose another name if you retained an earlier copy. Restart with the same `STASH_FRONTEND` command and verify the UI and CLI. The command symlinks do not need to change.

## Remove

Stop the server. After confirming that the three links still point to `/opt/stash/venv/bin/`, remove the installed commands and application files:

```bash
sudo rm /usr/local/bin/stash /usr/local/bin/stash-server /usr/local/bin/stash-mcp
sudo rm -r /opt/stash
```

These commands preserve your source checkout, per-user shelf data, and project `.stash/` folders. Keep those records if you intend to reinstall.
