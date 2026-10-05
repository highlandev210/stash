# Session and checkpoint commands

```sh
stash --json context
stash --json sessions list
stash --json sessions show SESSION_UUID
stash --actor Codex --kind agent --json sessions start "Actual task"
```

Start returns a `result` session and a durable request draft path. The session has a stable ID and content-hash revision. `sessions show` returns `{session, checkpoints}`.

For a hook-created session, write a task payload:

```json
{"revision":"SESSION_REVISION_ORIGINALLY_READ","task":"Actual task agreed with the user"}
```

```sh
stash --actor Codex --kind agent --json sessions task SESSION_UUID --file /tmp/intent.json
```

A task update changes the session revision. Read it again before checkpointing.

Checkpoint payload:

```json
{
  "revision": "SESSION_REVISION_ORIGINALLY_READ",
  "progress": "What actually changed",
  "unfinished_work": "Work still remaining",
  "blockers": "",
  "verification": "Actual command/check and result; include failed/unperformed checks",
  "verification_includes_uncommitted": null,
  "next_actions": "Concrete next action and relevant code reference",
  "final": false
}
```

```sh
stash --actor Codex --kind agent --json sessions checkpoint SESSION_UUID --file /tmp/checkpoint.json
```

The CLI supplies a request UUID if omitted. For a deliberate final handoff, set `final: true`; that completes the session, not all project issues. Start a new session for subsequent work.

If the server was unavailable, use the exact draft path reported by the failed start/checkpoint command:

```sh
stash --json sessions replay .stash/drafts/REQUEST_UUID.json
stash --json integrations codex status
stash --json integrations codex drain
```

Replay uses the original actor/payload and must target the original server. Git observations are captured at receipt time, not reconstructed historically. A repeated matching ID is idempotent. Changed content needs a new ID after rereading/reconciling; stale revisions must not be silently replaced.

Issue examples:

```sh
stash --actor Codex --kind agent --json issues create "Observed problem" --type bug
stash --actor Codex --kind agent --json issues update ISSUE_UUID --status in_progress
stash --actor Codex --kind agent --json issues comment ISSUE_UUID "Observed blocker and next action"
stash --actor Codex --kind agent --json decisions add "Actual choice" --reasoning "Why" --alternatives "Considered options" --reference "path:line or actual commit"
```

Detailed issue updates require the original revision. Inspect `stash issues update --help` for the supported payload and verification option. Only mark an issue done when its criteria and verification support it.
