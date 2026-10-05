# Initialize and reassess projects

Adding a folder opens its project workspace. In Overview, **Initialize project** establishes context before you start tracking work. Choose Existing repository or New project, enter the intended goal, and list requirements or initial tasks one per line. If you need a new empty folder, choose Create new folder in Add project; its parent directory must already exist.

**Inspect project** reads bounded source/documentation, manifests, tests, current Git state and existing stash memory. It automatically validates package/Python manifests and inspected Python syntax. Source TODO/FIXME annotations become candidates requiring review. It does not launch an AI agent or run repository commands during inspection.

Review the proposed context next to existing values. Edit incorrect or incomplete proposals and use **Save context corrections to draft**. Existing nonempty fields are unselected by default. An undocumented project needs an intended goal before acceptance. A new project's supplied requirements become initial task candidates; stash does not generate an application scaffold.

Select candidate issues you want to track. Each has evidence and a confidence label. Matching titles or stable assessment identities link to existing issues, preserving their descriptions, status and attribution. A source annotation is not a confirmed bug, a failing command needs diagnosis, and no candidates does not mean the repository is bug-free.

For deeper understanding of architecture, implemented features, semantic bugs and reproduction steps, ask your coding agent to use the bundled [stash skill](../agent-skills/stash/SKILL.md). It reads the current code and supplies a structured refinement. The browser can import its JSON under **Add coding-agent analysis**, or the agent can submit it through `stash assessments refine`. Evidence must reference observed project files or recorded checks. Agent findings stay in the same reviewable draft.

Available test/type/lint/build commands appear under **Run repository checks**. Select the checks you want and click **Run selected checks and reassess**. This explicitly executes project code, which may write test/build files. Each command has a 60-second limit. stash stores outcomes and exit codes, not raw command output. Commands left unselected stay marked not run. If a check changes inspected source, inspect again before accepting.

**Accept selected context and issues** saves the selected context, creates or links selected issues, saves an initial unfinished checkpoint and establishes file tracking from the current baseline. These changes share one recoverable transaction. Source/Git/metadata changes since inspection reject the stale draft; inspect again and reconcile. Saving an assessment never claims tasks are complete.

Tracking is enabled by default at acceptance and can be disabled. It records saved file additions/modifications/removals while stash runs, including differences after downtime. Explanations and task progress come from Context checkpoints or optional agent integrations. Hooks require their own installation and trust; choosing file tracking does not configure hooks.

Use **Reassess project** after meaningful changes or when context is stale. Previous assessments, issues and checkpoints remain historical. Review which context fields to replace and which findings to track. A finding that disappears on reassessment does not close an existing issue automatically. Assessment history appears in Overview and is included in context and JSON exports.

## CLI

Global `--actor`, `--kind`, `--project`, `--server` and `--json` flags precede subcommands. From a registered project:

```sh
stash --json assessments run --goal "What this app should accomplish"
stash --json assessments list
stash --json assessments refine ASSESSMENT_ID --file /tmp/refinement.json
stash --json assessments approve ASSESSMENT_ID --file /tmp/approval.json
```

See the [initialization reference](../agent-skills/stash/references/initialize.md) for request payloads. `stash init . --goal "Intended outcome"` registers and inspects a folder, returning the same reviewable assessment. Repeat `--requirement "Task"` for initial tasks and use `--mode new` for a fresh project. Optional `--file payload.json` fills empty metadata before inspecting, retaining populated fields.

## Renaming existing Trackle data

On first default launch, stash copies the previous default SQLite shelf using SQLite backup, leaving the original database untouched. When a registered project has `.trackle/` but no `.stash/`, its records are copied into `.stash/`, retaining identities, user text, issue state and history. Original `.trackle/` files remain intact. Markdown record markers and configured document roots are translated to the new format.

Migration refuses symlinks, special files, oversized memory and pending legacy recovery journals. Resolve pending transactions with the previous version first. If `.stash/` already exists, it takes precedence and is not overwritten. Reinstall optional Codex hooks for the stash commands; legacy runtime configuration is retained as `legacy-config.json` but is not activated automatically. Explicit/custom database locations need the new `STASH_DB` or `STASH_DATA_DIR` setting.
