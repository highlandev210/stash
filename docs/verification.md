# Implementation verification

Date: 2026-10-03.

Project-owned `.stash/` storage is implemented behind the existing browser/CLI API. SQLite retains registry/settings and rebuildable cache; legacy record tables are used only for safe migration of the earlier version. Agent skill/MCP expansion remains deferred.

Completed checks:

- Frontend TypeScript check and production Vite build.
- Five frontend tests: registration, project-scoped docs, unavailable-server messaging, API conflicts, and preservation of the original revision across a background refresh.
- All 18 backend/API/CLI tests passed against real temporary project folders and SQLite registries. Coverage includes full workflow and restart, external metadata/issue/brief/handoff edits, hash conflicts, plain Markdown viewing, canonical registration, moves/re-registration/rebuilding a shelf, source-preserving removal, duplicate identities, symlink restrictions, history/idempotency, concurrent issue numbering, interrupted write/partial log recovery, recovery conflicts, legacy migration, migration conflicts, and relocation of unavailable legacy folders.
- ESLint has no errors; inherited Fast Refresh warnings remain in reusable UI components.
- Python compilation and Bash launch-script syntax checks.

Test-environment note: Starlette/AnyIO cross-thread event-loop wakeups stall in this sandbox even for a minimal unrelated FastAPI app. `STASH_TEST_POLL=1` enables a periodic loop wakeup in the test helper. It uses the actual Starlette client, worker threads, HTTP handlers, service layer, filesystem, and database; persistence/API responses are not mocked. Production code does not depend on this workaround.

```sh
STASH_TEST_POLL=1 .venv/bin/python -m pytest
npm run check
npm test
npm run build
```

Testing changes only temporary fixture projects, not the user's real project directories. Migration of real registrations occurs when the updated backend is restarted/used and their directories are accessible. Existing conflicting folder files are preserved with a visible migration error; missing folders keep pending legacy rows for retry.

Back up actual project memory by preserving each project's `.stash/` folder. The SQLite backup command now protects only the shelf registry/settings/cache and still-pending legacy data. Exports read current project-owned records.

Known scope limits: POSIX filesystem locks/directory-descriptor access require platform work before Windows packaging. Non-cooperating editor writes can still race in the brief interval between a final check and rename. Direct external edits don't automatically create attributed activity events. Corrupted/unsupported record files fail explicitly rather than being silently replaced.

## Session/checkpoint update (2026-10-03)

Completed attachment scope: session/checkpoint storage, read-only Git/fingerprint observations, backend/API/CLI operations with offline drafts, and Context resume/history/copy integration.

- All 25 backend tests passed, including seven new session tests. They cover Git and non-Git projects, subsequent edits to already-dirty files, branch/HEAD observations, index preservation, bounds/exclusions, cross-project isolation, content revision conflicts, duplicate request identities, checkpoint history, database reopen, interrupted and partially completed transactions, malformed external records, offline CLI draft/replay, safe draft paths, exports, activity record resolution, and context Markdown.
- All seven frontend tests passed, including two new resume/checkpoint tests for unfinished progress, verification, next action, subsequent changes, history, and revision-bearing checkpoint submissions.
- TypeScript, Vite production build, and Python compilation passed. ESLint: zero errors, six inherited Fast Refresh warnings. CLI entry-point help exposes start/list/show/checkpoint/replay/resume.
- Attempted a live HTTP/subprocess smoke run, but the sandbox rejected socket creation with `PermissionError` before a server was launched. Live socket/browser verification is therefore not claimed. API tests use actual FastAPI handlers and filesystem/database persistence through Starlette TestClient; CLI transport is redirected to that client.
- stash's own project folder now contains an implementation session and historical progress/final checkpoints. Its development notes describe the new workflow. Bootstrap used a temporary registry because the application's live server was unavailable; project-owned memory remains authoritative.

Scope limits: operations are explicit. Agent hooks, background watchers, automatic skill invocation, and browser draft persistence across restarts remain future work. CLI drafts are durable; replay captures repository observations at server receipt time. Repository observations are bounded scans, not atomic source snapshots.


## Skill and Codex adapter verification

34 backend tests pass. Acceptance covers repeated initialization preserving human fields, real CLI/API lifecycle calls, revision conflicts, actual Python compilation of a fixture, durable hook subprocess capture, concurrent deduplication, interrupted sessions remaining incomplete, offline queue recovery, safe event fields, binding, and installer preservation. These are executable contract tests, not an independent agent session.

Frontend tests (7), TypeScript checking, production build, and lint passed (six existing lint warnings). The skill passed the official quick validator using the installed JavaScript YAML parser as a dependency adapter: PyYAML was unavailable and network installation was blocked.

Installed Codex reports codex-cli 0.160.0 with hooks stable/enabled; the generated client schema and official hook documentation were inspected. Live client event emission and explicit skill/interruption gates are still unverified: protected agent configuration directories and unavailable server sockets prevent activation here. See codex-integration.md for the concrete host acceptance procedure. Earlier verification sections describe their historical scope.


## Watcher, MCP, and prepared host conditions

The optional watcher and project-scoped stdio MCP bridge are implemented. The watcher groups saved states without agents/Git, excludes generated/secret/dependency paths and symlinks, preserves baselines across moves/restarts, and distinguishes partial scans and file facts from semantic progress. MCP forwards context/issues/comments to the same API, preserves original issue revisions, deduplicates identical comment retries, and fixes attribution as an agent.

Verified suite before the additional watcher crash-recovery test: 40 backend tests and 8 frontend tests passed; TypeScript check and production build passed; lint passed with six inherited warnings and zero errors. Real MCP subprocess negotiation was tested; real client-to-HTTP integration is not claimed. The additional targeted checks are recorded in project memory with their actual results.

Prepared a disposable host fixture using `scripts/prepare_acceptance.py`; it contains human-written records, two unfinished sessions, no Git, hooks, a watcher baseline, a prompt, and isolated registry/start commands. Preparation succeeded. No live Codex interruption occurred here.

Git initialization was attempted and failed because `.git` is read-only. GitHub terminal authentication/API checks could not connect to api.github.com. The available GitHub connector is signed in to a different account; the user explicitly selected highlandev210 for publication. No repository was created or published, and no alternate account was substituted. Packaging is explicitly a README TODO, with contributions welcomed.

Final automated rerun for this change: **41 backend tests and 9 frontend tests passed**, TypeScript check/build passed, lint zero errors/six inherited warnings. Watcher journal crash recovery and browser original-revision draft preservation passed. The live gates and publication remain pending.

Host recheck: localhost socket creation is still denied, .git/.codex/.agents remain read-only, and the terminal GitHub API request still cannot connect. An authorized read-only Antigravity CLI probe was attempted in the disposable fixture with sandbox restrictions enabled; it terminated before starting a usable agent session because its language server could not bind a localhost socket. No cross-agent acceptance or live session was claimed.

## Elevated live host acceptance (2026-10-04)

Elevated host execution can bind localhost and access GitHub as highlandev210. Isolated live verification used a disposable fixture and registry on port 18764, preserving the existing port-8000 service.

Real Codex 0.160.0 client hook trust, SessionStart/tool event delivery, task intent, a non-final checkpoint, active-turn interruption, offline event queuing, server restart/draining and a fresh Codex-to-MCP resume read passed. The interrupted session remained incomplete and retained its verification/next action. Three offline events recovered without duplicate IDs. A live stdio MCP-to-HTTP workflow rejected a stale issue update, preserved the human change, retained human/agent comment attribution and deduplicated an identical comment retry. Repeated live CLI initialization preserved human metadata, README and project identity.

All 41 backend tests and 9 frontend tests passed again, along with TypeScript checking and production build. Lint: zero errors, six inherited warnings. No application implementation changes were made.

Follow-up live checks passed for abrupt termination during active work and relocation with pending observations. A real Codex client was killed during an observed active sleep command, leaving nine queued hook events and the previous non-final checkpoint intact. Moving the fixture preserved all queued payloads and the watcher baseline. The original-revision API path update preserved identity, issue and session history; recovery drained all pending events, with 34 accepted observations and 34 unique IDs.

Browser interaction remains unverified: no browser is connected to the current automation session. GitHub publication has not occurred because live browser acceptance is still pending. Detailed evidence and continuation information are in `.stash/docs/host-acceptance-progress.md`.

## stash rename and guided assessment (2026-10-05)

The app, Python packages/entry points, frontend branding, environment variables, storage paths and bundled agent skill now use **stash**. The previous Git metadata was moved outside this checkout; the new repository has origin `git@github.com:highlandev210/stash.git` and begins with fresh history.

Browser registration now opens initialization inside the existing workspace. New folders can be created, goals/requirements captured, existing repositories inspected, candidate context/issues reviewed, context corrected and agent semantic analysis imported. Reassessment preserves prior reports and records. Explicitly selected repository checks record outcome/exit-code evidence; inspection alone does not execute them. `stash init` now produces a reviewable assessment without requiring a metadata payload.

Acceptance atomically saves selected metadata, creates/links deduplicated issues, saves an initial unfinished checkpoint and establishes watcher configuration/baseline through the recovery journal. Stale source/Git/metadata/draft revisions are rejected, and repeat acceptance does not duplicate records. Legacy project memory is copied without modifying the original `.trackle/` records. The default shelf uses SQLite backup to preserve the prior database.

Fresh verification:

- 48 backend/API/CLI tests passed, including seven assessment tests covering existing/new projects, preservation/deduplication, tracking, stale drafts, explicit checks, semantic refinements, legacy migration, interrupted acceptance recovery and payload-free CLI initialization.
- 12 frontend tests passed, including three assessment interaction tests for user goals/requirements, preservation and issue review, conflicts and explicit check execution.
- TypeScript checking and production build passed. ESLint: zero errors and six existing Fast Refresh warnings.
- Python compilation, Bash launch syntax and the official skill validator passed.
- An isolated live localhost server served the built frontend, accepted an existing-project assessment and retained context/issues/checkpoint/tracking and assessment exports after a full server restart. Fixture: `/tmp/stash-live-smoke-jtpeiula`.

No browser is connected to this automation session, so full live browser interaction is not claimed. Browser behavior is covered by component interaction tests. Semantic repository understanding uses the external coding-agent refinement workflow; the built-in inspector provides bounded source/documentation evidence, manifest/Python syntax checks and reviewable source annotations. Standalone desktop packaging remains outside this change.
