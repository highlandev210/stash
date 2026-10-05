"""CLI business operations go exclusively through the running HTTP API."""
import json
from pathlib import Path
import sys
from typing import Optional

import httpx
import typer

app = typer.Typer(no_args_is_help=True)
projects = typer.Typer(no_args_is_help=True)
issues = typer.Typer(no_args_is_help=True)
decisions = typer.Typer(no_args_is_help=True)
handoffs = typer.Typer(no_args_is_help=True)
app.add_typer(projects, name="projects")
app.add_typer(issues, name="issues")
app.add_typer(decisions, name="decisions")
app.add_typer(handoffs, name="handoffs")
state = {}


@app.callback()
def configure(server: str = "http://127.0.0.1:8000", project: Optional[str] = None, actor: str = "Agent", kind: str = "agent", json_output: bool = typer.Option(False, "--json")):
    if kind not in {"human", "agent"}:
        raise typer.BadParameter("kind must be human or agent")
    state.pop("pending_draft", None)
    state.update(server=server.rstrip("/") + "/api/v1", project=project, actor={"name": actor, "kind": kind}, json=json_output)


def fail(code, message, exit_code):
    payload = {"code": code, "message": message}
    if state.get("pending_draft"):
        payload["draft"] = state["pending_draft"]
    if state.get("json"):
        typer.echo(json.dumps({"error": payload}))
    else:
        typer.echo(message + (f"; recoverable draft: {state['pending_draft']}" if state.get("pending_draft") else ""), err=True)
    raise typer.Exit(exit_code)


def request(method, path, payload=None, params=None, key=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Idempotency-Key"] = key
    try:
        response = httpx.request(method, state["server"] + path, json=payload, params=params, headers=headers, timeout=660 if path.endswith("/assessments") and method == "POST" else 15)
    except httpx.HTTPError:
        fail("server_unavailable", "stash server is unavailable. Start stash-server and check --server", 1)
    if response.is_error:
        try:
            error = response.json()
        except ValueError:
            error = {"code": "server_error", "message": f"Server returned HTTP {response.status_code}"}
        fail(error.get("code", "error"), error.get("message", str(error)), 4 if response.status_code == 409 else 3 if error.get("code") == "unresolved_project" else 2 if response.status_code == 422 else 1)
    return response.json()


def project_id():
    if state["project"]:
        return state["project"]
    return request("GET", "/resolve", params={"path": str(Path.cwd().resolve())})["id"]


def base():
    return f"/projects/{project_id()}"


def emit(data):
    if state["json"]:
        typer.echo(json.dumps(data, ensure_ascii=False))
    elif isinstance(data, dict) and "markdown" in data:
        typer.echo(data["markdown"])
    else:
        typer.echo(json.dumps(data, indent=2, ensure_ascii=False))


def load_payload(file):
    try:
        data = json.loads(sys.stdin.read() if file == "-" else Path(file).read_text())
        if not isinstance(data, dict):
            raise ValueError()
        return {**data, "actor": state["actor"]}
    except (OSError, ValueError):
        fail("invalid_input", "Provide a readable JSON object file, or '-' for stdin", 2)


@app.command()
def register(path: Path):
    emit(request("POST", "/projects", {"path": str(path.expanduser().resolve()), "actor": state["actor"]}))


PROJECT_FIELDS = {"name", "path", "status", "description", "purpose", "tags", "stack", "focus", "next_step", "brief", "setup_command", "run_command", "test_command", "services", "env_names", "repo_url", "demo_url", "screenshot", "doc_roots", "writable_doc_roots"}


def metadata_payload(project):
    return {field: project[field] for field in PROJECT_FIELDS}


@projects.command("show")
def project_show():
    emit(request("GET", base()))


@projects.command("update")
def project_update(file: str = typer.Option(..., "--file")):
    incoming = load_payload(file)
    if "revision" not in incoming:
        fail("invalid_input", "Metadata update must include the revision originally read", 2)
    unknown = set(incoming) - PROJECT_FIELDS - {"revision", "actor"}
    if unknown:
        fail("invalid_input", "Unknown metadata fields: " + ", ".join(sorted(unknown)), 2)
    path = base()
    current = request("GET", path)
    if current["revision"] != incoming["revision"]:
        fail("conflict", "Project changed since inspection; reread and reconcile the draft", 4)
    emit(request("PUT", path, {**metadata_payload(current), **incoming, "actor": state["actor"]}))


@app.command("init")
def initialize(path: Path = typer.Argument(Path(".")), file: Optional[str] = typer.Option(None, "--file", help="Optional metadata JSON to fill empty fields"), goal: str = "", mode: str = "existing", requirement: Optional[list[str]] = typer.Option(None, "--requirement")):
    """Register and inspect a project; propose context and evidence-backed issues for review."""
    incoming = load_payload(file) if file else {}
    unknown = set(incoming) - PROJECT_FIELDS - {"actor"}
    if unknown:
        fail("invalid_input", "Unknown initialization fields: " + ", ".join(sorted(unknown)), 2)
    if "path" in incoming and Path(incoming["path"]).expanduser().resolve() != path.expanduser().resolve():
        fail("invalid_input", "Metadata path must match the directory being initialized", 2)
    current = request("POST", "/projects", {"path": str(path.expanduser().resolve()), "actor": state["actor"]})
    payload = metadata_payload(current)
    applied, preserved = [], []
    for field, value in incoming.items():
        if field in {"actor", "path"}:
            continue
        # Registration supplies these defaults; changing them requires an explicit revision-checked update.
        if field in {"name", "status", "doc_roots", "writable_doc_roots"} or current.get(field):
            if value != current.get(field):
                preserved.append(field)
            continue
        if value:
            payload[field] = value
            applied.append(field)
    if applied:
        current = request("PUT", f"/projects/{current['id']}", {**payload, "revision": current["revision"], "actor": state["actor"]})
    assessment = request("POST", f"/projects/{current['id']}/assessments", {"mode": mode, "goal": goal or incoming.get("purpose", ""), "requirements": requirement or [], "actor": state["actor"]})
    emit({"project": current, "filled_fields": sorted(applied), "preserved_fields": sorted(preserved), "assessment": assessment, "next": "Review and refine the assessment, then approve selected context/issues to establish a checkpoint and tracking baseline."})


@projects.command("list")
def project_list(query: str = "", status: str = "", tag: str = "", limit: int = 100, offset: int = 0):
    emit(request("GET", "/projects", params={"q": query, "status": status, "tag": tag, "limit": limit, "offset": offset}))


@app.command()
def context():
    emit(request("GET", base() + "/context"))


@issues.command("list")
def issue_list(status: str = "", query: str = "", limit: int = 100, offset: int = 0):
    emit(request("GET", base() + "/issues", params={"status": status, "q": query, "limit": limit, "offset": offset}))


@issues.command("create")
def issue_create(title: str, type: str = "task", description: str = "", priority: str = "medium", file: Optional[str] = None):
    payload = load_payload(file) if file else {"title": title, "type": type, "description": description, "priority": priority, "actor": state["actor"]}
    emit(request("POST", base() + "/issues", payload))


@issues.command("update")
def issue_update(issue_id: str, status: Optional[str] = None, verification: Optional[str] = None, title: Optional[str] = None, file: Optional[str] = None):
    path = base() + "/issues/" + issue_id
    if file:
        payload = load_payload(file)
        # Files must carry the revision originally read, preventing silent stale edits.
        if "revision" not in payload:
            fail("invalid_input", "Update JSON must include the revision you read", 2)
    else:
        payload = request("GET", path)
        for key in ["id", "project_id", "number", "creator", "created_at", "updated_at"]:
            payload.pop(key, None)
        for key, value in [("status", status), ("verification", verification), ("title", title)]:
            if value is not None:
                payload[key] = value
        payload["actor"] = state["actor"]
    emit(request("PUT", path, payload))


@issues.command("comment")
def comment(issue_id: str, body: str, key: Optional[str] = None):
    emit(request("POST", base() + f"/issues/{issue_id}/comments", {"body": body, "actor": state["actor"]}, key=key))


@decisions.command("add")
def decision_add(choice: str, reasoning: str = "", alternatives: str = "", reference: str = "", key: Optional[str] = None):
    emit(request("POST", base() + "/decisions", {"choice": choice, "reasoning": reasoning, "alternatives": alternatives, "reference": reference, "actor": state["actor"]}, key=key))


@handoffs.command("add")
def handoff_add(file: str = typer.Argument(..., help="JSON file or '-' for stdin"), key: Optional[str] = None):
    emit(request("POST", base() + "/handoffs", load_payload(file), key=key))


@app.command("export")
def export():
    emit(request("GET", base() + "/export"))


from .session_commands import install
import sys as _sys
install(app, _sys.modules[__name__])
from .integration_commands import install_commands
install_commands(app, _sys.modules[__name__])
from .document_commands import install_commands as install_docs
install_docs(app, _sys.modules[__name__])


from .watcher_commands import install_commands as install_watcher
install_watcher(app, _sys.modules[__name__])


if __name__ == "__main__":
    app()
from .assessment_commands import install_commands as install_assessments
install_assessments(app, _sys.modules[__name__])
