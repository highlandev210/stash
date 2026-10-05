# Installation and project instructions

Install the stash backend/CLI and start its local server first. Ensure `stash` resolves to the intended executable in the agent environment. For this source checkout, the executable is `.venv/bin/stash`; from another project use its absolute path or put the installed executable on PATH.

Explicit use needs no global installation: ask the agent to read this skill's `SKILL.md` by path and follow it for the target repository. For project-local Codex discovery, copy the complete skill directory to `.agents/skills/stash/`, preserving any existing customized skill. User-level installation can use the agent's documented skill directory; do not assume Claude/other clients use the same location.

The Codex integration installer can install this skill and merge project hooks:

```sh
stash --json register /absolute/project
stash --json integrations codex install --path /absolute/project
```

Run `--no-skill` when a customized skill already exists or installing from a distribution without bundled skill sources. Restart the supported Codex CLI and review/trust the hook definitions using `/hooks`. Installation cannot silently grant hook trust. See the app's `docs/codex-integration.md` for the supported client, diagnostics and removal.

Copy the requested parts of `assets/AGENTS.snippet.md` into project instructions, preserving unrelated content. Nothing in registration automatically modifies instructions. Installing or exposing a skill does not guarantee that every client invokes it automatically.

For an agent without supported hooks, explicitly invoke the skill and save semantic checkpoints throughout work. Do not claim equivalent automatic capture.
