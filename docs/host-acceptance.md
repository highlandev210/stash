# Preparing the real host acceptance gate

Generate an isolated fixture with `.venv/bin/python scripts/prepare_acceptance.py /tmp/stash-acceptance-UNIQUE`. The destination must not exist. This uses shared backend services to create fixture records and installs project-local skill/hooks without trusting them. It does not launch an agent or pass the live gate.

Generated artifacts:
- ACCEPTANCE.md: isolated server command and interruption/restart/offline/move/conflict checklist.
- codex-prompt.txt: an explicit initialization/resume task designed for interruption.
- conditions.json: fixture project ID and registry location.
- project/: a small Python project with human-owned metadata, product README, two unfinished sessions, checkpoints, and watcher baseline.

Run Codex on the fixture, not the stash application source. Use the client-supported trust review described in the hook guide. Keep the fixture registry separate from the normal shelf. Record actual event delivery, retained checkpoints, and recoverable next actions after interrupt/abrupt termination; do not require a SessionEnd event after a kill.

Only Codex has a hook adapter. Other agents/editors can use the skill and watcher; their dedicated hooks are not claimed as supported. For browser/agent shared issues, connect the project-scoped MCP bridge and deliberately exercise original-revision conflicts and attributed comment retries.

Publication follows successful live acceptance. Publish to the user-selected highlandev210 account. Git metadata must be writable and authenticated GitHub access available. Do not substitute another connected account or claim publication without checking the remote repository and commit. The development sandbox cannot initialize its protected `.git` or reach GitHub through the terminal; these limitations do not establish a passing gate.
