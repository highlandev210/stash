# Development and codebase guide

Read the [user guide](user-guide.md) first to understand the product: stash is a local browser app with a project shelf and five project tabs. Agent tooling extends that app; it is not a prerequisite for using it.

## Architecture

One React frontend holds shelf and project state. `src/app/App.tsx` keeps the shelf mounted while a project is open, preserving its navigation state. `Workspace.tsx` selects Overview, Docs, Issues, Context, and Activity. Keep this as one frontend workspace, as required by [AGENTS.md](../AGENTS.md).

Browser requests go through `src/lib/api/client.ts` to FastAPI's `/api/v1` endpoints. The Typer CLI uses HTTPX against the same API. The stdio MCP bridge also forwards HTTP requests. These clients do not independently write project records.

FastAPI handlers validate requests and call backend services. Authoritative project records live in each project's `.stash/` folder; SQLite stores settings, location registrations, observations, and shelf caches. Legacy SQL record tables remain for migration, not as another current editable store. See [folder storage](folder-storage.md) for ownership and recovery behavior.

Development uses Vite on localhost port 3000, proxying `/api` to FastAPI on port 8000. A built installation uses FastAPI on port 8000 for both API and frontend. The default frontend directory is `dist` relative to the server's working directory; `STASH_FRONTEND` overrides it.

## Source map

- `src/main.tsx`, `src/app/App.tsx`: frontend entry and shelf/project state.
- `src/features/Shelf.tsx`, `Workspace.tsx`: registration, discovery, and navigation.
- `src/features/Overview.tsx`, `Docs.tsx`, `Issues.tsx`, `Context.tsx`, `Activity.tsx`: the five tabs.
- `src/features/SessionResume.tsx`, `FileWatcher.tsx`: checkpoints, resuming work, and watcher UI.
- `src/app/shared.tsx`, `src/lib/api/client.ts`: shared forms, errors, API types, and requests.
- `src/components/ui/`, `src/styles.css`: UI primitives and styling.
- `backend/stash/main.py`, `api.py`: localhost server entry and HTTP routes.
- `backend/stash/assessments.py`, `src/features/Assessment.tsx`: onboarding, semantic refinements, review and reassessment.
- `backend/stash/legacy.py`: non-destructive name migration.
- `backend/stash/schemas.py`: request validation and record contracts.
- `backend/stash/services.py`, `store.py`: domain operations, folder records, revisions, and transactions.
- `backend/stash/filesystem.py`: bounded file access and path restrictions.
- `backend/stash/db.py`, `models.py`, `migrations/`: SQLite registry and migrations.
- `backend/stash/sessions.py`, `observations.py`, `watcher.py`: sessions, repository observations, and polling.
- `backend/stash/codex_*.py`, `mcp_server.py`: optional integration runtime.
- `cli/stash_cli/`: CLI commands, payload handling, integrations, and offline drafts.
- `agent-skills/stash/`: reusable agent workflow and references.
- `backend/tests/`, `src/test/`: backend/CLI/integration and browser component tests.
- `scripts/`: setup, development launch, and acceptance-fixture preparation.
- `pyproject.toml`, `package.json`: package entry points, dependencies, and frontend scripts.

## Set up development

Requirements: Node.js 22.12+ with npm, Python 3.10+, and uv.

```bash
cd /path/to/stash
bash scripts/setup.sh
bash scripts/dev.sh
```

Open **http://127.0.0.1:3000**. The launcher starts both services and stops them when it exits. API documentation is at **http://127.0.0.1:8000/docs**.

Without uv, use Python's venv and pip instead of the setup script:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
npm ci
bash scripts/dev.sh
```

Your OS may need a separate Python venv package. To run the built app, stop the development services, run `npm run build`, then `npm start` from the checkout.

The checkout CLI is `.venv/bin/stash`; it requires a running API server. From another project, call it by absolute path. A shell alias only affects shells that load it and does not expose a command to all agent subprocesses. Use [systemwide installation](systemwide-install.md) when that is needed.

## Working rules for people and agents

Before editing a feature, read its frontend component, API handler, schemas, and service/storage operation. Check the relevant technical reference and existing tests. The code defines current behavior; [implementation-plan.md](implementation-plan.md) is historical design context, not a complete current specification.

- Keep shelf/project navigation in one frontend workspace.
- Preserve project-owned records, stable IDs, original revision tokens, and historical attribution.
- An outdated update must report a conflict. Do not silently fetch a newer revision and overwrite someone else's edits.
- Distinguish observed file/tool changes from written explanations, actual verification, and completion.
- Use disposable project folders and databases for tests. Do not register or mutate a user's real project as a test.
- Keep secrets out of notes, logs, and fixtures. Stored environment fields contain names, not values.
- Keep ordinary app flows usable without agent setup. Read integration references before changing optional hooks or MCP behavior.

For scripts and agents, inspect `.venv/bin/stash --help` and subcommand help. `sessions checkpoint SESSION_ID` takes a `--file` JSON payload with the original session revision; it does not accept summary/next/final shortcut flags. The [session reference](session-checkpoints.md) documents payloads and replay. MCP binds a registered project UUID, not a folder path; use the exact tools in the [MCP reference](mcp.md).

## Validate changes

Run checks appropriate to the change. The full standard set is:

```bash
.venv/bin/python -m pytest
npm run check
npm test
npm run lint
npm run build
```

If the test environment has the documented cross-thread event-loop stall, run backend tests with `STASH_TEST_POLL=1`; see [verification history](verification.md). Historical test counts are not current results. Report commands actually run and any failures or untested host behavior.

Live hook trust, interruption, and client compatibility require the disposable [host acceptance workflow](host-acceptance.md). Synthetic event tests alone do not establish those results. Linux/POSIX is the current target; standalone packaging and other platforms remain work to verify.

## Runtime settings

- `STASH_FRONTEND`: built-frontend directory when starting outside the checkout; use an absolute path.
- `STASH_DATA_DIR`: shelf data directory; otherwise derived from `XDG_DATA_HOME` or `~/.local/share`.
- `STASH_DB`: explicit SQLite path, useful for isolated fixtures.

These settings do not relocate project-owned `.stash/` records. Never point a test server at your normal shelf database.
