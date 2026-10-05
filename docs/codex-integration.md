# Codex integration

The adapter targets the verified installed **codex-cli 0.160.0**. Installation rejects other versions rather than assuming compatible events. This client exposes stable hooks; its configuration schema supports SessionStart, PostToolUse, Stop, Interrupt, and SessionEnd.

## Install and activate

Install stash's backend/CLI, start its server, register the project, then run from the project directory:

```sh
stash integrations codex install --path .
stash integrations codex status --path .
```

The installer copies the reusable skill into `.agents/skills/stash`, adds handlers to `.codex/hooks.json`, and enables `.stash/runtime/codex/config.json`. It preserves unrelated hook handlers and refuses to overwrite customized skill files. Use `--no-skill` if the skill is already installed elsewhere. The executable's Python environment must remain available.

**Review and trust the hooks in Codex using `/hooks`.** Writing configuration does not grant client trust. See [Codex hooks documentation](https://learn.chatgpt.com/docs/hooks). Restart/open a project session after installation and invoke `$stash` explicitly for initialization or resumption. Add the instruction snippet from `agent-skills/stash/assets/AGENTS.snippet.md` to the project's instructions when desired; the installer does not edit AGENTS.md.

## What is recorded

SessionStart binds the hashed Codex session identity to a stable stash session. Its context tells the agent which session to use; the skill records the actual task with a revision check. An explicit existing session can be bound with:

```sh
stash integrations codex bind RUNTIME_KEY --session SESSION_UUID
```

Hooks synchronously persist small local outbox events, then launch a detached delivery worker. They perform no network requests or repository inspection on the capture path. The worker sends through the same API as the CLI. The running backend also sweeps registered project outboxes, allowing recovery after agent shutdown.

Observations contain event type, time, hashed identifiers, broad tool category, and structured exit/error facts when available. Commands, prompts, tool output, transcripts, and secret values are not captured. Unstructured results have unknown exit status. Stop and Interrupt never mark work complete. Written checkpoints remain separate and require the agent to describe actual work and verification.

Generic hook-created sessions do not replace meaningful earlier resume context. Context displays observations separately from written progress.

## Recovery and removal

Operational files live in `.stash/runtime/codex/`: bindings, outbox, receipts, worker status, and configuration. Authoritative accepted observations live in `.stash/observations/`; sessions/checkpoints remain in `.stash/sessions/`. Pending events survive outages. Persisted event IDs and server comparison make retries idempotent; conflicting payloads are retained with an error rather than overwritten.

```sh
stash integrations codex status --path .
stash integrations codex drain --path .
stash integrations codex observations
stash integrations codex uninstall --path .
```

Uninstall disables capture/delivery and removes only stash's handlers. It preserves the skill, pending events, and project history. Reinstall to resume queued delivery. Delivery uses loopback HTTP only. CLI semantic checkpoints can separately use the documented offline drafts/replay workflow.

## Acceptance on a normal host

Automated tests execute the hook command in subprocesses with provider-shaped inputs, recover durable events after process exit/outages, exercise concurrent duplicate capture, and verify that interruption leaves sessions incomplete. They do not prove that the real Codex client emits the expected events.

For the remaining live gate: install and trust the hooks, explicitly invoke the skill, record task intent and a checkpoint, run a harmless edit/check, then interrupt the active turn. Close Codex abruptly, restart stash, and check integration status, observed events, and `stash --json context`. Resume in a fresh session. Confirm the prior next action and verification remain readable, pending events drain once, and interruption did not create a final checkpoint. Repeat initialization after adding human-written metadata and notes and confirm they remain unchanged.

The development sandbox cannot write the project's protected `.codex`/`.agents` directories or open server sockets. Actual client emission, trust activation, and live interruption acceptance therefore remain host verification tasks; they are not reported as passing.
