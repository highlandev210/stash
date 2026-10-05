# Project-owned stash memory

stash's project records live in each project's `.stash/` folder. The browser and CLI use the same API to read/edit those files. An editor can read them without stash running. Existing README and repository documentation are referenced in place.

```text
.stash/
├── project.json                 # Stable UUID, format version, metadata, commands, focus, next step
├── docs/
│   └── brief.md                 # Authoritative project brief; not duplicated in project.json
├── issues/
│   └── <issue-uuid>.json         # Structured issue fields, labels, links, verification
├── comments/
│   └── <comment-uuid>.json       # Issue reference, text, attribution, timestamp
├── decisions/
│   └── <decision-uuid>.md        # Readable decision with machine-readable identity header
├── handoffs/
│   └── <handoff-uuid>.md         # Historical session handoff
└── activity.jsonl               # Append-only, attributed tracker events
```

The folder also contains `.lock` and may temporarily contain `.transaction.json`. These support safe writes and recovery; they are not additional editable sources of project metadata. Do not manually modify either file. If committing project memory to Git, ignore `.stash/.lock`, `.stash/.transaction.json`, and `.stash/**/.write-*`. These rules are guidance; stash does not modify your Git ignore files automatically.

## Source of truth

- `project.json` holds `schema_version: 1`, a stable UUID `id`, `created_at`, `updated_at`, and structured metadata: name, description, purpose, status, tags, stack, focus, next_step, command text, services, environment-variable names, optional links/screenshot path, and permitted document paths.
- `docs/brief.md` holds the brief. The API combines these sources for the existing frontend without maintaining another editable copy.
- Issues and comments are JSON objects. Decisions/handoffs use Markdown sections with a JSON identity header in an HTML comment.
- Absolute host paths are not stored in project.json. They belong to the local shelf registry, so a folder can move between computers.
- SQLite retains settings, project ID/location registrations, last-opened timestamps, observations, and a rebuildable last-known shelf summary. The summary is a cache, never a write target for project edits. It supports showing unavailable projects; full history requires the project folder to be available.
- Direct file edits are visible on the next API read/browser refresh. They change revision tokens even if the editor doesn't update timestamps or any revision field. Browser queries refresh on focus; Docs also periodically checks the selected document.

## Human editing

Edit descriptions/commands/tags in `project.json` and keep its UUID, schema version, and required field types intact. Put prose in `docs/brief.md`. Edit an issue's fields in its JSON file, retaining its identity, project_id, number, creator, and timestamps.

A decision/handoff starts with a `<!-- stash-record ... -->` JSON header containing identity, project reference, kind, actor, timestamp, optional issue reference, and request key. Each prose field has a readable heading enclosed by `<!-- stash-field:FIELD -->` and `<!-- /stash-field -->`. Edit the text inside the sections; retain the markers/header so stash can map it back to the UI. Ordinary Markdown headings inside the prose are supported. Section markers are reserved syntax.

Handoffs created through stash remain historical records; corrections are new handoffs. Directly editing a historical file changes the record visible in the app, so Git is useful if you want a version history of manual edits. Manual file edits do not fabricate a human/agent activity event; attributed events are recorded for API/CLI writes.

## Conflict and recovery behavior

Project revisions hash both project.json and brief.md. Issue revisions hash the entire issue file. Clients must echo the revision they originally read. A mismatch returns HTTP 409 without replacing the external edit.

stash serializes its own project writes with a folder lock. Multi-file updates use an fsynced journal, atomic file replacement, and a matching activity append. A subsequent read recovers interrupted writes. Recovery verifies the original/current hashes before proceeding and can complete a known partial final activity line without rewriting earlier history. Unexpected external edits during recovery retain the journal and return a conflict rather than overwriting them.

Locks coordinate stash writers; ordinary editors do not share them. There remains a narrow check/rename race with non-cooperating external writers, as in typical editor saves. Avoid simultaneous saves to the same file and inspect Git when reconciling conflicts.

Symlinks inside tracker storage are rejected. Tracker-document access is explicitly limited to `.stash/docs`, `.stash/decisions`, and `.stash/handoffs`; metadata, comments, issues, the lock, and recovery journal are not exposed through a generic filesystem endpoint. Decisions/handoffs are read-only through Docs. Existing repository Markdown retains its configured read/write scopes and secret/dependency exclusions.

## Registration, removal, and movement

Registration creates initial memory for a new project or reads an existing folder's project.json and stable ID. It never moves/copies source. Re-registering a canonical path is idempotent. Removing from the shelf removes only its registration: `.stash/`, issues, docs, and history stay intact.

After moving the whole project folder, register the new path or update the old registration's path. Its stable ID and records are retained. If two simultaneously available directories have the same project ID, registration rejects the duplicate. For a deliberately independent clone, assign a new project identity and update the record project references; a guided clone feature is not included yet.

A fresh stash installation can register a project with an existing `.stash/` and show its records without importing a database.

## Migration of the earlier SQLite version

The database schema adds a registry table while retaining old tables only for pending migration. API startup/use attempts migration of accessible legacy registrations. IDs, issue numbers, creator attribution, comments, decisions, handoffs, and events are written into `.stash/` and checked before the corresponding old database rows are removed. Successful migrations leave no active database copies of those project records.

Missing/inaccessible folders or conflicting `.stash/` files retain the old rows for retry and display migration/storage errors. Existing conflicting files are not overwritten. Restore the directory/path or resolve the conflicting folder records before migration can finish. A stale browser form from the old version must reload because revisions are now content hashes.

## Backup and export

Back up each entire project folder including `.stash/` (or commit its records to Git). This is what preserves its project memory. A SQLite backup preserves shelf locations/settings/cache and any still-pending legacy migration data, not the folder's current records. JSON/Markdown exports remain available through Overview and read current authoritative files.

The reusable skill, optional Codex hooks, file watcher, and project-scoped MCP bridge all use the same storage/API rules. Opening the website does not launch a coding agent. See agent-integration.md, codex-integration.md, watcher.md, and mcp.md.
