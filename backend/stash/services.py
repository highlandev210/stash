"""Shared business rules. FolderStore owns project records; SQLite locates them."""
from pathlib import Path
import hashlib
import json

from sqlalchemy import delete, select, update

from .filesystem import Problem, canonical, observe, relative, SKIP
from .models import Activity, Issue, Project, Record, Registry, Setting, now, uid
from .schemas import ProjectPatch
from .store import BRIEF, METADATA_FIELDS, FolderStore, digest, json_bytes, markdown_bytes, valid_id


DOC_ROOTS = ["README.md", "docs", ".stash/docs", ".stash/decisions", ".stash/handoffs"]
WRITE_ROOTS = ["docs", ".stash/docs"]


def defaults(name, path):
    return ProjectPatch(revision="new", name=name, path=path, doc_roots=DOC_ROOTS, writable_doc_roots=WRITE_ROOTS).model_dump(exclude={"actor", "revision", "path"})


def actor_dict(actor):
    return actor.model_dump() if hasattr(actor, "model_dump") else actor


def new_event(project_id, kind, record_id, summary, actor):
    return {"id": uid(), "project_id": project_id, "kind": kind, "record_id": record_id, "summary": summary, "actor": actor_dict(actor), "created_at": now()}


def prepare_registry(db):
    """Safely migrate accessible legacy projects, retaining failed rows for retry.

    The disk write finishes and validates before database records are removed.
    Crashes between these steps can retry without clobbering project files.
    """
    for legacy in list(db.scalars(select(Project))):
        if db.get(Setting, f"removed-legacy:{legacy.id}"):
            continue
        registry = db.get(Registry, legacy.id)
        if not registry:
            values = {**defaults(legacy.name, legacy.path), **legacy.details, "id": legacy.id, "name": legacy.name, "status": legacy.status, "created_at": legacy.created_at, "tracker_updated_at": legacy.updated_at, "revision": "migration-pending", "open_issue_count": 0}
            registry = Registry(id=legacy.id, path=legacy.path, observations=legacy.observations, availability=legacy.availability, last_opened_at=legacy.last_opened_at, summary=values)
            db.add(registry)
            db.flush()
        try:
            canonical(legacy.path)
            data = {**registry.summary, "doc_roots": list(dict.fromkeys(legacy.details.get("doc_roots", ["README.md", "docs"]) + DOC_ROOTS[2:])), "writable_doc_roots": list(dict.fromkeys(legacy.details.get("writable_doc_roots", ["docs"]) + [".stash/docs"]))}
            issues = [{**i.details, "id": i.id, "project_id": i.project_id, "number": i.number, "title": i.title, "type": i.type, "status": i.status, "priority": i.priority, "creator": i.creator, "created_at": i.created_at, "updated_at": i.updated_at} for i in db.scalars(select(Issue).where(Issue.project_id == legacy.id))]
            records = [{**r.data, "id": r.id, "project_id": r.project_id, "issue_id": r.issue_id, "kind": r.kind, "actor": r.actor, "created_at": r.created_at, "request_key": r.request_key} for r in db.scalars(select(Record).where(Record.project_id == legacy.id))]
            events = [{k: getattr(e, k) for k in ["id", "project_id", "kind", "record_id", "summary", "actor", "created_at"]} for e in db.scalars(select(Activity).where(Activity.project_id == legacy.id).order_by(Activity.created_at, Activity.id))]
            with FolderStore(legacy.path).locked(create=True) as store:
                store.initialize(data, issues, records, events)
                # Verify identities/counts before retiring the old authoritative rows.
                if {i["id"] for i in store.issues(legacy.id)} != {i["id"] for i in issues}:
                    raise Problem("migration_conflict", "Issue files conflict with the legacy database", 409)
                for kind in ["comment", "decision", "handoff"]:
                    if {r["id"] for r in store.records(kind, legacy.id)} != {r["id"] for r in records if r["kind"] == kind}:
                        raise Problem("migration_conflict", "Record files conflict with the legacy database", 409)
            db.execute(delete(Project).where(Project.id == legacy.id))
            registry.summary = {**data, "migration_pending": False}
        except Problem as error:
            registry.summary = {**registry.summary, "migration_pending": True, "storage_error": error.message}
    db.commit()


def all_projects(db):
    return list(db.scalars(select(Registry).order_by(Registry.id)))


def get_project(db, project_id):
    item = db.get(Registry, project_id)
    if not item:
        raise Problem("not_found", "Project not found", 404)
    project_dict(db, item)
    return item


def store_for(project):
    if project.summary.get("migration_pending"):
        raise Problem("migration_pending", project.summary.get("storage_error", "Project migration is pending"), 409)
    return FolderStore(project.path)


def project_dict(db, project):
    try:
        if project.summary.get("migration_pending"):
            raise Problem("migration_pending", project.summary["storage_error"], 409)
        with FolderStore(project.path).locked() as store:
            data = store.read_project(project.id)
            count = sum(i["status"] not in {"done", "cancelled"} for i in store.issues(project.id))
            activity = store.activity()
            tracker = max([data["tracker_updated_at"]] + [event["created_at"] for event in activity])
            # Human edits have filesystem mtimes even without a generated tracker event.
            source_time = 0
            tracked_paths = ["project.json", BRIEF]
            for directory, suffix in [("issues", ".json"), ("comments", ".json"), ("decisions", ".md"), ("handoffs", ".md")]:
                tracked_paths += store.names(directory, suffix)
            for path in tracked_paths:
                parent, name = store._parent(path)
                try:
                    import os
                    source_time = max(source_time, os.stat(name, dir_fd=parent, follow_symlinks=False).st_mtime)
                finally:
                    os.close(parent)
            from datetime import datetime, timezone
            tracker = max(tracker, datetime.fromtimestamp(source_time, timezone.utc).isoformat())
            data.update(tracker_updated_at=tracker, open_issue_count=count, storage_error=None, migration_pending=False)
        project.summary = data
        project.availability = "available"
    except Problem as error:
        data = dict(project.summary)
        data.update(storage_error=error.message)
        project.availability = "missing" if not Path(project.path).exists() else "inaccessible"
    code_time = max(filter(None, [project.observations.get("code_activity_at"), project.observations.get("git", {}).get("committed_at")]), default=None)
    tracker = data.get("tracker_updated_at", data.get("created_at", now()))
    data.update(id=project.id, path=project.path, availability=project.availability, observations=project.observations, code_activity_at=code_time, last_activity_at=max(filter(None, [tracker, code_time])), activity_source="code" if code_time and code_time > tracker else "tracker", last_opened_at=project.last_opened_at)
    project.details = data
    db.commit()
    return data


def register(db, payload):
    path = str(canonical(payload.path))
    legacy = db.scalar(select(Project).where(Project.path == path))
    if legacy:
        tombstone = db.get(Setting, f"removed-legacy:{legacy.id}")
        if tombstone:
            db.delete(tombstone)
            db.commit()
        prepare_registry(db)
        pending = db.get(Registry, legacy.id)
        if pending and pending.summary.get("migration_pending"):
            raise Problem("migration_pending", pending.summary.get("storage_error", "Migration must complete before registration"), 409)
    with FolderStore(path).locked(create=True) as store:
        existing = store.json("project.json", required=False)
        if existing:
            data = store.read_project()
        else:
            project_id = uid()
            data = {**defaults(Path(path).name, path), "id": project_id, "created_at": now(), "tracker_updated_at": now()}
            store.initialize(data, events=[new_event(project_id, "registration", project_id, "Project memory initialized", payload.actor)])
            data = store.read_project(project_id)
    registered_path = db.scalar(select(Registry).where(Registry.path == path))
    if registered_path and registered_path.id != data["id"]:
        raise Problem("identity_conflict", "This directory's .stash ID differs from its registration", 409)
    old = db.get(Registry, data["id"])
    if old and old.path != path and Path(old.path).exists():
        raise Problem("duplicate_identity", "Another available folder has this project ID. Move the original folder or give a clone a new project ID", 409)
    if old:
        old.path = path
        project = old
    else:
        project = Registry(id=data["id"], path=path, summary=data)
        db.add(project)
    db.flush()
    project.details = data
    project.availability, project.observations = observe(project)
    db.commit()
    return project


def update_project(db, project, payload):
    new_path = project.path if payload.path == project.path else str(canonical(payload.path))
    conflict = db.scalar(select(Registry).where(Registry.path == new_path, Registry.id != project.id))
    if conflict:
        raise Problem("conflict", "Directory is already registered to another project", 409)
    if project.summary.get("migration_pending") and new_path != project.path:
        if payload.revision != project.summary.get("revision"):
            raise Problem("conflict", "Project changed; reload before updating its location", 409)
        legacy = db.get(Project, project.id)
        if legacy:
            legacy.path = new_path
            project.path = new_path
            db.commit()
            prepare_registry(db)
            current = project_dict(db, project)
            if current.get("migration_pending"):
                raise Problem("migration_pending", current.get("storage_error", "Migration could not complete"), 409)
            payload = payload.model_copy(update={"revision": current["revision"]})
    for item in payload.doc_roots + payload.writable_doc_roots:
        relative(item)
    if payload.screenshot:
        relative(payload.screenshot)
    with FolderStore(new_path).locked() as store:
        current = store.read_project(project.id)
        if current["revision"] != payload.revision:
            raise Problem("conflict", "Project files changed. Reload before applying your draft", 409)
        metadata = {k: v for k, v in payload.model_dump().items() if k in METADATA_FIELDS}
        metadata.update(schema_version=1, id=project.id, created_at=current["created_at"], updated_at=now())
        store.transaction({"project.json": (store.project_snapshot["project.json"], json_bytes(metadata)), BRIEF: (store.project_snapshot[BRIEF], payload.brief.encode("utf-8"))}, new_event(project.id, "metadata", project.id, "Project metadata updated", payload.actor))
    project.path = new_path
    project.details = payload.model_dump()
    project.availability, project.observations = observe(project)
    db.commit()
    return project_dict(db, project)


def remove_project(db, project, revision):
    current = project_dict(db, project)
    if current.get("revision") != revision:
        raise Problem("conflict", "Project changed; reload before removing", 409)
    if db.get(Project, project.id):
        # Retain legacy records for a folder that could not yet migrate, without recreating its shelf entry.
        db.add(Setting(key=f"removed-legacy:{project.id}", value={"path": project.path}))
    db.delete(project)
    db.commit()
    return {"removed": True, "source_files_deleted": False, "project_memory_deleted": False}


def event(db, project, kind, record_id, summary, actor):
    with store_for(project).locked() as store:
        store.read_project(project.id)
        store.transaction({}, new_event(project.id, kind, record_id, summary, actor))


def settings(db):
    item = db.get(Setting, "app")
    return {"master_folder": "", "identity": "You", "revision": 0} if not item else {**item.value, "revision": item.revision}


def update_settings(db, payload):
    values = {"master_folder": str(canonical(payload.master_folder)) if payload.master_folder else "", "identity": payload.identity}
    if payload.revision == 0:
        if db.get(Setting, "app"):
            raise Problem("conflict", "Settings changed; reload first", 409)
        db.add(Setting(key="app", value=values))
    else:
        result = db.execute(update(Setting).where(Setting.key == "app", Setting.revision == payload.revision).values(value=values, revision=Setting.revision + 1))
        if not result.rowcount:
            raise Problem("conflict", "Settings changed; reload first", 409)
    db.commit()
    return settings(db)


def discover(db):
    master = settings(db)["master_folder"]
    if not master:
        raise Problem("master_not_configured", "Configure a master folder first")
    root = canonical(master)
    candidates = []
    try:
        children = sorted(root.iterdir(), key=lambda p: p.name.lower())
        for path in children[:2000]:
            if path.name.startswith(".") or path.name in SKIP or not path.is_dir():
                continue
            try:
                resolved = str(canonical(str(path)))
                project = db.scalar(select(Registry).where(Registry.path == resolved))
                candidates.append({"name": path.name, "path": resolved, "project_id": project.id if project else None, "error": None})
            except Problem as error:
                candidates.append({"name": path.name, "path": str(path), "project_id": None, "error": error.message})
    except OSError:
        raise Problem("inaccessible", "Master folder cannot be scanned")
    return candidates


def get_issue(db, project_id, issue_id):
    project = get_project(db, project_id)
    with store_for(project).locked() as store:
        store.read_project(project.id)
        return store.issue(issue_id, project_id)


def issue_dict(item):
    return dict(item)


def list_issues(db, project):
    with store_for(project).locked() as store:
        store.read_project(project.id)
        return sorted(store.issues(project.id), key=lambda i: i["number"], reverse=True)


def create_issue(db, project, payload):
    with store_for(project).locked() as store:
        store.read_project(project.id)
        number = max((i["number"] for i in store.issues(project.id)), default=0) + 1
        item = {**payload.model_dump(exclude={"actor"}), "id": uid(), "project_id": project.id, "number": number, "creator": actor_dict(payload.actor), "created_at": now(), "updated_at": now()}
        path = f"issues/{item['id']}.json"
        store.transaction({path: (None, json_bytes(item))}, new_event(project.id, "issue", item["id"], f"Issue #{number} created: {item['title']}", payload.actor))
        return store.issue(item["id"], project.id)


def update_issue(db, project, item, payload):
    with store_for(project).locked() as store:
        store.read_project(project.id)
        current = store.issue(item["id"], project.id)
        if current["revision"] != payload.revision:
            raise Problem("conflict", "Issue file changed. Reload before applying your draft", 409)
        updated = {**current, **payload.model_dump(exclude={"actor", "revision"}), "updated_at": now()}
        updated.pop("revision", None)
        path = f"issues/{item['id']}.json"
        store.transaction({path: (store.issue_snapshots[item["id"]], json_bytes(updated))}, new_event(project.id, "issue", item["id"], f"Issue #{current['number']} updated: {payload.status}", payload.actor))
        return store.issue(item["id"], project.id)


def records(db, project_id, kind, limit=100, offset=0, issue_id=None):
    project = get_project(db, project_id)
    with store_for(project).locked() as store:
        store.read_project(project.id)
        items = store.records(kind, project_id)
        if issue_id:
            items = [i for i in items if i.get("issue_id") == issue_id]
        return items[offset:offset + limit]


def record_dict(item):
    return {k: v for k, v in item.items() if k != "request_key"}


def get_record(db, project_id, record_id):
    valid_id(record_id)
    for kind in ["decision", "handoff", "comment"]:
        for item in records(db, project_id, kind, 10000):
            if item["id"] == record_id:
                return record_dict(item)
    from .assessments import history
    for assessment in history(get_project(db, project_id)):
        if assessment['id'] == record_id:
            return {**assessment, 'kind': 'assessment'}
    from .observations import list_observations
    for observation in list_observations(get_project(db,project_id),10000):
        if observation['id']==record_id:
            return {**observation,'kind':'observation','created_at':observation['observed_at']}
    from .watcher import list_observations as list_file_observations
    for observation in list_file_observations(get_project(db,project_id),10000):
        if observation["id"] == record_id:
            return {**observation,"kind":"file_observation","created_at":observation["observed_at"]}
    from .sessions import list_sessions, session_detail
    project = get_project(db, project_id)
    for session in list_sessions(project):
        if session['id'] == record_id:
            return {**session, 'kind': 'session', 'session_id': session['id']}
        for checkpoint in session_detail(project, session['id'])['checkpoints']:
            if checkpoint['id'] == record_id:
                return {**checkpoint, 'kind': 'checkpoint'}
    raise Problem("not_found", "Record not found in this project", 404)


def add_record(db, project, kind, payload, issue_id=None, request_key=None):
    key = hashlib.sha256(f"{project.id}:{kind}:{issue_id}:{request_key}".encode()).hexdigest() if request_key else None
    data = payload.model_dump(exclude={"actor"})
    with store_for(project).locked() as store:
        store.read_project(project.id)
        if issue_id:
            store.issue(issue_id, project.id)
        existing = store.records(kind, project.id)
        old = next((i for i in existing if key and i.get("request_key") == key), None)
        if old:
            if any(old.get(k) != v for k, v in data.items()) or old["actor"] != actor_dict(payload.actor):
                raise Problem("conflict", "Idempotency key already used for different content", 409)
            return record_dict(old)
        item = {**data, "id": uid(), "project_id": project.id, "issue_id": issue_id, "kind": kind, "actor": actor_dict(payload.actor), "created_at": now(), "request_key": key}
        directory = {"comment": "comments", "decision": "decisions", "handoff": "handoffs"}[kind]
        path = f"{directory}/{item['id']}{'.json' if kind == 'comment' else '.md'}"
        content = json_bytes(item) if kind == "comment" else markdown_bytes(item)
        store.transaction({path: (None, content)}, new_event(project.id, kind, issue_id or item["id"], {"decision": "Decision recorded", "handoff": "Session handoff saved", "comment": "Comment added"}[kind], payload.actor))
        return record_dict(item)


def activities(db, project):
    with store_for(project).locked() as store:
        store.read_project(project.id)
        return sorted(store.activity(), key=lambda i: (i["created_at"], i["id"]), reverse=True)


def context_data(db, project):
    from .sessions import resume
    from .assessments import history
    from .observations import list_observations
    from .watcher import list_observations as list_file_observations
    return {"assessments": history(project)[:10] if Path(project.path).is_dir() else [], "file_observations": list_file_observations(project) if Path(project.path).is_dir() else [], "project": project_dict(db, project), "resume": resume(project) if Path(project.path).is_dir() else None, "observations": list_observations(project) if Path(project.path).is_dir() else [], "issues": [i for i in list_issues(db, project) if i["status"] not in {"done", "cancelled"}][:50], "decisions": [record_dict(i) for i in records(db, project.id, "decision", 10)], "handoffs": [record_dict(i) for i in records(db, project.id, "handoff", 20)]}


def export_project(db, project):
    from .sessions import export_sessions
    from .observations import read_observations
    from .watcher import read_observations as read_file_observations
    with store_for(project).locked() as store:
        data = store.read_project(project.id)
        return {"format_version": 5, "assessments": [store.json(name) for name in store.names("assessments", ".json")], "file_observations": read_file_observations(store,project.id), "observations": read_observations(store,project.id), "sessions": export_sessions(store, project.id), "exported_at": now(), "project": {**data, "path": project.path}, "issues": store.issues(project.id), "records": [record_dict(i) for kind in ["comment", "decision", "handoff"] for i in store.records(kind, project.id)], "activity": store.activity()}
def context_markdown(data):
    p = data["project"]
    lines = [f"# {p['name']} — agent context", f"Project ID: {p['id']}", f"Path: {p['path']} ({p['availability']})", f"Tracker updated: {p['tracker_updated_at']}", "", "Recorded information may be stale. Inspect the repository before relying on it.", "", "## Project brief", p.get("brief") or p.get("purpose") or p.get("description") or "No brief recorded.", "", "## Current focus", p.get("focus") or "Not recorded.", "", "## Next step", p.get("next_step") or "Not recorded.", "", "## Unresolved issues"]
    for issue in data["issues"]:
        lines.append(f"- #{issue['number']} {issue['title']} ({issue['status']}, {issue['priority']}) — ID {issue['id']}")
    if data.get("resume"):
        r = data["resume"]
        s, c = r["session"], r["checkpoint"]
        lines += ["", "## Resume checkpoint", f"Session {s['id']} · {s['actor']['name']} · {s['status']} · started {s['created_at']}", f"Task: {s['task']}", "No final handoff checkpoint: unfinished session." if s['status'] == 'incomplete' else "Final handoff checkpoint recorded."]
        if c:
            lines += [f"Checkpoint {c['id']} · {c['created_at']} · {c['actor']['name']}"]
            for key, value in c['explanation'].items():
                lines += [f"{key}: {value if value is not None else 'Not recorded'}"]
        baseline = c['observation'] if c else s['observation']
        lines += [f"Repository at checkpoint: branch {baseline['branch']}, HEAD {baseline['head']}, dirty {baseline['dirty']}", "Changes since checkpoint: " + json.dumps(r['changes']), "Observation warnings: " + json.dumps(r['current_observation']['warnings']), f"Incomplete sessions: {len(r['incomplete_sessions'])}"]
    if data["handoffs"]:
        h = data["handoffs"][0]
        lines += ["", "## Latest handoff", f"{h['created_at']} · {h['actor']['name']} ({h['actor']['kind']}) · commit {h.get('commit') or 'not recorded'}"]
        for key in ["summary", "completed_work", "changed_files", "verification", "unresolved_problems", "blockers", "next_actions"]:
            lines += [f"### {key.replace('_', ' ').title()}", h.get(key) or "Not recorded; verification must not be assumed."]
    else:
        lines += ["", "No session handoff recorded."]
    if data.get('observations'):
        lines += ['', '## Recent observed agent events', 'These are facts about lifecycle/tools, not evidence that a task is complete.']
        for item in data['observations'][:10]:
            lines += [f"- {item['observed_at']} · session {item['session_id']} · {item['event']} · tool {item.get('tool')} · exit {item.get('exit_code')} · error {item.get('tool_error')}"]
    if data.get("file_observations"):
        lines += ["", "## Saved file observations", "Observed file changes do not establish task completion or successful verification."]
        for item in data["file_observations"][:5]:
            lines += [f"- {item['observed_at']} · added {item['added']} · modified {item['modified']} · removed {item['removed']}"]
    lines += ["", "## Recent decisions"]
    for item in data["decisions"]:
        lines += [f"- {item['created_at']} · {item['choice']}", f"  Reasoning: {item.get('reasoning') or 'Not recorded'}", f"  Alternatives: {item.get('alternatives') or 'Not recorded'}", f"  Reference: {item.get('reference') or 'Not recorded'}"]
    return "\n".join(lines) + "\n"



def export_markdown(data):
    # Include full records/history, not just the concise agent brief.
    return f"# {data['project']['name']} — complete tracker export\n\nExported {data['exported_at']}. Repository files are not included.\n\n" + "\n\n".join(f"## {key.title()}\n\n```json\n{json.dumps(data[key], indent=2, ensure_ascii=False)}\n```" for key in ["project", "issues", "records", "sessions", "observations", "file_observations", "activity"]) + "\n"




def save_document(db, project, payload, locks_dir):
    from .filesystem import write_document, document, scoped
    # The folder brief and tracker Markdown are coordinated with metadata updates.
    if payload.path.startswith(".stash/"):
        scoped(project, payload.path, write=True)
        relative_path = payload.path.removeprefix(".stash/")
        if not relative_path.startswith("docs/"):
            raise Problem("forbidden_path", "Historical decisions/handoffs are read-only through Docs", 403)
        with store_for(project).locked() as store:
            store.read_project(project.id)
            old = store.read(relative_path)
            revision = digest(old) if old is not None else None
            if revision != payload.revision:
                raise Problem("conflict", "Document changed externally. Reload and compare before saving", 409)
            store.transaction({relative_path: (old, payload.content.encode("utf-8"))}, new_event(project.id, "document", payload.path, f"Document saved: {payload.path}", payload.actor))
        return document(project, payload.path)
    return write_document(project, payload, locks_dir, on_saved=lambda: event(db, project, "document", payload.path, f"Document saved: {payload.path}", payload.actor))
