import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from stash import services as svc
from stash.db import open_database
from stash.filesystem import Problem, digest
from stash.models import Activity, Issue, Project, Record, Registry, now, uid
from stash.schemas import Actor, Decision, DocumentWrite, Handoff, IssueInput, IssuePatch, ProjectPatch, Registration
from stash.store import FolderStore, json_bytes
from support import TestClient
from stash.api import create_app


@pytest.fixture
def memory(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "README.md").write_text("# Existing source documentation\n")
    engine, factory = open_database(tmp_path / "shelf.db")
    with factory() as db:
        project = svc.register(db, Registration(path=str(root)))
        project_id = project.id
    yield root, factory, project_id
    engine.dispose()


def patch(data, **changes):
    fields = set(ProjectPatch.model_fields) - {"actor"}
    return ProjectPatch.model_validate({**{k: data[k] for k in fields}, **changes})


def test_files_are_authoritative_and_database_has_no_record_copies(memory):
    root, factory, project_id = memory
    with factory() as db:
        p = svc.get_project(db, project_id)
        original = svc.project_dict(db, p)
        updated = svc.update_project(db, p, patch(original, description="Before", brief="The brief"))
        assert "brief" not in json.loads((root / ".stash/project.json").read_text())
        assert (root / ".stash/docs/brief.md").read_text() == "The brief"
        issue = svc.create_issue(db, p, IssueInput(title="Fix startup", type="bug"))
        path = root / f".stash/issues/{issue['id']}.json"
        external = json.loads(path.read_text())
        external["title"] = "Edited in my editor"
        path.write_text(json.dumps(external))
        assert svc.get_issue(db, project_id, issue["id"])["title"] == "Edited in my editor"
        stale = IssuePatch.model_validate({**{k: issue[k] for k in IssueInput.model_fields if k in issue}, "revision": issue["revision"]})
        with pytest.raises(Problem) as conflict:
            svc.update_issue(db, p, issue, stale)
        assert conflict.value.status == 409
        metadata = json.loads((root / ".stash/project.json").read_text())
        metadata["description"] = "Edited externally"
        (root / ".stash/project.json").write_text(json.dumps(metadata))
        assert svc.project_dict(db, p)["description"] == "Edited externally"
        with pytest.raises(Problem) as conflict:
            svc.update_project(db, p, patch(updated, description="Stale web draft"))
        assert conflict.value.status == 409
        for model in [Project, Issue, Record, Activity]:
            assert db.scalar(select(func.count()).select_from(model)) == 0
        assert db.scalar(select(func.count()).select_from(Registry)) == 1


def test_markdown_history_and_brief_are_shared_with_docs(memory):
    root, factory, project_id = memory
    with factory() as db:
        p = svc.get_project(db, project_id)
        old = svc.project_dict(db, p)
        handoff = svc.add_record(db, p, "handoff", Handoff(summary="Checkpoint", next_actions="Write tests", verification="Not yet run"), request_key="checkpoint")
        decision = svc.add_record(db, p, "decision", Decision(choice="Keep files local", reasoning="Portable project memory"))
        file = root / f".stash/handoffs/{handoff['id']}.md"
        assert "## Next Actions" in file.read_text() and "Write tests" in file.read_text()
        file.write_text(file.read_text().replace("Write tests", "Review the changed files"))
        assert svc.context_data(db, p)["handoffs"][0]["next_actions"] == "Review the changed files"
        with FolderStore(root).locked() as store:
            brief = store.read("docs/brief.md")
        svc.save_document(db, p, DocumentWrite(path=".stash/docs/brief.md", content="An editor-readable project brief", revision=digest(brief)), root.parent / "locks")
        assert svc.project_dict(db, p)["brief"] == "An editor-readable project brief"
        with pytest.raises(Problem):
            svc.update_project(db, p, patch(old, brief="Stale brief"))
        svc.add_record(db, p, "handoff", Handoff(summary="Second checkpoint", next_actions="Continue review"))
        assert len(svc.records(db, project_id, "handoff")) == 2
        assert svc.get_record(db, project_id, decision["id"])["choice"] == "Keep files local"
        log = (root / ".stash/activity.jsonl").read_bytes()
        svc.add_record(db, p, "decision", Decision(choice="Preserve history"))
        assert (root / ".stash/activity.jsonl").read_bytes().startswith(log)


def test_remove_move_and_rebuild_registry_preserve_memory(memory, tmp_path):
    root, factory, project_id = memory
    with factory() as db:
        p = svc.get_project(db, project_id)
        svc.add_record(db, p, "handoff", Handoff(summary="Saved work", next_actions="Resume"))
        data = svc.project_dict(db, p)
        svc.remove_project(db, p, data["revision"])
        assert (root / ".stash/project.json").exists()
        restored = svc.register(db, Registration(path=str(root)))
        assert restored.id == project_id
        moved = tmp_path / "moved"
        root.rename(moved)
        assert svc.project_dict(db, restored)["availability"] == "missing"
        attached = svc.register(db, Registration(path=str(moved)))
        assert attached.id == project_id
        assert svc.context_data(db, attached)["handoffs"][0]["summary"] == "Saved work"
    engine, empty_registry = open_database(tmp_path / "new-computer.db")
    with empty_registry() as db:
        attached = svc.register(db, Registration(path=str(moved)))
        assert attached.id == project_id
        assert svc.context_data(db, attached)["handoffs"][0]["next_actions"] == "Resume"
    engine.dispose()


def test_duplicate_identity_and_symlinks_do_not_escape(memory, tmp_path):
    import shutil
    root, factory, project_id = memory
    cloned = tmp_path / "clone"
    shutil.copytree(root, cloned)
    with factory() as db:
        with pytest.raises(Problem) as conflict:
            svc.register(db, Registration(path=str(cloned)))
        assert conflict.value.code == "duplicate_identity"
        project = svc.get_project(db, project_id)
        (root / ".stash/issues").rmdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (root / ".stash/issues").symlink_to(outside, target_is_directory=True)
        with pytest.raises(Problem) as unsafe:
            svc.create_issue(db, project, IssueInput(title="Must not escape"))
        assert unsafe.value.status == 403 and list(outside.iterdir()) == []


def test_interrupted_transaction_recovers_and_keeps_log_prefix(memory):
    root, factory, project_id = memory
    with FolderStore(root).locked() as store:
        original_log = store.log_bytes()
        old = store.read("project.json")
        metadata = json.loads(old)
        metadata["description"] = "Recovered after interruption"
        intended = json_bytes(metadata)
        event = svc.new_event(project_id, "metadata", project_id, "Recovered edit", Actor())
        recover = store.recover
        def interrupt():
            raise RuntimeError("simulated power interruption")
        store.recover = interrupt
        with pytest.raises(RuntimeError):
            store.transaction({"project.json": (old, intended)}, event)
        store.recover = recover
    # Simulate a partial append, one of the crash boundaries recovered by the journal.
    line = (json.dumps(event, ensure_ascii=False) + "\n").encode()
    (root / ".stash/activity.jsonl").write_bytes(original_log + line[:20])
    with FolderStore(root).locked() as store:
        assert store.read_project(project_id)["description"] == "Recovered after interruption"
        assert store.log_bytes() == original_log + line
        assert store.read(".transaction.json") is None
    with FolderStore(root).locked() as store:
        assert sum(e["id"] == event["id"] for e in store.activity()) == 1


def test_recovery_conflict_preserves_external_edit(memory):
    root, _, project_id = memory
    with FolderStore(root).locked() as store:
        old = store.read("project.json")
        metadata = json.loads(old)
        metadata["description"] = "Interrupted app write"
        store.recover = lambda: (_ for _ in ()).throw(RuntimeError("interrupt"))
        with pytest.raises(RuntimeError):
            store.transaction({"project.json": (old, json_bytes(metadata))})
    external = json.loads(old)
    external["description"] = "External change after crash"
    (root / ".stash/project.json").write_text(json.dumps(external))
    with pytest.raises(Problem) as conflict:
        with FolderStore(root).locked():
            pass
    assert conflict.value.status == 409
    assert "External change after crash" in (root / ".stash/project.json").read_text()
    assert (root / ".stash/.transaction.json").exists()


def test_parallel_issue_creation_allocates_unique_numbers(memory):
    _, factory, project_id = memory
    def create(title):
        with factory() as db:
            p = svc.get_project(db, project_id)
            return svc.create_issue(db, p, IssueInput(title=title))
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(create, ["First", "Second"]))
    assert {i["number"] for i in results} == {1, 2}
    assert len({i["id"] for i in results}) == 2


def test_legacy_migration_preserves_records_and_removes_database_copies(tmp_path):
    root = tmp_path / "legacy"
    root.mkdir()
    engine, factory = open_database(tmp_path / "legacy.db")
    project_id, issue_id, handoff_id = uid(), uid(), uid()
    with factory() as db:
        db.add(Project(id=project_id, path=str(root), name="Legacy project", details={"description": "User description", "brief": "Legacy brief"}))
        db.flush()
        db.add(Issue(id=issue_id, project_id=project_id, number=12, title="Keep this issue", type="bug", creator={"name": "Ben", "kind": "human"}, details={"description": "Legacy bug"}))
        db.add(Record(id=handoff_id, project_id=project_id, kind="handoff", data={"summary": "Legacy checkpoint", "next_actions": "Finish migration"}, actor={"name": "Agent", "kind": "agent"}))
        db.commit()
        svc.prepare_registry(db)
        project = svc.get_project(db, project_id)
        assert svc.project_dict(db, project)["description"] == "User description"
        assert svc.get_issue(db, project_id, issue_id)["number"] == 12
        assert svc.context_data(db, project)["handoffs"][0]["summary"] == "Legacy checkpoint"
        assert (root / f".stash/handoffs/{handoff_id}.md").exists()
        for model in [Project, Issue, Record, Activity]:
            assert db.scalar(select(func.count()).select_from(model)) == 0
        before = (root / ".stash/activity.jsonl").read_bytes() if (root / ".stash/activity.jsonl").exists() else b""
        svc.prepare_registry(db)
        assert ((root / ".stash/activity.jsonl").read_bytes() if (root / ".stash/activity.jsonl").exists() else b"") == before
    engine.dispose()


def test_failed_migration_never_overwrites_existing_folder_records(tmp_path):
    root = tmp_path / "conflict"
    root.mkdir()
    project_id = uid()
    original = {**svc.defaults("Conflict", str(root)), "id": project_id, "description": "Folder version", "created_at": now(), "tracker_updated_at": now()}
    with FolderStore(root).locked(create=True) as store:
        store.initialize(original)
    before = (root / ".stash/project.json").read_bytes()
    engine, factory = open_database(tmp_path / "shelf.db")
    with factory() as db:
        db.add(Project(id=project_id, path=str(root), name="Conflict", details={"description": "Database version"}))
        db.commit()
        svc.prepare_registry(db)
        assert db.get(Project, project_id).details["description"] == "Database version"
        assert (root / ".stash/project.json").read_bytes() == before
        data = svc.project_dict(db, db.get(Registry, project_id))
        assert data["migration_pending"] and "differs" in data["storage_error"]
    engine.dispose()


def test_pending_missing_migration_can_be_unregistered_and_restored(tmp_path):
    root = tmp_path / "not-present"
    project_id = uid()
    engine, factory = open_database(tmp_path / "shelf.db")
    with factory() as db:
        db.add(Project(id=project_id, path=str(root), name="Missing", details={"description": "Retained legacy records"}))
        db.commit()
        svc.prepare_registry(db)
        registered = svc.get_project(db, project_id)
        assert registered.availability == "missing"
        svc.remove_project(db, registered, registered.summary["revision"])
        svc.prepare_registry(db)
        assert svc.all_projects(db) == []
        assert db.get(Project, project_id) is not None
        root.mkdir()
        restored = svc.register(db, Registration(path=str(root)))
        assert restored.id == project_id
        assert svc.project_dict(db, restored)["description"] == "Retained legacy records"
        assert db.get(Project, project_id) is None
    engine.dispose()


def test_website_reads_plain_folder_edits_and_renders_tracker_docs(memory, tmp_path):
    root, _, project_id = memory
    # Rebuild a shelf from the project's own files, then exercise the real HTTP API.
    with TestClient(create_app(tmp_path / "other.db", test=True)) as client:
        p = client.post("/api/v1/projects", json={"path": str(root)}).json()
        assert p["id"] == project_id
        url = f"/api/v1/projects/{project_id}"
        metadata = json.loads((root / ".stash/project.json").read_text())
        metadata["description"] = "Edited without the website"
        (root / ".stash/project.json").write_text(json.dumps(metadata))
        assert client.get(url).json()["description"] == "Edited without the website"
        (root / ".stash/docs/brief.md").write_text("# Plain Markdown brief\n")
        doc = client.get(url + "/document", params={"path": ".stash/docs/brief.md"})
        assert doc.status_code == 200 and "Plain Markdown brief" in doc.json()["html"]
        assert ".stash/docs/brief.md" in client.get(url + "/docs").json()["files"]
        handoff = client.post(url + "/handoffs", json={"summary": "Readable history", "next_actions": "Continue"}).json()
        rendered = client.get(url + "/document", params={"path": f".stash/handoffs/{handoff['id']}.md"})
        assert "Readable history" in rendered.json()["html"]
        assert "stash-record" not in rendered.json()["html"]  # storage comments don't clutter prose


def test_missing_legacy_project_can_migrate_at_updated_path(tmp_path):
    old_path = tmp_path / "old-location"
    moved = tmp_path / "new-location"
    moved.mkdir()
    (moved / "README.md").write_text("# Source already moved by its owner")
    project_id = uid()
    engine, factory = open_database(tmp_path / "shelf.db")
    with factory() as db:
        db.add(Project(id=project_id, path=str(old_path), name="Moved legacy", details={"description": "Preserve description"}))
        db.commit()
        svc.prepare_registry(db)
        project = svc.get_project(db, project_id)
        data = svc.project_dict(db, project)
        result = svc.update_project(db, project, patch(data, path=str(moved)))
        assert result["id"] == project_id and result["description"] == "Preserve description"
        assert result["availability"] == "available"
        assert (moved / ".stash/project.json").exists()
        assert not old_path.exists()
        assert db.get(Project, project_id) is None
    engine.dispose()
