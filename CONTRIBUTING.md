# Contributing to stash

Contributions are welcome. Start with the [user guide](docs/user-guide.md) to understand the app and the [development and codebase guide](docs/development.md) for setup, architecture, and checks. Describe the concrete problem, resulting behavior, and checks you actually performed.

stash's primary experience is an ordinary browser app for organizing local projects. Keep everyday workflows understandable and usable without coding-agent integrations. Treat CLI, skills, MCP, and hooks as optional extensions.

Keep the shelf/project experience in one frontend workspace. Project-owned `.stash/` files are authoritative; SQLite is the local registry/cache. The browser, CLI, and MCP bridge share backend rules. Preserve original revisions, human content, historical records, and retry identity. Observations must remain distinct from semantic checkpoints and task completion. Avoid secret values, raw agent transcripts, and automatic project command execution. Assessment checks execute only after explicit selection; outcomes must distinguish failed, unavailable and not run.

Use temporary projects/databases in tests. Codex integration tests currently require codex-cli 0.160.0 because the installer checks its supported version. Live hook trust and interruption tests use a disposable project prepared by:

```sh
.venv/bin/python scripts/prepare_acceptance.py /tmp/stash-acceptance-UNIQUE
```

The generated ACCEPTANCE.md and codex-prompt.txt describe the remaining host gates. Do not claim live client acceptance from provider-shaped synthetic events.

Linux is the initial target. Packaging is a TODO: bundle frontend assets and migrations, verify installation without Node/source checkout, and test upgrades/backups/uninstall without deleting project memory. Verify other platforms before advertising them.
