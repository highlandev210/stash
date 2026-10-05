from pathlib import Path
import sqlite3

import pytest
from support import TestClient

from stash.api import create_app


@pytest.fixture
def fixture(tmp_path):
    master = tmp_path / "projects"
    master.mkdir()
    repo = master / "first"
    repo.mkdir()
    (repo / "README.md").write_text("# First project\n")
    (repo / "docs").mkdir()
    (repo / "docs" / "notes.md").write_text("Original")
    external = tmp_path / "external"
    external.mkdir()
    (external / "README.md").write_text("# External project")
    database = tmp_path / "data" / "stash.db"
    app = create_app(database, test=True)
    with TestClient(app) as client:
        yield client, master, repo, external, database


def register(client, path):
    response = client.post("/api/v1/projects", json={"path": str(path)})
    assert response.status_code == 200, response.text
    return response.json()


def project_payload(project, **changes):
    fields = ["revision", "name", "path", "status", "description", "purpose", "brief", "focus", "next_step", "tags", "stack", "setup_command", "run_command", "test_command", "services", "env_names", "repo_url", "demo_url", "screenshot", "doc_roots", "writable_doc_roots"]
    return {**{key: project[key] for key in fields}, **changes}


def test_complete_vertical_workflow_and_restart(fixture):
    client, master, repo, external, database = fixture
    assert client.put("/api/v1/settings", json={"revision": 0, "master_folder": str(master), "identity": "Ben"}).status_code == 200
    candidates = client.get("/api/v1/discover").json()
    assert candidates[0]["path"] == str(repo)
    project = register(client, repo)
    second = register(client, external)
    assert external.exists() and external.parent != master
    path = f"/api/v1/projects/{project['id']}"
    read = client.get(path + "/document", params={"path": "README.md"})
    assert "First project" in read.json()["html"]
    project = client.put(path, json=project_payload(project, description="User written", next_step="Fix registration", brief="Local project registry")).json()
    response = client.post(path + "/issues", json={"title": "Registration bug", "type": "bug", "reproduction_steps": "Register same path twice"})
    assert response.status_code == 200, response.text
    issue = response.json()
    issue_path = path + f"/issues/{issue['id']}"
    assert client.get(f"/api/v1/projects/{second['id']}/issues/{issue['id']}").status_code == 404
    assert client.post(issue_path + "/comments", json={"body": "Confirmed in fixture"}).status_code == 200
    update = {key: value for key, value in issue.items() if key not in {"id", "project_id", "number", "creator", "created_at", "updated_at"}}
    update.update(status="done", verification="Registration regression test passed")
    assert client.put(issue_path, json=update).status_code == 200
    assert client.put(issue_path, json=update).status_code == 409
    assert client.post(path + "/decisions", json={"choice": "Keep UUID identity", "reasoning": "Paths can move"}).status_code == 200
    assert client.post(path + "/handoffs", json={"summary": "Fixed registration", "next_actions": "Check moved project", "verification": "Fixture test passed", "actor": {"name": "Test agent", "kind": "agent"}}).status_code == 200
    assert client.post(path + "/handoffs", json={"summary": "Checked moves", "next_actions": "Add export", "verification": "Not run"}).status_code == 200
    context = client.get(path + "/context").json()
    assert len(context["handoffs"]) == 2
    assert "Add export" in context["markdown"] and "Not run" in context["markdown"]
    assert client.get(path).json()["open_issue_count"] == 0
    assert client.get(path + "/activity").json()["total"] >= 8
    exported = client.get(path + "/export").json()
    assert len(exported["issues"]) == 1 and len(exported["records"]) == 4
    markdown = client.get(path + "/export", params={"format": "markdown"}).text
    assert "Confirmed in fixture" in markdown and "Fixed registration" in markdown
    with TestClient(create_app(database, test=True)) as restarted:
        assert restarted.get(path).json()["description"] == "User written"
        assert len(restarted.get(path + "/handoffs").json()) == 2
        assert restarted.get(issue_path).json()["status"] == "done"


def test_registration_symlinks_moves_missing_and_removal(fixture):
    client, master, repo, external, _ = fixture
    project = register(client, repo)
    link = master / "alias"
    link.symlink_to(repo, target_is_directory=True)
    assert register(client, link)["id"] == project["id"]
    assert client.get("/api/v1/projects").json()["total"] == 1
    path = f"/api/v1/projects/{project['id']}"
    moved = master / "renamed"
    repo.rename(moved)
    assert client.post("/api/v1/rescan", json={}).status_code == 200
    missing = client.get(path).json()
    assert missing["availability"] == "missing"
    changed = client.put(path, json=project_payload(missing, path=str(moved), description="Keep me")).json()
    assert changed["id"] == project["id"]
    assert client.post("/api/v1/rescan", json={}).status_code == 200
    changed = client.get(path).json()
    assert changed["description"] == "Keep me"
    assert client.request("DELETE", path, params={"revision": changed["revision"]}, json={}).status_code == 200
    assert moved.exists() and (moved / "README.md").read_text() == "# First project\n"


def test_documents_scope_sanitization_and_conflicts(fixture):
    client, _, repo, external, _ = fixture
    project = register(client, repo)
    path = f"/api/v1/projects/{project['id']}"
    (repo / ".env").write_text("SECRET=do-not-read")
    (repo / "docs" / "escape.md").symlink_to(external / "README.md")
    for name in ["../external/README.md", ".env", "docs/escape.md", "/etc/passwd"]:
        assert client.get(path + "/document", params={"path": name}).status_code in {403, 422}
    assert "docs/escape.md" not in client.get(path + "/docs").json()["files"]
    scope = project_payload(project, writable_doc_roots=["outside-docs"])
    assert client.put(path, json=scope).status_code == 422
    file = repo / "docs" / "notes.md"
    read = client.get(path + "/document", params={"path": "docs/notes.md"}).json()
    file.write_text("External change")
    stale = {"path": "docs/notes.md", "content": "My draft", "revision": read["revision"]}
    assert client.put(path + "/document", json=stale).status_code == 409
    assert file.read_text() == "External change"
    new = {"path": "docs/new.md", "content": "# New\n<script>alert(1)</script>\n[bad](javascript:alert(1))", "revision": None}
    response = client.put(path + "/document", json=new)
    assert response.status_code == 200, response.text
    assert "<script>" not in response.json()["html"] and 'href="javascript:' not in response.json()["html"]
    assert client.put(path + "/document", json=new).status_code == 409
    assert client.put(path + "/document", json={"path": "README.md", "content": "Unauthorized edit", "revision": None}).status_code == 403


def test_origins_revisions_idempotency_and_resolution(fixture):
    client, _, repo, _, _ = fixture
    assert client.post("/api/v1/projects", json={"path": str(repo)}, headers={"Origin": "https://evil.example"}).status_code == 403
    project = register(client, repo)
    path = f"/api/v1/projects/{project['id']}"
    first = client.put(path, json=project_payload(project, description="First"))
    assert first.status_code == 200
    assert client.put(path, json=project_payload(project, description="Stale")).status_code == 409
    nested = repo / "docs"
    assert client.get("/api/v1/resolve", params={"path": str(nested)}).json()["id"] == project["id"]
    payload = {"summary": "Checkpoint", "next_actions": "Continue"}
    one = client.post(path + "/handoffs", json=payload, headers={"Idempotency-Key": "session-1"})
    two = client.post(path + "/handoffs", json=payload, headers={"Idempotency-Key": "session-1"})
    assert one.json()["id"] == two.json()["id"]
    assert client.post(path + "/handoffs", json={**payload, "summary": "Different"}, headers={"Idempotency-Key": "session-1"}).status_code == 409
    assert client.put(path, json=project_payload(first.json(), env_names=["TOKEN=secret"])).status_code == 422


def test_backup_has_all_records(fixture, tmp_path):
    client, _, repo, _, database = fixture
    project = register(client, repo)
    backup = tmp_path / "backup.db"
    with sqlite3.connect(database) as source, sqlite3.connect(backup) as target:
        source.backup(target)
    with TestClient(create_app(backup, test=True)) as restored:
        assert restored.get(f"/api/v1/projects/{project['id']}").status_code == 200
