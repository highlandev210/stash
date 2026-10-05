# Using stash with coding agents

The reusable [skill](../agent-skills/stash/SKILL.md) and its [installation guide](../agent-skills/stash/references/install.md) describe the current lifecycle. For durable Codex event capture, see [Codex integration](codex-integration.md). Hooks supplement explicit checkpoints; they do not write task explanations or verification.

The skill teaches the workflow; stash stores the memory. Installing a skill or adding instructions does not guarantee that an agent invokes it automatically.

After installing the backend/CLI and starting the server, ask your coding agent to use the stash skill:

> Use the stash skill at /path/to/stash/agent-skills/stash/SKILL.md to initialize /path/to/your-project. Establish its intended goal, inspect existing context and code, run appropriate authorized checks, refine the assessment with architecture/features and evidence-backed issue candidates, then reconcile and accept the selected changes with a tracking baseline.

The browser exposes the same workflow in Overview. See [project initialization and reassessment](project-assessment.md) and the [skill initialization reference](../agent-skills/stash/references/initialize.md) for assessment, refinement and approval payloads. `stash init . --goal "Intended outcome"` registers and performs an initial reviewable assessment; optional `--file` also fills empty metadata fields.

The repository stays in place. Nothing is automatically written to that project's AGENTS.md.

Install or expose `agent-skills/stash/SKILL.md` using your coding agent's skill mechanism. Ensure the installed `stash` executable is on the agent's PATH, or specify its absolute path in the instructions. The skill folder is portable and contains no project-specific registration data.

Add this snippet to a project's AGENTS.md when you want that project's agents to use stash:

```markdown
## Project memory with stash

When working on this registered project, use the stash skill if available.
When asked to initialize this project, inspect its repository, run `stash assessments run`, refine context and supported findings,
then accept the selected context/issues and tracking configuration. Acceptance saves an initial checkpoint. Existing metadata is preserved; use revision-checked
`projects update` for explicit changes.
At session start, run `stash --json context` from the project directory and
read the brief, relevant issues, decisions, and latest handoff. Inspect the
repository before assuming recorded context is current.

During work, update relevant issues and record meaningful decisions, blockers,
and checkpoints. At session end, save a handoff with completed work, changed
files, actual verification results, unresolved work, and concrete next actions.
Do not store secrets or claim checks passed unless they actually ran.

stash's server must be running. If unavailable, report that records could not
be saved and retain a handoff draft; do not invent a successful update.
```

Agent identity is attributed text for a single-user tool, not authenticated proof. Context always includes freshness references and an instruction to inspect current code. Earlier checkpoints remain when a session is interrupted.

## How initialization works

The browser can create an empty folder, perform bounded deterministic inspection, review candidates, run explicitly selected checks and save initialization. `stash init` registers and inspects an existing folder, optionally filling empty metadata from a supplied payload. Both produce the same reviewable assessment.

stash does not contain an embedded coding agent. For semantic architecture/feature analysis and bug discovery, Codex or another coding agent inspects the current repository and submits a refinement through the CLI. Opening a directory in the browser does not launch that agent. An application scaffold can be created separately under the user's development task; stash can register it or create an empty folder for a new project.
