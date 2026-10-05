# Optional saved-file watcher

Enable per project in Context or with `stash watcher enable`. Use `stash watcher status`, `stash watcher observations`, and `stash watcher disable` to inspect or stop it. The server scans registered enabled projects about every three seconds, after integration recovery finishes. The interval is approximate; large projects can take longer.

The first scan establishes a baseline without reporting every existing file as new. Later scans group additions, modifications and removals into one observation per scan. No agent or Git repository is required. Hashes and paths are recorded, never file contents. Dependency folders, build output, dotfiles including .env/.git/.stash, key files, and escaping symlinks are excluded using the same bounded fingerprint scan as session observations.

The durable baseline lives under `.stash/runtime/watcher/`; accepted history lives under `.stash/file_observations/`. Changes saved while stash is stopped are compared on its next scan. Moving a project preserves its baseline and history after updating its registered path. Disabling preserves history and baseline. A journal commits each observation and baseline together, so a crash cannot acknowledge a change without retaining its observation.

A partial scan explicitly reports warnings and never infers deletion from omitted files. Scan limits bound directories, file counts, bytes and metadata. Oversized files can be omitted. This is polling: changes made and reverted entirely between scans cannot be recovered. It records saved states, not every keystroke or a complete filesystem audit.

Context, Activity, exports, and agent context show observations separately from checkpoints. No file observation completes an issue or session or claims successful verification. Hooks and the skill remain responsible for semantic progress.
