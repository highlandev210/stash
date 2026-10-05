# Using stash

stash brings your local projects, tasks, and notes together. You can use the browser app on its own. Git, coding agents, and the command line are optional for everyday use after installation.

## Open stash

Follow the [README setup](../README.md#install-and-open-the-app) or [systemwide installation guide](systemwide-install.md). With a source installation, run `npm start` from the stash checkout and open **http://127.0.0.1:8000**. Keep the server running while you use the app. Closing the browser does not stop it; Ctrl+C in its terminal does.

stash currently needs technical setup from source. It does not yet include a desktop installer, automatic startup, or an application-menu shortcut.

## Add and find projects

The **shelf** is the home screen. A **project** is an existing folder on your computer that you add to the shelf.

1. In **Settings**, set **Your name**. Saved changes show this name.
2. Click **Add project** and enter its full folder path under **Existing project path**.
3. Click **Register project**, then open its card on the shelf.

stash registers the folder in place and creates its `.stash/` records. Existing files stay where they are. A project folder can be registered without Git.

For several projects in one place, set **Master folder** in Settings to their parent directory. **Add project** shows discovered immediate subfolders; click **Add** beside the ones you want. It does not search every nested folder. Use search, status filters, tags, sorting, and grid/list controls to find registered projects later.

## Work inside a project

The shelf and project views are part of one app. Use the back arrow to return to the shelf.

### Overview: describe the project

Click **Edit project** to set the name, description, purpose, status, tags, current focus, and next step. For example, a focus might be “Finish the portfolio homepage,” and a next step might be “Check the layout on a phone.”

Technical fields such as stack, commands, services, and environment-variable names are available when useful. Commands are reference text to copy; stash does not execute them. Store variable names, not secret values. **Export JSON** and **Export Markdown** download project records for reference.

### Issues: keep track of work

Create a **New issue** for a task, bug, or feature idea. Give it a clear title and describe the outcome you want. Set its status and priority, open it to edit details, and add comments as you work.

Acceptance criteria describe what would make the task finished. Verification evidence describes what you actually checked—for example, “Opened the page on a phone and confirmed the menu works.” Record checks you performed rather than expected results.

### Docs: read and write notes

Read the project's permitted Markdown files here. **New document** creates a note inside `.stash/docs/`. The app offers editing for writable documents; decisions and handoffs shown through Docs are read-only. In **Overview → Edit project**, readable and writable document paths control access to existing project documentation.

### Context: remember where you stopped

A **brief** describes the project. A **handoff** is a saved progress note for your future self or another person. Use **Edit brief and focus** for the current summary and **Save session handoff** to record progress, unfinished work, checks, and next actions. Handoffs stay in history; save a new one to correct an earlier note.

You can also save decisions with their reasons and alternatives. For longer work, **Start session** records the task and **Save checkpoint** opens a form to record progress during it. A session without a final checkpoint is shown as unfinished; this is separate from saving a standalone handoff. See [sessions and checkpoints](session-checkpoints.md) for details.

The optional file watcher records file changes. Those observations do not mean a task passed its checks or is complete.

### Activity: review saved changes

Activity shows attributed tracker events in time order. A name is a label for who saved the change, not proof of an authenticated identity. Manual file edits can change visible records without creating an activity event.

## Save, back up, and move projects

Saved records persist when you stop stash. They live in each project's hidden `.stash/` folder. Shelf locations and settings live separately under `$XDG_DATA_HOME/stash/` or `~/.local/share/stash/`.

Back up entire project folders, including `.stash/`, and the shelf data directory while the server is stopped. Exports are useful readable copies, but do not replace a complete backup of folders and shelf settings.

If you move a project, move the whole folder including `.stash/`, then update **Project path** in **Edit project** or register the new path. Its records and identity remain with it. Two available folders with the same identity cannot both be registered as independent projects; duplicating a folder is not a supported way to create a new independent stash project.

Removing a project from the shelf removes its registration, not its source files or `.stash/` records. You can register it again later. Losing the shelf database requires registering folders again; stash does not automatically discover all prior locations.

## Common problems

- **The page will not connect:** start the server and check its terminal for errors. Use port 8000 for the built app; port 3000 is for frontend development.
- **The frontend is not built:** run `npm run build` in the checkout. For a systemwide installation, set `STASH_FRONTEND` as shown in its guide.
- **A project is unavailable:** check that its folder or drive is accessible. Correct a moved path and use **Settings → Rescan registered projects** to refresh availability.
- **An edit conflicts with another change:** keep your draft, reload the current record, compare, and apply the intended edits again. stash rejects outdated edits rather than overwriting newer content.
- **A storage or migration error appears:** preserve your files and read the error. Do not delete `.stash/` to clear it. See [storage and recovery](folder-storage.md).

For optional automation, continue to [agent integration](agent-integration.md). It is not required for the basic browser workflows above.

## Initialize and keep context current

Registration opens Overview. Use Initialize project to capture the intended goal and requirements, inspect code/docs, review context and candidate issues, and accept tracking settings. Existing projects use the same flow with their previous memory preserved. Use Reassess project when the code or project direction changes. See [project assessment](project-assessment.md) for review, checks and optional deeper agent analysis.
