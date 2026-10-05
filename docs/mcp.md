# Project-scoped MCP tools

stash provides a local **stdio MCP bridge** for agents sharing issues and comments with the browser. It forwards to the same FastAPI endpoints; it does not write the database or project files directly. The server must be running. No MCP service is needed for browser use.

Run using the installed stash Python environment, pinning one registered project ID:

```sh
/absolute/path/to/stash/.venv/bin/python -m stash.mcp_server --project PROJECT_UUID
```

For the verified Codex CLI, register that command on a normal host:

```sh
codex mcp add stash -- /absolute/path/to/stash/.venv/bin/python -m stash.mcp_server --project PROJECT_UUID
```

Alternatively configure a project-specific `mcp_servers.stash` entry in `.codex/config.toml` using `command` for that Python and `args` for `-m`, `stash.mcp_server`, `--project`, and the UUID. Do not share a global fixed project binding across unrelated projects. The bridge rejects remote server origins; an optional `--server` accepts loopback HTTP only. Attribution defaults to Codex (agent). Identity is attributed text, not authenticated proof.

Tools: project_context, issues_list, issue_get, issue_create, issue_update, comments_list, comment_add. Lists support pagination. Read the issue before updating; submit all fields you intend to preserve with its original revision. Newer human/agent writes produce a conflict. Read again, compare drafts, and explicitly reconcile. The bridge never silently fetches a newer revision to force an update. Comment retries reuse the same request_id and body. Creates do not automatically retry: a network disconnect can leave acceptance uncertain, so inspect the list before resubmitting.

The browser polls issues/comments/activity and shows when an open edit's revision has changed. Drafts retain their original revision, and the backend remains the authority for conflict detection. No embedded agent is launched by the website.

The bridge implements the newline-delimited stdio transport and tools/lifecycle from [MCP 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports). It negotiates that handshake version; it does not advertise newer protocol extensions. Tests cover an actual subprocess handshake and tool calls forwarded into the real API, including human/agent conflicts and comment deduplication. Real Codex-to-MCP HTTP calls remain a host acceptance gate because this development sandbox prohibits network sockets.
