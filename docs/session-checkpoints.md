# Git-aware session checkpoints

stash records task intent and progress before a final handoff exists. These operations are explicit: no agent hook, timer, watcher, or automatic skill invocation is installed by this feature.

## Ownership and durability

Each project stores:

```text
.stash/
  sessions/<session UUID>/
    session.json
    checkpoints/<checkpoint UUID>.json
  drafts/<request UUID>.json
```

`session.json` contains stable session/project IDs, schema version, actor, start time, task intent, initial observation, status, and latest checkpoint ID. It has a content-hash revision. Checkpoint files preserve creation time, attribution, the original session revision, written explanations, and a separate repository observation. Checkpoints are append-only through the API. A final checkpoint acts as the session's final handoff; ordinary handoffs remain separate historical records.

A session remains `incomplete` until an explicit checkpoint with `final: true` is saved. Closing an app does not establish completion. A final checkpoint does not automatically resolve issues, execute tests, or commit code. Start a new session for further work after completion.

Folder locks, original-content checks, atomic replacements and the existing recovery journal coordinate the checkpoint, session pointer, and activity event. Restart/read recovers interrupted transactions. Do not manually edit recovery journals. External changes that conflict with a pending write are preserved and reported.

## Browser workflow

Open a project's Context tab. Use **Start session** to record the task before edits, and **Save checkpoint** throughout work. Record actual verification results and concrete next actions. Choose whether verification included uncommitted changes; leave it unrecorded if unknown. Select a final handoff only when the session's work is concluded.

The resume panel shows the latest active record by session activity, unfinished status, progress, blockers, verification, and changed files since its checkpoint (or since task intent if there is no checkpoint). Multiple unfinished sessions remain visible in history and can receive their own checkpoints. **Refresh observations** compares the repository again. **Copy agent context** includes the session/checkpoint IDs, timestamps, next action, verification, Git references and subsequent changes. History and activity links expose older records.

The browser retains a form draft while the panel remains open after a failed save. Persisting offline requests across browser restarts is not implemented; the CLI provides durable offline drafts.

## CLI workflow

Global flags precede subcommands. Run from the registered project directory, or pass an explicit `--project UUID`.

```sh
stash --actor Codex --kind agent --json sessions start "Implement issue filtering"
stash --json sessions list
stash --json sessions show SESSION_UUID
stash --json sessions resume
```

Use the revision returned by `sessions show` in a checkpoint payload:

```json
{
  "revision": "SESSION_CONTENT_HASH_ORIGINALLY_READ",
  "progress": "Added filter controls",
  "unfinished_work": "Backend filtering and tests remain",
  "blockers": "",
  "verification": "TypeScript passed; backend tests not run",
  "verification_includes_uncommitted": true,
  "next_actions": "Implement backend filtering and test it",
  "final": false
}
```

```sh
stash --actor Codex --kind agent --json sessions checkpoint SESSION_UUID --file /tmp/checkpoint.json
```

The CLI supplies a checkpoint UUID if omitted. You may supply an `id` to keep a request identity across retries. `sessions start` accepts `--id UUID`. Both mutations accept `--draft /absolute/path/request.json`; the default is `.stash/drafts/<request UUID>.json` under the current directory. For calls from elsewhere with an explicit project ID, choose a draft location explicitly.

Every mutation draft is atomically written and fsynced **before any HTTP operation**, including project resolution. Drafts contain the intended actor, operation, target path/ID, server, payload, and stable request ID. They contain no source file bodies. Treat explanation text like all project context: never enter secret values. Successful requests retain their draft as a replayable receipt.

On an unavailable server, exit code 1 and JSON/human diagnostics identify the draft. Start the server, register the project if needed, then replay:

```sh
stash --json sessions replay .stash/drafts/REQUEST_UUID.json
```

Replay must use the original `--server`. It preserves the original actor and payload. A repeated matching request returns the existing record without another event or observation. A reused ID with different content, or a genuinely stale session revision on an unsaved checkpoint, returns a conflict (exit code 4). Read the current session and reconcile before writing a new request ID; the old draft remains available. Invalid inputs use exit code 2.

Offline replay's repository observation is captured when the backend receives the request, not retrospectively at the time the draft was authored. Verification scope is an explicit recorded claim, not automatic proof that tests ran.

## Read-only Git and file observations

At task intent and each checkpoint, stash captures branch, HEAD (including detached/unborn cases), porcelain status and changed paths. It uses read-only Git commands with optional Git locks disabled. Projects without Git still receive filesystem fingerprints. Projects inside a parent Git worktree use that worktree's branch/HEAD and project-scoped status.

Fingerprints contain SHA-256 hashes and project-relative paths, not file bodies. They detect further edits to already-modified files and filesystem changes when Git is absent. `.stash/`, hidden files (including `.env`), known secret filenames/extensions, dependency directories, build output, and symlinks are excluded. Git dirty status can still reflect excluded changes; the displayed path list intentionally omits them. stash does not change `.gitignore` or auto-commit notes.

Observation limits: at most 5,000 fingerprints, 2 MB per file, 50 MB content total, and approximately 250 KB fingerprint metadata. Omitted/inaccessible files produce a partial-observation warning; excluded paths are outside the comparison scope. Git commands have timeouts. An observation is a bounded scan, not an atomic snapshot of simultaneously changing source files. Inspect current code before treating a checkpoint as fresh.

## API

All routes are under `/api/v1/projects/{project_id}`:

- `POST /sessions`: task intent (`id`, `task`, `actor`).
- `GET /sessions`: sessions ordered by recent recorded session activity.
- `GET /sessions/{session_id}`: session revision and full checkpoint history.
- `POST /sessions/{session_id}/checkpoints`: revision-checked checkpoint (`id`, `revision`, explanations, `actor`).
- `GET /resume`: latest checkpoint and current repository comparison, plus unfinished sessions.
- `GET /context`: same resume information and concise Markdown brief.

Project exports include sessions and historical checkpoints (format version 4, including accepted agent observations). SQLite keeps no editable session copy. Back up `.stash/` alongside the repository. Session/checkpoint JSON is accessed through Context and CLI; the Docs tab remains focused on Markdown development notes.

## Verification evidence

See `docs/verification.md`. Session/backend tests are in `backend/tests/test_sessions.py`; UI tests are in `src/test/session-resume.test.tsx`. The tests exercise persisted files, revision conflicts, idempotent offline replay, restart recovery, Git and non-Git observations, resume content, and history. Live socket verification was blocked by the current sandbox, which forbids socket creation.
