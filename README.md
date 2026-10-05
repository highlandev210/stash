# stash

stash is a local project organizer. Keep your projects on one shelf, track tasks, read notes, and remember where you stopped—all in a browser app on your own computer.

Use it yourself through the app. Coding-agent integrations are optional and let agents read and update the same records.

## What you can do

- Find projects by name, status, or tags, using a grid or list.
- Keep a description, current focus, and next step for each project.
- Track tasks, bugs, and feature ideas with comments.
- Read project Markdown and create development notes.
- Save decisions and progress notes so you can pick up work later.
- Export project records as JSON or Markdown.

Projects stay in their existing folders. stash adds a `.stash/` folder for their records and keeps shelf settings separately. A project does not need Git to be registered.

## Install and open the app

Linux is the initial target. stash currently requires installation from source; there is no prebuilt desktop installer. You need Node.js 22.12+ with npm, Python 3.10+, and uv for the setup script.

```bash
git clone https://github.com/highlandev210/stash.git
cd stash
bash scripts/setup.sh
npm run build
npm start
```

Open **http://127.0.0.1:8000**. Keep the terminal running while you use stash. Stop it with Ctrl+C. To open it again, run `npm start` from the checkout. This starts stash, not the projects on your shelf.

Without uv, follow the manual setup in the [development guide](docs/development.md). To install commands for all users and run independently of the checkout, see [Linux systemwide installation](docs/systemwide-install.md).

## Your first project

1. Open **Settings** and enter your name for attribution on saved changes.
2. Click **Add project**, enter the full path to an existing folder, and click **Register project**. For example, `/home/you/Projects/my-project`.
3. Registration opens **Overview**. Use **Initialize project**: choose new or existing, supply its intended goal and requirements, inspect the repository, review context and issue candidates, then accept the selected changes and tracking settings.
4. Use **Issues** for tasks and **Docs** for notes. Before stopping, use **Context → Save session handoff** to record what happened and what to do next.

If you keep projects under one parent folder, set it as the **Master folder** in Settings. Add project then lists its immediate subfolders for you to choose from. Discovery does not automatically register every folder.

The [user guide](docs/user-guide.md) explains the five project tabs, backups, moved folders, and common problems. You do not need CLI commands or an agent to follow it.

See [initialization and reassessment](docs/project-assessment.md) for code inspection, explicit checks, deeper agent analysis, issue reconciliation and keeping context current.

## Where your data lives

Project records live in `<project>/.stash/`. Shelf locations and settings live in `$XDG_DATA_HOME/stash/` or `~/.local/share/stash/`. Back up both your project folders, including hidden `.stash/` folders, and your shelf data.

Removing a project from the shelf preserves its files and records. If a folder moves, update its path or register the new location. If the shelf database is lost, you must register your project folders again; their `.stash/` records can still be read.

The app runs on localhost without a cloud account. It is intended for local use, not as an authenticated shared network service. See [storage details](docs/folder-storage.md) for file formats, migration, and recovery.

## Documentation

- [User guide](docs/user-guide.md): everyday browser workflows and troubleshooting.
- [Systemwide installation](docs/systemwide-install.md): Linux installation, startup, updates, and removal.
- [Development and codebase guide](docs/development.md): architecture, source map, setup, and checks for human contributors and coding agents.
- [Documentation index](docs/README.md): detailed storage, sessions, watcher, and integration references.
- [Contributing](CONTRIBUTING.md): project conventions and acceptance requirements.

## Optional coding-agent support

The CLI, reusable skill, MCP bridge, and supported Codex hooks share the app's records. They require their own setup; opening stash does not launch an agent or grant hook trust. Start with [agent integration](docs/agent-integration.md), then use the [MCP reference](docs/mcp.md) or [Codex integration reference](docs/codex-integration.md) as needed.

## License

[MIT](LICENSE).
