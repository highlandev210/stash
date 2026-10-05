---
name: stash
description: Assess and initialize a repository's stash development notes or explicitly use stash to resume and record project work, issues, decisions, checkpoints, and handoffs. Use when the user requests stash project memory or project instructions call for it; requires the stash CLI and local server for accepted records.
---

# stash project memory

Each project owns its metadata and history in `.stash/`; SQLite holds the shelf registry/settings and derived cache. Markdown development notes live in `.stash/docs/`. Repository README/product docs are separate. Preserve both, and link existing repository documentation rather than copying it into a competing source of truth.

Use the CLI/API for structured records, identity, validation and attributed history. Edit Markdown development notes with original-content checks. Never write SQLite or hand-edit structured historical records. Use a working stash executable on PATH, or the executable path supplied by the user. Global `--actor`, `--kind`, `--project`, `--server`, and `--json` flags precede subcommands. Attribute writes as the actual agent, not the human.

## Initialize

Read [initialization](references/initialize.md) for new projects, existing repositories, or reassessment. Register an existing directory (or create a new folder) and run `stash assessments run` with the intended goal and requirements. Read the resulting evidence and existing memory, inspect the code to explain architecture and implemented features, and submit an evidence-backed semantic refinement. Review and apply selected context changes and issue candidates through assessment approval; it saves an initial checkpoint and tracking baseline atomically.

Reassessment uses the same workflow, retaining historical assessments and existing issues. Preserve human metadata by selecting only intended context changes; do not close issues merely because a finding disappeared. Distinguish source facts, inferred behavior, checks not run and checks actually executed. An empty candidate list does not establish bug-free software.

`stash init . --goal "Intended outcome"` registers and performs the same bounded assessment. Optional `--file payload.json` first fills empty metadata fields, preserving populated values. Review/refine/approve its returned assessment through the shared workflow. Create issues only for supported work/observed bugs and decisions only for actual choices.

## Resume and establish intent

Run `stash --json context` and inspect current repository code before relying on recorded context. Read relevant issues, decisions, the latest semantic checkpoint, subsequent file changes and recent observed hook events. Observations and dirty Git state do not prove task completion. Retrieve more history using `sessions list`/`sessions show` when needed.

A Codex SessionStart hook may supply a stash session UUID and runtime key. Read that session and use `sessions task SESSION_ID --file payload.json` with its original revision to record actual intent; its initial hook-created task is only a placeholder. If continuing a specific unfinished session, bind the supplied runtime key to it with `integrations codex bind RUNTIME_KEY --session SESSION_ID` after confirming that choice. Queued older events keep their original binding.

Without a binding, explicitly continue the relevant unfinished session or use `sessions start "Actual task"`. Do not pick an unrelated session because it is recent; clarify if multiple tasks remain ambiguous. A completed session stays historical: start a new session, then bind the runtime to that new session if applicable. Read [checkpoint commands](references/checkpoints.md) for payloads and retry rules.

## During work

Record intent before edits, and save semantic checkpoints after meaningful progress, actual verification, blockers, decisions and before changing focus. Hook tool/turn events and an optional saved-file watcher provide additional observed facts; they never replace these explanations. When project-scoped stash MCP tools are available, they may be used for context, issues and comments through the same API. Preserve original revisions and comment request IDs; never infer progress from observations alone.

Update relevant issues truthfully: `issues create`, `issues list`, `issues update`, `issues comment`. Record meaningful choices with `decisions add --reasoning --alternatives --reference`. Preserve the revision originally read for detailed issue or metadata edits. A passing tool event or end of a turn is not a reason to mark an issue done. Record verification evidence only for checks actually performed.

Check integration status when observations may be pending: `integrations codex status`. Hooks work only when installed, enabled and trusted by the supported client. Do not claim automatic tracking just because this skill exists.

## Finish or interrupt

Save a checkpoint with actual progress, unfinished work, blockers, verification/results and a concrete next action. Use `final: true` only for a deliberate final session handoff; successful tool calls, turn completion and interruption hooks do not imply a final handoff. Earlier checkpoints remain useful if the session ends abruptly. An additional `handoffs add` is optional; do not duplicate the same narrative unnecessarily.

## Conflicts, unavailable servers and secrets

Exit codes: 1 operation/server failure, 2 invalid input, 3 unresolved project, 4 conflict. On conflict, reread, reconcile the draft and use a new request ID for changed content; never refresh the revision and blindly overwrite someone else's work. Reuse an existing request draft/ID only for the exact same intended mutation.

Session start/checkpoint commands persist `.stash/drafts/` requests before HTTP and report their path on failure. Keep and replay them when the server returns. Hook outboxes are separate operational state under `.stash/runtime/codex/`; inspect status and drain pending facts. Task/issue/metadata mutations without durable draft support require retaining a local payload yourself if submission fails. Continue authorized source work when possible and clearly report what has not been saved.

Never read `.env` or secret values to fill context. Record environment names from manifests/examples only. Never put credentials, raw prompts, full transcripts, shell output containing secrets or fabricated verification in notes, payloads or drafts. See [installation and project instructions](references/install.md) when installing or exposing this skill.
