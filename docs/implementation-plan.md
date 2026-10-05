# stash MVP implementation plan

Status: baseline implementation plan. Project storage has since changed to project-owned `.stash/` files; [folder-storage.md](folder-storage.md) supersedes the database ownership and removal descriptions below. The reusable skill, Codex adapter, optional watcher and project-scoped MCP bridge now have implementations; live host acceptance remains pending.

This is historical planning context. For the current product experience, see the [user guide](user-guide.md); for current architecture and contributor entry points, see the [development guide](development.md). stash's main workflow is browser use, with agent integrations optional.
Date: 2026-10-03.

## Product definition

stash is the existing app's name. ProjectShelf describes its product concept: a locally hosted project shelf for one human and their coding agents.

Primary workflow: open shelf → select project → read docs, manage issues, recover context → save progress. Retain one React front-end workspace with shelf and project states. Preserve the current visual language, responsive layout, sidebar, cards/list, five workspace tabs, issue detail sheet, and prominent latest handoff.

First real usage target: configure `/home/ben/Projects/HLD210`, discover immediate project directories, register `/home/ben/Projects/HLD210/vibe-wise`, read its actual README, save an issue and handoff, and retrieve the same information through the CLI after a server restart. Use temporary fixture projects for automated tests; never change the real project's files as a test.

## Current implementation and necessary changes

- `src/routes/index.tsx` contains the shelf and all workspace tabs in one component file. Split by feature while retaining one application shell.
- `src/lib/project-data.ts` supplies sample projects and a global sample issue list. Replace these imports with API queries; retain fixtures only for tests or an explicit demo mode.
- Shelf search, status filtering, sorting, view switching, and project selection work against sample data. Sidebar tags are hardcoded and do not implement real tag filtering. Recently opened has a fixed count.
- Add project and Settings are inactive. Empty-state buttons currently reset filters rather than register directories. Separate the unconfigured/empty shelf from an empty search result.
- Overview mixes selected-project fields with hardcoded commands, commit, handoff, and activity. Docs changes the selected filename but displays fixed content. Issues, Context, and Activity are not scoped to the selected project.
- Issue detail and context-copy patterns are reusable, but their data and actions must become real. Do not show acceptance criteria as checked without stored evidence.
- Current issue states are Open/In progress/Done and types are Feature/Bug/Chore. Use backlog, ready, in_progress, blocked, done, cancelled; types bug, task, feature. Display friendly labels separately from API values.
- Current runtime uses TanStack Start SSR and Nitro. Move to a client-rendered React + TypeScript + Vite app, retaining React Query and existing UI components. Remove Start/Nitro, server wrappers, and SSR-generated route plumbing when the client entry works. Routing may remain client-side, but shelf/project/tab transitions stay inside one workspace.
- Keep stash branding. Remove the placeholder user avatar unless it becomes a configurable local identity. Git/repository links must be optional. Replace the nonfunctional Open in editor action with Copy path for MVP. No shell execution endpoint.

## Architecture and ownership

Browser → `/api/v1` → FastAPI routers → shared services → SQLAlchemy/SQLite or restricted project filesystem access.

Typer CLI → HTTPX → the same `/api/v1` endpoints. The CLI requires a running server and never imports persistence code to write the database.

Development: Vite on `127.0.0.1:3000`, FastAPI on `127.0.0.1:8000`, with a Vite `/api` proxy. Production: FastAPI serves the compiled frontend and API from one localhost origin. API and static fallback paths must not intercept each other.

Suggested layout:

- `src/app/`: application shell and project/tab selection.
- `src/features/{shelf,overview,docs,issues,context,activity,settings}/`: views, forms, queries.
- `src/lib/api/`: API client, error handling, generated contract types.
- `backend/stash/{api,schemas,services,models,db}/`: Python backend.
- `backend/alembic/`: checked-in schema migrations.
- `backend/tests/`: API/service tests using temporary roots and database.
- `cli/stash_cli/`: Typer commands, HTTP client, output/error formatting.
- `agent-skills/stash/SKILL.md`: distributable agent workflow, authored in phase 5.
- `docs/`: setup, API/CLI usage, backup/restore, this plan.

Default app data lives outside tracked project repositories at `$XDG_DATA_HOME/stash/` or `~/.local/share/stash/`. Store `stash.db` and managed screenshot assets there. Permit an explicit database location for tests and portable installs. SQLite stores configuration and project metadata; do not create a second editable metadata file in registered projects.

Repository files remain authoritative for documents and source. Store configured doc-root paths and references, not duplicate editable document bodies, in SQLite. Git and filesystem observations are derived information with observation timestamps and explicit unavailable/error states.

## Data model and shared rules

Use UUIDs as stable internal IDs, UTC timestamps, foreign keys, migrations, and integer revisions on mutable records. Database transactions commit record changes and their activity events together. Enable SQLite foreign-key enforcement and configure bounded contention handling.

Core records:

- Settings: master folder, local display identity, supported preferences.
- Project: UUID, canonical absolute path (unique), name, description, purpose, status (active/paused/archived), focus, next step, setup/run/test command text, required services, environment-variable names, optional repo/demo URLs, screenshot reference, date added, last opened, revision.
- Project availability: available/missing/inaccessible, last check and reason. Separate availability from user project status.
- Tags and project/tag associations: distinguish user labels from stack tags; search and filter both deliberately.
- Documentation roots: project-relative read roots and approved writable roots. Root README readable by default; `docs/` writable by default if explicitly configured. Changing root README requires including it in permitted edit scope.
- Issue: UUID, project ID, immutable per-project issue number, title, type, description, status, priority, acceptance criteria, bug details, affected commit/version, creator identity/kind, timestamps, revision, completion verification evidence.
- Comment: issue/project relationship, body, identity/kind, timestamps, revision if editing is supported.
- Issue labels and typed links: relative file/doc paths plus optional line, commit references, or validated web URLs. Links do not grant filesystem permissions.
- Decision: choice, reasoning, alternatives, identity/kind, date, optional code/commit references. Preserve changes/history rather than silently replacing past reasoning.
- Handoff: append-only UUID, project ID, summary, completed work, changed files, verification/results, unresolved problems, blockers, next actions, identity/kind, timestamp, optional commit reference. A correction is another attributed record.
- Activity: project ID, actor name/kind, event type, record ID, timestamp, safe change summary. Do not log secrets or entire document contents.
- Derived observations: Git branch/latest commit/dirty state and bounded filesystem activity checks. Keep separate tracker_updated_at, code_activity_at, last_opened_at, and observed_at.

Shelf recent activity uses the newest known tracker or code timestamp and labels the source. Do not treat scanning or reading as code activity. Recently opened uses last_opened_at. Open issue count excludes done and cancelled. “Missing” does not delete issues, notes, or handoffs.

Actor identity is attribution for a single-user local tool, not authenticated proof. Browser defaults to the configured human identity; CLI can specify an agent name/kind.

## Registration and filesystem policy

1. Save/validate the master folder; enumerate only immediate candidate directories. Skip hidden/dependency/build/system directories; do not recursively discover nested projects.
2. Present candidates for selection with registered/new/inaccessible state. Discovery does not register every directory automatically.
3. Registration requires an accessible directory. Expand supported home notation, normalize the absolute path, resolve symlinks, and return the existing record on repeated registration. Enforce canonical-path uniqueness in the database to handle races.
4. Seed only a display name from the folder name. Offer detected stack/README suggestions for explicit adoption; rescans never replace user fields or recorded context.
5. External registration takes an absolute path and registers in place. A browser folder-upload picker is not a reliable way to obtain a host absolute path; MVP uses a path form with server validation and candidate selection.
6. Updating a moved path explicitly preserves the UUID and records, validates the new location, and rejects conflicts with another registration. Do not infer moves automatically.
7. Rescan refreshes availability and observations, leaving user content intact. Missing master folders produce a clear error without unregistering projects.
8. Removal confirms “Remove from shelf; project files stay on disk.” Remove tracker records with a clear export option and transactional relationships; never delete source directories. Archive is the retention alternative.
9. Authorize every file operation against the selected registered project and doc roots after canonical resolution. Reject traversal, escaping symlinks, secret files, unsupported file types, and oversized reads. Recheck write targets; use safe atomic replacement and account for filesystem races.
10. Ignore `.git` internals, dependency folders, build outputs, `.env` variants, credentials, key files, and configured exclusions in document/observation scans. Do not execute repository code or parse secrets to infer configuration.

## UI adapted to the existing design

### Shelf and Settings

Keep header search/Add project, collapsible status/tag sidebar, sort selector, and grid/list controls. Add a small master-folder/rescan area in Settings and onboarding. Add project opens a dialog for master-folder candidates or external path. Cards retain description, status, tags, issue count, next step, and activity; replace synthetic previews with an optional screenshot or neutral project placeholder. Provide edit, update path, archive, export, and remove actions through a real accessible menu rather than a decorative ellipsis.

Separate initial onboarding, registered-but-missing, loading, unavailable server, failed scan, and no search matches. Counts come from stored records. Preserve shelf filters and scroll position when returning from a project.

### Overview

Retain the wide project/continuation column and narrower local-development/details column. Populate everything per project. Add Edit project for metadata and command text. Show purpose, current focus, next action, actual latest handoff, optional screenshot/links, Git availability and observation time. Make command rows copyable; never executable. Show service requirements and environment-variable names without values. Copy path remains available for missing projects.

### Docs

Keep file tree + article layout. Load real relative paths and Markdown; View source toggles the actual source. Add New document/Edit/Save within writable roots. Sanitize rendering and URL schemes; disable raw HTML by default. Relative document links resolve through approved roots; disallowed assets are not fetched.

Read responses include a content revision/hash. Updates require the expected revision; creation requires the file not to exist. External modification returns a conflict without writing. Keep the user's draft and offer reload/compare/reapply. Missing files remain explicitly identified, rather than falling back to a different document. Refresh/on-focus checks are sufficient for MVP; filesystem watchers are optional later.

### Issues

Keep the list and right-side detail sheet. Add New issue, editable fields, comments, labels, typed references, bug-specific fields, and completion evidence. Filters cover status/type/priority/labels and text. Fix mobile rows to show the title. Hide the board toggle for MVP; no need to implement drag and drop. Acceptance criteria are unverified unless individually recorded or supported by explicit verification.

### Context

Keep Continue from here and Copy agent context as the primary actions. Add brief/focus editing, Record decision, Save handoff, and readable history. Include actual timestamps, identity, changed files, commits, evidence, blockers, and next actions. Brief export includes the project/path, recorded focus, relevant unresolved issues, decisions, latest handoff, freshness references, and instruction to inspect code. If no handoff exists, show that honestly and use recorded next step. Never invent verification.

### Activity

Reuse the human/agent timeline. Populate tracker events and link to affected records using current workspace state. Filters cover actor/type/date. Display current Git observations separately in Overview; do not imply the tracker captured every commit. Viewing a record should not manufacture a work event.

## API contracts

Version the API under `/api/v1`. Generate or validate frontend types against FastAPI OpenAPI. List endpoints support bounded pagination and deterministic ordering. Use a consistent error shape with code, message, field details, and safe conflict metadata.

Endpoint groups:

- Health and settings: server readiness, get/update settings, discover/rescan master-folder candidates.
- Projects: register, list/search/filter/sort, get/update, update path, remove, record opened, refresh observations.
- Docs: tree, read/source, create, revision-checked update.
- Issues: create/list/get/update, comments, labels, links, verification.
- Context: brief get/update, decisions create/list, handoffs create/list/get, Markdown agent context.
- Activity: paginated event list and filters.
- Export: project JSON and rendered Markdown records; no secret files or repository copy.
- Resolution: canonical current-directory lookup, returning the most-specific containing registered project; explicit ID resolves ambiguity.

Expected errors: 404 missing record/file, 409 revision/path conflict, 422 invalid input/path, bounded filesystem errors without stack traces. Distinguish absent Git from failure reading Git. Require expected revisions for updates and support request idempotency keys for retried handoff/comment/decision creates. Canonical registration is inherently idempotent.

## Local security and durability

Build these into the relevant feature, rather than postponing all hardening to the last phase:

- Bind to loopback, validate Host and exact permitted browser origins, reject cross-origin mutations, and restrict CORS. Browser mutations use JSON and explicit origin validation; CLI requests without browser Origin remain supported. Do not accept arbitrary origins or bind to all interfaces by default.
- Limit all reads/writes to registered roots; registration itself is an explicit user/CLI action. No unrestricted filesystem browser or arbitrary download endpoint.
- Escape user text, sanitize Markdown, reject dangerous URL schemes, and avoid secret values in records and errors.
- Optimistic concurrency from the first editable API. File hash/revision checks from the first document editor.
- Treat Git inspection as bounded, read-only subprocess work with argument arrays, fixed operations, timeouts, and repository-owned executable hooks disabled where relevant. Never run user commands.
- Use transactions, stable IDs, append-only handoffs, migration checks, and safe backup/restore. Back up a live database through SQLite's backup mechanism rather than blindly copying its file; include referenced managed screenshot assets.

## Delivery sequence and gates

### Phase 1 — Real registration, persistence, and shelf

Build Python package, FastAPI health/settings, initial Alembic migration, registration/discovery services, and project APIs. Convert the frontend to Vite client rendering, split its shell/shelf, and connect React Query. Implement registration dialog, master-folder settings, dynamic counts/tags, filtering/sorting, editable metadata, availability, path updates, and safe removal.

Gate: register a temporary master-folder project plus an external project; canonical/symlink registration produces one UUID; rename/move path without losing identity; missing directories remain listed; rescan preserves description; restart retains data; source files are untouched.

### Phase 2 — Useful overview and documentation reading

Bind overview to selected-project data; add metadata forms and copyable commands. Implement safe document tree/read/source, sanitized Markdown, optional Git inspection and observation states. Ship read-only docs first; then implement bounded revision-checked document creation/editing before calling Docs complete.

Gate: selecting two different fixture projects shows their own docs/commands/Git state; a non-Git project works; traversal/secrets/escaping symlinks are rejected; stale saves preserve both external changes and the user's draft.

### Phase 3 — Issues and comments

Add issue/comment/label/link models and migration; implement service rules, APIs, new-issue form and editable detail sheet. Add all six statuses, filters, bug details, acceptance criteria, and verification evidence. Commit activity events with each change.

Gate: create a bug, add comment and file reference, progress it to done with actual evidence, reload/restart, and verify no records leak between projects; stale edits return 409.

### Phase 4 — Context, handoffs, decisions, and activity

Implement decisions, append-only handoffs, project brief/focus, server-rendered Markdown context, activity pagination/filtering and linked records. Connect the prominent continuation panel and historical detail views.

Gate: two attributed sessions retain both handoffs; latest is prominent; copied context identifies a concrete next action and timestamps; unperformed tests are labelled unverified; interrupted work still retains earlier issue/decision updates.

### Phase 5 — CLI and coding-agent workflow

Package Typer/HTTPX commands: `stash register PATH`, `projects list`, `context`, `issues create/list/update`, `decisions add`, and `handoffs add`. Shared options: server URL, project ID, actor name/kind, JSON output. Resolve current directory through the API, including nested directories. Use file/stdin payloads for structured handoffs and multiline text.

Define exit codes: 0 success, 1 operation/server failure, 2 invalid usage, 3 unresolved project, 4 conflict. JSON failures use a stable structured error, stdout carries machine-readable results, and human diagnostics go to stderr. Time out unavailable servers with an actionable message.

Author the coding-agent skill using the appropriate skill-creation workflow at implementation time. Provide an opt-in AGENTS.md snippet explaining when to invoke it. Do not silently edit every registered project's AGENTS.md or imply automatic execution. Skill steps cover repository inspection, context reading, issue/decision updates, checkpoints, and truthful final handoffs.

Gate: CLI and browser retrieve the same records; a new agent can resolve a fixture project, read its brief, update an issue, and save a handoff; explicit ID and unavailable-server paths behave predictably.

### Phase 6 — Export, backup, packaging, and release checks

Finish JSON/Markdown export, database backup/restore, managed asset handling, migration upgrades, startup scripts, single-process production serving, and setup instructions. Run cross-feature reliability/security tests established in earlier phases. Package one documented local launch flow plus the CLI; no cloud account required.

Gate: fresh install and restart pass all eight original MVP acceptance scenarios. Export preserves issues/comments/decisions/handoff history and IDs; restore recovers relationships. Registration/removal never moves, copies, or deletes source. Commands are displayed only. No hosted-editor runtime dependency or integration is introduced.

## Testing and scope control

Use service/API tests with temporary databases and directories for path normalization, missing paths, uniqueness, scanning exclusions, revisions, atomic changes/activity, doc conflicts, and project scoping. Test real migrations and backup/restore. Add frontend interaction tests for registration, selection, issue edits, conflicts, and context copy; one end-to-end workflow covers browser + CLI + restart. Mock Git failure states where needed and use a temporary actual Git repository for basic inspection.

First checkpoint is phase 1 plus read-only README access from phase 2: an existing real folder becomes a persistent shelf entry with meaningful content. Then extend that same workflow rather than polishing disconnected placeholder tabs.

Defer board drag-and-drop, automatic editor launching, shell execution, GitHub sync, watchers, embedded AI, MCP, cloud accounts, team permissions, vector search, and chat transcript storage. Avoid invented data, automatic summaries, recursive discovery, and duplicate metadata files.

Planning defaults: keep stash branding; one configured master folder; manual candidate selection; explicit path form; one central local SQLite database; frontend development port 3000; production served by FastAPI. Optional integrations are reconsidered only after the vertical workflow is usable.
