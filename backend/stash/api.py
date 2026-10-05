from contextlib import asynccontextmanager
import asyncio
import mimetypes
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import services as svc
from . import sessions as session_svc
from .schemas import SessionStart, CheckpointInput, SessionTask, HookObservation, WatcherConfig
from . import observations, watcher, assessments
from .schemas import AssessmentRequest, AssessmentApproval, AssessmentRefinement, ProjectCreation
from .db import data_dir, open_database
from .filesystem import Problem, canonical, doc_tree, document, observe, read_bytes, write_document
from .models import now
from .schemas import Actor, Comment, Decision, DocumentWrite, Handoff, IssueInput, IssuePatch, Mutation, ProjectPatch, Registration, SettingsPatch

PREFIX = "/api/v1"


def create_app(db_path=None, dist_dir=None, test=False):
    engine, factory = open_database(db_path or os.environ.get("STASH_DB"))

    @asynccontextmanager
    async def lifespan(app):
        async def recover_integrations():
            from .codex_worker import sweep
            while True:
                await asyncio.to_thread(sweep,factory)
                await asyncio.to_thread(watcher.sweep,factory)
                await asyncio.sleep(3)
        pump=asyncio.create_task(recover_integrations()) if not test else None
        try:
            yield
        finally:
            if pump:
                pump.cancel()
                await asyncio.gather(pump,return_exceptions=True)
            engine.dispose()

    app = FastAPI(title="stash", version="0.1.0", lifespan=lifespan)
    app.state.session_factory = factory
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"] + (["testserver"] if test else []))
    origins = {"http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000", "http://127.0.0.1:8000"}

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if (origin and origin not in origins) or request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"code": "forbidden_origin", "message": "Browser origin is not permitted"}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"code": "json_required", "message": "Mutations require application/json"}, status_code=415)
        return await call_next(request)

    @app.exception_handler(Problem)
    async def problem(_, error):
        return JSONResponse({"code": error.code, "message": error.message}, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation(_, error):
        return JSONResponse({"code": "validation", "message": "Invalid input", "details": [{"field": ".".join(str(x) for x in e["loc"]), "message": e["msg"]} for e in error.errors()]}, status_code=422)

    @app.exception_handler(IntegrityError)
    async def integrity(_, error):
        return JSONResponse({"code": "conflict", "message": "A concurrent update or duplicate path conflicts with this operation"}, status_code=409)

    @app.exception_handler(OperationalError)
    async def busy(_, error):
        return JSONResponse({"code": "database_unavailable", "message": "Database is unavailable or busy; retry shortly"}, status_code=503)

    def db():
        with factory() as session:
            svc.prepare_registry(session)
            yield session

    @app.get(PREFIX + "/health")
    def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.get(PREFIX + "/settings")
    def settings(session=Depends(db)):
        return svc.settings(session)

    @app.put(PREFIX + "/settings")
    def settings_update(payload: SettingsPatch, session=Depends(db)):
        return svc.update_settings(session, payload)

    @app.get(PREFIX + "/discover")
    def discover(session=Depends(db)):
        return svc.discover(session)

    @app.post(PREFIX + "/rescan")
    def rescan(payload: Mutation, session=Depends(db)):
        for p in svc.all_projects(session):
            p.availability, p.observations = observe(p)
        session.commit()
        return {"projects": [svc.project_dict(session, p) for p in svc.all_projects(session)], "candidates": svc.discover(session) if svc.settings(session)["master_folder"] else []}

    @app.post(PREFIX + "/projects")
    def register(payload: Registration, session=Depends(db)):
        return svc.project_dict(session, svc.register(session, payload))

    @app.post(PREFIX + "/projects/create")
    def create_project(payload: ProjectCreation, session=Depends(db)):
        target = Path(payload.path).expanduser()
        if not target.is_absolute() or not target.name or not target.parent.is_dir():
            raise Problem("invalid_path", "Choose a new folder inside an existing parent directory")
        try:
            target.mkdir(exist_ok=False)
        except FileExistsError:
            raise Problem("conflict", "Folder already exists; register it as an existing project", 409)
        except OSError:
            raise Problem("inaccessible", "Cannot create the project directory", 403)
        return svc.project_dict(session, svc.register(session, Registration(path=str(target.resolve()), actor=payload.actor)))

    @app.get(PREFIX + "/projects/{project_id}/assessments")
    def assessment_history(project_id: str, session=Depends(db)):
        return assessments.history(svc.get_project(session, project_id))

    @app.post(PREFIX + "/projects/{project_id}/assessments")
    def assess_project(project_id: str, payload: AssessmentRequest, session=Depends(db)):
        return assessments.assess(session, svc.get_project(session, project_id), payload)

    @app.put(PREFIX + "/projects/{project_id}/assessments/{assessment_id}")
    def refine_assessment(project_id: str, assessment_id: str, payload: AssessmentRefinement, session=Depends(db)):
        return assessments.refine(session, svc.get_project(session, project_id), assessment_id, payload)

    @app.post(PREFIX + "/projects/{project_id}/assessments/{assessment_id}/approve")
    def approve_assessment(project_id: str, assessment_id: str, payload: AssessmentApproval, session=Depends(db)):
        return assessments.approve(session, svc.get_project(session, project_id), assessment_id, payload)

    @app.get(PREFIX + "/resolve")
    def resolve(path: str, session=Depends(db)):
        target = canonical(path)
        matches = [p for p in svc.all_projects(session) if target == Path(p.path) or Path(p.path) in target.parents]
        if not matches:
            raise Problem("unresolved_project", "Current directory is not registered. Register it or pass --project ID", 404)
        return svc.project_dict(session, max(matches, key=lambda p: len(Path(p.path).parts)))

    @app.get(PREFIX + "/projects")
    def projects(q: str = "", status: str = "", tag: str = "", sort: str = "recent", opened: bool = False, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), session=Depends(db)):
        items = [svc.project_dict(session, p) for p in svc.all_projects(session)]
        items = [p for p in items if (not status or p["status"] == status) and (not tag or tag in p.get("tags", []) + p.get("stack", [])) and (not opened or p["last_opened_at"]) and q.lower() in " ".join([p["name"], p.get("description", ""), *p.get("tags", []), *p.get("stack", [])]).lower()]
        field = {"recent": "last_activity_at", "name": "name", "added": "created_at", "opened": "last_opened_at"}.get(sort, "last_activity_at")
        items.sort(key=lambda p: (str(p[field] or "").lower(), p["id"]), reverse=field != "name")
        return {"items": items[offset:offset + limit], "total": len(items)}

    @app.get(PREFIX + "/shelf-summary")
    def shelf_summary(session=Depends(db)):
        items = [svc.project_dict(session, p) for p in svc.all_projects(session)]
        return {"total": len(items), "statuses": {status: sum(p["status"] == status for p in items) for status in ["active", "paused", "archived"]}, "opened": sum(bool(p["last_opened_at"]) for p in items), "tags": sorted({tag for p in items for tag in p.get("tags", []) + p.get("stack", [])})}

    @app.get(PREFIX + "/projects/{project_id}")
    def project(project_id: str, session=Depends(db)):
        return svc.project_dict(session, svc.get_project(session, project_id))

    @app.put(PREFIX + "/projects/{project_id}")
    def project_update(project_id: str, payload: ProjectPatch, session=Depends(db)):
        return svc.update_project(session, svc.get_project(session, project_id), payload)

    @app.post(PREFIX + "/projects/{project_id}/opened")
    def opened(project_id: str, payload: Mutation, session=Depends(db)):
        p = svc.get_project(session, project_id)
        p.last_opened_at = now()
        session.commit()
        return svc.project_dict(session, p)

    @app.post(PREFIX + "/projects/{project_id}/refresh")
    def refresh(project_id: str, payload: Mutation, session=Depends(db)):
        p = svc.get_project(session, project_id)
        p.availability, p.observations = observe(p)
        session.commit()
        return svc.project_dict(session, p)

    @app.delete(PREFIX + "/projects/{project_id}")
    def remove(project_id: str, payload: Mutation, revision: str = Query(min_length=1, max_length=64), session=Depends(db)):
        return svc.remove_project(session, svc.get_project(session, project_id), revision)

    @app.get(PREFIX + "/projects/{project_id}/docs")
    def documents(project_id: str, session=Depends(db)):
        return doc_tree(svc.get_project(session, project_id))

    @app.get(PREFIX + "/projects/{project_id}/document")
    def read_document(project_id: str, path: str, session=Depends(db)):
        return document(svc.get_project(session, project_id), path)

    @app.put(PREFIX + "/projects/{project_id}/document")
    def save_document(project_id: str, payload: DocumentWrite, session=Depends(db)):
        p = svc.get_project(session, project_id)
        result = svc.save_document(session, p, payload, Path(db_path).parent / "locks" if db_path else data_dir() / "locks")
        session.commit()
        return result

    @app.get(PREFIX + "/projects/{project_id}/screenshot")
    def screenshot(project_id: str, session=Depends(db)):
        p = svc.get_project(session, project_id)
        path = p.details.get("screenshot", "")
        return Response(read_bytes(p, path, image=True), media_type=mimetypes.guess_type(path)[0] or "application/octet-stream", headers={"X-Content-Type-Options": "nosniff"})

    @app.get(PREFIX + "/projects/{project_id}/issues")
    def issues(project_id: str, q: str = "", status: str = "", type: str = "", priority: str = "", label: str = "", limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), session=Depends(db)):
        project = svc.get_project(session, project_id)
        items = svc.list_issues(session, project)
        items = [i for i in items if (not status or i["status"] == status) and (not type or i["type"] == type) and (not priority or i["priority"] == priority) and (not label or label in i.get("labels", [])) and q.lower() in f"{i['number']} {i['title']} {i.get('description', '')}".lower()]
        return {"items": items[offset:offset + limit], "total": len(items)}

    @app.post(PREFIX + "/projects/{project_id}/issues")
    def issue_create(project_id: str, payload: IssueInput, session=Depends(db)):
        return svc.create_issue(session, svc.get_project(session, project_id), payload)

    @app.get(PREFIX + "/projects/{project_id}/issues/{issue_id}")
    def issue(project_id: str, issue_id: str, session=Depends(db)):
        return svc.issue_dict(svc.get_issue(session, project_id, issue_id))

    @app.put(PREFIX + "/projects/{project_id}/issues/{issue_id}")
    def issue_update(project_id: str, issue_id: str, payload: IssuePatch, session=Depends(db)):
        return svc.update_issue(session, svc.get_project(session, project_id), svc.get_issue(session, project_id, issue_id), payload)

    @app.get(PREFIX + "/projects/{project_id}/issues/{issue_id}/comments")
    def comments(project_id: str, issue_id: str, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), session=Depends(db)):
        svc.get_issue(session, project_id, issue_id)
        return svc.records(session, project_id, "comment", limit, offset, issue_id)

    @app.post(PREFIX + "/projects/{project_id}/issues/{issue_id}/comments")
    def comment_create(project_id: str, issue_id: str, payload: Comment, idempotency_key: str | None = Header(default=None, max_length=200), session=Depends(db)):
        svc.get_issue(session, project_id, issue_id)
        return svc.add_record(session, svc.get_project(session, project_id), "comment", payload, issue_id, idempotency_key)

    @app.get(PREFIX + "/projects/{project_id}/decisions")
    def decisions(project_id: str, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), session=Depends(db)):
        svc.get_project(session, project_id)
        return svc.records(session, project_id, "decision", limit, offset)

    @app.post(PREFIX + "/projects/{project_id}/decisions")
    def decision_create(project_id: str, payload: Decision, idempotency_key: str | None = Header(default=None, max_length=200), session=Depends(db)):
        return svc.add_record(session, svc.get_project(session, project_id), "decision", payload, request_key=idempotency_key)

    @app.get(PREFIX + "/projects/{project_id}/handoffs")
    def handoffs(project_id: str, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), session=Depends(db)):
        svc.get_project(session, project_id)
        return svc.records(session, project_id, "handoff", limit, offset)

    @app.post(PREFIX + "/projects/{project_id}/handoffs")
    def handoff_create(project_id: str, payload: Handoff, idempotency_key: str | None = Header(default=None, max_length=200), session=Depends(db)):
        return svc.add_record(session, svc.get_project(session, project_id), "handoff", payload, request_key=idempotency_key)

    @app.get(PREFIX + "/projects/{project_id}/records/{record_id}")
    def record(project_id: str, record_id: str, session=Depends(db)):
        return svc.get_record(session, project_id, record_id)

    @app.post(PREFIX + "/projects/{project_id}/sessions")
    def session_start(project_id: str, payload: SessionStart, session=Depends(db)):
        return session_svc.start_session(svc.get_project(session, project_id), payload)

    @app.put(PREFIX + "/projects/{project_id}/sessions/{session_id}/task")
    def session_task(project_id: str, session_id: str, payload: SessionTask, session=Depends(db)):
        return session_svc.update_task(svc.get_project(session,project_id),session_id,payload)

    @app.get(PREFIX + "/projects/{project_id}/integrations/codex")
    def integration_status(project_id: str, session=Depends(db)):
        from .codex_runtime import status
        try: return status(svc.get_project(session,project_id).path)
        except (OSError,ValueError): raise Problem('inaccessible_integration','Integration state is inaccessible or invalid',403)

    @app.post(PREFIX + "/projects/{project_id}/observations")
    def observation_create(project_id: str, payload: HookObservation, session=Depends(db)):
        return observations.ingest(svc.get_project(session,project_id),payload)

    @app.get(PREFIX + "/projects/{project_id}/observations")
    def observation_list(project_id: str, limit: int = Query(50,ge=1,le=500), session=Depends(db)):
        return observations.list_observations(svc.get_project(session,project_id),limit)

    @app.get(PREFIX + "/projects/{project_id}/watcher")
    def watcher_status(project_id: str, session=Depends(db)):
        return watcher.status(svc.get_project(session, project_id))

    @app.put(PREFIX + "/projects/{project_id}/watcher")
    def watcher_configure(project_id: str, payload: WatcherConfig, session=Depends(db)):
        return watcher.configure(svc.get_project(session, project_id), payload.enabled, payload.actor)

    @app.get(PREFIX + "/projects/{project_id}/file-observations")
    def file_observations(project_id: str, limit: int = Query(50, ge=1, le=10000), session=Depends(db)):
        return watcher.list_observations(svc.get_project(session, project_id), limit)

    @app.get(PREFIX + "/projects/{project_id}/sessions")
    def session_list(project_id: str, session=Depends(db)):
        return session_svc.list_sessions(svc.get_project(session, project_id))

    @app.get(PREFIX + "/projects/{project_id}/sessions/{session_id}")
    def session_detail(project_id: str, session_id: str, session=Depends(db)):
        return session_svc.session_detail(svc.get_project(session, project_id), session_id)

    @app.post(PREFIX + "/projects/{project_id}/sessions/{session_id}/checkpoints")
    def checkpoint_create(project_id: str, session_id: str, payload: CheckpointInput, session=Depends(db)):
        return session_svc.save_checkpoint(svc.get_project(session, project_id), session_id, payload)

    @app.get(PREFIX + "/projects/{project_id}/resume")
    def session_resume(project_id: str, session=Depends(db)):
        return session_svc.resume(svc.get_project(session, project_id))

    @app.get(PREFIX + "/projects/{project_id}/context")
    def context(project_id: str, session=Depends(db)):
        data = svc.context_data(session, svc.get_project(session, project_id))
        return {**data, "markdown": svc.context_markdown(data)}

    @app.get(PREFIX + "/projects/{project_id}/activity")
    def activity(project_id: str, kind: str = "", actor: str = "", since: str = "", until: str = "", limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), session=Depends(db)):
        p = svc.get_project(session, project_id)
        items = svc.activities(session, p)
        items = [i for i in items if (not kind or i["kind"] == kind) and (not since or i["created_at"] >= since) and (not until or i["created_at"] <= until) and (not actor or i["actor"]["kind"] == actor)]
        return {"items": items[offset:offset + limit], "total": len(items)}

    @app.get(PREFIX + "/projects/{project_id}/export")
    def export(project_id: str, format: str = "json", session=Depends(db)):
        data = svc.export_project(session, svc.get_project(session, project_id))
        if format == "markdown":
            return Response(svc.export_markdown(data), media_type="text/markdown", headers={"Content-Disposition": 'attachment; filename="stash-export.md"'})
        return JSONResponse(data, headers={"Content-Disposition": 'attachment; filename="stash-export.json"'})

    frontend = Path(dist_dir or os.environ.get("STASH_FRONTEND", "dist")).resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def frontend_route(path: str):
        if path.startswith(("api/", "docs/", "openapi")):
            raise Problem("not_found", "Endpoint not found", 404)
        candidate = (frontend / path).resolve()
        if frontend not in candidate.parents and candidate != frontend:
            raise Problem("forbidden_path", "Invalid path", 403)
        if candidate.is_file():
            return FileResponse(candidate)
        if (frontend / "index.html").is_file():
            return FileResponse(frontend / "index.html")
        raise Problem("frontend_unbuilt", "Frontend is not built. Run npm run build, or use Vite on port 3000", 404)

    return app
