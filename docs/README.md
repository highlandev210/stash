# Documentation

stash is a browser app for organizing local project folders. Start with the guide that matches your task.

## Using the app

- [Getting started](../README.md): install from source and open your first project.
- [User guide](user-guide.md): browser workflows, data ownership, and troubleshooting.
- [Linux systemwide installation](systemwide-install.md): install, start, update, and remove.

- [Project initialization and reassessment](project-assessment.md): initial context, evidence-backed issues, review, checks and tracking.

## Understanding and changing the code

- [Development and codebase guide](development.md): architecture, source map, setup, and checks.
- [Contributing](../CONTRIBUTING.md): implementation rules and acceptance requirements.
- [Folder storage](folder-storage.md): authoritative records, revisions, transactions, migration, and backups.
- [Sessions and checkpoints](session-checkpoints.md): session state, payloads, offline drafts, and resuming work.
- [File watcher](watcher.md): optional polling, exclusions, and observed-change limits.
- [Verification history](verification.md): dated checks and environment limitations; a historical record, not a fresh test result.
- [Host acceptance](host-acceptance.md): live integration checks with disposable fixtures.

## Optional agent integrations

- [Agent integration](agent-integration.md): explicit skill use and project initialization.
- [Reusable stash skill](../agent-skills/stash/SKILL.md): agent workflow and supporting references.
- [MCP bridge](mcp.md): project UUID binding, actual tool names, and conflict behavior.
- [Codex hooks](codex-integration.md): supported client version, installation, trust, diagnostics, and removal.

Integration references describe supported behavior and outstanding acceptance gates. Do not infer support for an untested client from a generic MCP configuration example.
