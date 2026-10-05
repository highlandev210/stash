"""Historical session checkpoints and bounded, read-only repository observations."""
import hashlib
import os
from pathlib import Path
import subprocess

from pydantic import ValidationError, BaseModel
from datetime import datetime

from .filesystem import Problem, allowed_name, parent_fd, read_at
from .models import now
from .schemas import SessionStart, CheckpointInput, Actor
from .store import FolderStore, digest, json_bytes, valid_id


class Observation(BaseModel):
    captured_at: datetime
    git: bool
    branch: str | None
    head: str | None
    working_tree: list[dict[str, str]]
    dirty: bool | None
    fingerprints: dict[str, str]
    warnings: list[str]
    complete: bool


def validate_observation(value):
    observed = Observation.model_validate(value)
    if observed.captured_at.tzinfo is None:
        raise ValueError()
    for path, fingerprint in observed.fingerprints.items():
        parts = Path(path).parts
        if Path(path).is_absolute() or '..' in parts or not all(allowed_name(p) for p in parts):
            raise ValueError()
        if len(fingerprint) != 64 or any(c not in '0123456789abcdef' for c in fingerprint):
            raise ValueError()


def validate_time(value):
    if datetime.fromisoformat(value).tzinfo is None:
        raise ValueError()


def observe_repository(root, include_git=True):
    root = Path(root)
    warnings = []
    env = {**os.environ, 'GIT_OPTIONAL_LOCKS': '0'}
    def git(*args):
        try:
            result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, timeout=5, env=env)
            return result.stdout.decode('utf-8', errors='replace').rstrip('\n') if result.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            warnings.append('Git command unavailable or timed out')
            return None
    top = git('rev-parse', '--show-toplevel') if include_git else None
    is_git = top is not None
    prefix = root.relative_to(Path(top).resolve()).as_posix() if is_git else '.'
    fingerprints = {}
    total = 0
    metadata_bytes = 0
    # Record hashes only, never source bodies. Reuse the repository secret/build exclusions.
    directories = 0
    for current, dirs, files in os.walk(root, followlinks=False, onerror=lambda _: warnings.append('A directory was inaccessible during observation')):
        directories += 1
        if directories > 2000:
            warnings.append('Fingerprint directory limit reached')
            break
        dirs[:] = sorted(d for d in dirs if allowed_name(d) and not (Path(current)/d).is_symlink())
        for name in sorted(files):
            path = Path(current)/name
            if not allowed_name(name) or path.is_symlink() or not path.is_file():
                continue
            if len(fingerprints) >= 5000:
                warnings.append('Fingerprint file limit reached')
                dirs[:] = []
                break
            try:
                relative_name = path.relative_to(root).as_posix()
                if metadata_bytes + len(relative_name.encode('utf-8')) + 80 > 250_000:
                    warnings.append('Fingerprint metadata limit reached')
                    continue
                size = path.stat().st_size
                if size > 2_000_000 or total + size > 50_000_000:
                    warnings.append('Fingerprint byte limit reached; some files omitted')
                    continue
                parent = parent_fd(root, path.relative_to(root))
                leaf = path.name
                try:
                    content = read_at(parent, leaf, 2_000_000)
                finally:
                    os.close(parent)
                if len(content) > 2_000_000:
                    warnings.append('File grew beyond fingerprint limit')
                    continue
                total += len(content)
                fingerprints[relative_name] = hashlib.sha256(content).hexdigest()
                metadata_bytes += len(relative_name.encode('utf-8')) + 80
            except (OSError, Problem):
                warnings.append('A file was inaccessible during observation')
    status = git('status', '--porcelain=v1', '-z', '--untracked-files=all', '--', '.') if is_git else None
    if is_git and status is None:
        warnings.append('Git working-tree status unavailable')
    changed = []
    if status:
        parts = status.split('\0')
        index = 0
        while index < len(parts):
            line = parts[index]
            if len(line) >= 4:
                raw = line[3:]
                if prefix != '.':
                    raw = raw.removeprefix(prefix + '/')
                if all(allowed_name(p) for p in Path(raw).parts):
                    changed.append({'path': raw, 'status': line[:2]})
                if 'R' in line[:2] or 'C' in line[:2]: index += 1
            index += 1
    return {'captured_at': now(), 'git': is_git, 'branch': git('symbolic-ref', '--short', '-q', 'HEAD') if is_git else None, 'head': git('rev-parse', '--verify', 'HEAD') if is_git else None, 'working_tree': changed, 'dirty': bool(status) if is_git and status is not None else None, 'fingerprints': fingerprints, 'warnings': sorted(set(warnings)), 'complete': not warnings}


def read_session(store, project_id, session_id):
    valid_id(session_id)
    path = f'sessions/{session_id}/session.json'
    raw = store.read(path)
    if raw is None: raise Problem('not_found', 'Session not found', 404)
    value = store.json(path)
    try:
        if value['id'] != session_id or value['project_id'] != project_id or value['schema_version'] != 1: raise ValueError()
        SessionStart.model_validate({'id': value['id'], 'task': value['task'], 'actor': value['actor']})
        if value['status'] not in {'incomplete', 'completed'}: raise ValueError()
        validate_time(value['created_at'])
        if value.get('updated_at'): validate_time(value['updated_at'])
        validate_observation(value['observation'])
        if value['latest_checkpoint_id'] is not None: valid_id(value['latest_checkpoint_id'])
    except (KeyError, TypeError, ValueError, ValidationError): raise Problem('invalid_memory', 'Invalid session record', 409)
    return {**value, 'revision': digest(raw)}, raw


def checkpoints(store, project_id, session_id):
    result = []
    for path in store.names(f'sessions/{session_id}/checkpoints', '.json'):
        value = store.json(path)
        try:
            valid_id(value['id'])
            if value['id'] != Path(path).stem or value['project_id'] != project_id or value['session_id'] != session_id: raise ValueError()
            parsed = CheckpointInput.model_validate({**value['explanation'], 'id': value['id'], 'revision': value['base_revision'], 'actor': value['actor']})
            value['explanation'] = parsed.model_dump(exclude={'id', 'revision', 'actor'})
            if value['schema_version'] != 1: raise ValueError()
            validate_time(value['created_at'])
            validate_observation(value['observation'])
        except (KeyError, TypeError, ValueError, ValidationError): raise Problem('invalid_memory', 'Invalid checkpoint record', 409)
        result.append(value)
    return sorted(result, key=lambda c: (c['created_at'], c['id']))


def start_session(project, payload):
    valid_id(payload.id)
    from .services import new_event
    with FolderStore(project.path).locked() as store:
        store.read_project(project.id)
        path = f'sessions/{payload.id}/session.json'
        old = store.read(path)
        if old:
            existing, _ = read_session(store, project.id, payload.id)
            if existing['task'] != payload.task or existing['actor'] != payload.actor.model_dump(): raise Problem('conflict', 'Session ID already used for different intent', 409)
            return existing
        value = {'schema_version': 1, 'origin': payload.origin, 'intent_recorded': payload.origin == 'explicit', 'id': payload.id, 'project_id': project.id, 'actor': payload.actor.model_dump(), 'created_at': now(), 'task': payload.task, 'status': 'incomplete', 'latest_checkpoint_id': None, 'observation': observe_repository(project.path)}
        store.transaction({path: (None, json_bytes(value))}, new_event(project.id, 'session', payload.id, 'Session intent recorded', payload.actor))
        return read_session(store, project.id, payload.id)[0]


def save_checkpoint(project, session_id, payload):
    valid_id(payload.id)
    from .services import new_event
    explanation = payload.model_dump(exclude={'actor','id','revision'})
    with FolderStore(project.path).locked() as store:
        store.read_project(project.id)
        session, raw = read_session(store, project.id, session_id)
        path = f'sessions/{session_id}/checkpoints/{payload.id}.json'
        if store.read(path):
            old = next(c for c in checkpoints(store, project.id, session_id) if c['id'] == payload.id)
            if old['explanation'] != explanation or old['actor'] != payload.actor.model_dump() or old['base_revision'] != payload.revision: raise Problem('conflict', 'Checkpoint ID already used for different content', 409)
            return old
        if session['revision'] != payload.revision: raise Problem('conflict', 'Session changed; reread before checkpointing', 409)
        if session['status'] == 'completed': raise Problem('conflict', 'Completed sessions are historical; start a new session', 409)
        value = {'schema_version':1, 'id':payload.id,'project_id':project.id,'session_id':session_id,'created_at':now(),'actor':payload.actor.model_dump(),'base_revision':payload.revision,'explanation':explanation,'observation':observe_repository(project.path)}
        updated = {k:v for k,v in session.items() if k != 'revision'}
        updated.update(latest_checkpoint_id=payload.id, status='completed' if payload.final else 'incomplete', updated_at=value['created_at'])
        store.transaction({path:(None,json_bytes(value)),f'sessions/{session_id}/session.json':(raw,json_bytes(updated))},new_event(project.id,'checkpoint',payload.id,'Final handoff checkpoint saved' if payload.final else 'Progress checkpoint saved',payload.actor))
        return value


def list_sessions(project):
    with FolderStore(project.path).locked() as store:
        store.read_project(project.id)
        # names() accepts a suffix; session directories have canonical UUID names.
        result=[]
        for directory in store.names('sessions', ''):
            session_id=Path(directory).name
            result.append(read_session(store,project.id,session_id)[0])
        return sorted(result,key=lambda s:(s.get('updated_at',s['created_at']),s['id']),reverse=True)


def session_detail(project, session_id):
    with FolderStore(project.path).locked() as store:
        store.read_project(project.id)
        session,_=read_session(store,project.id,session_id)
        return {'session':session,'checkpoints':checkpoints(store,project.id,session_id)}


def resume(project):
    sessions=list_sessions(project)
    if not sessions: return None
    meaningful=[s for s in sessions if s.get('origin','explicit')=='explicit' or s.get('intent_recorded') or s.get('latest_checkpoint_id')]
    session=(meaningful or sessions)[0]
    detail=session_detail(project,session['id'])
    session=detail['session']
    history=detail['checkpoints']
    latest=next((c for c in history if c['id']==session['latest_checkpoint_id']), None)
    if (session['latest_checkpoint_id'] and latest is None) or (session['status']=='completed' and (not latest or not latest['explanation']['final'])):
        raise Problem('invalid_memory', 'Session checkpoint pointer or final handoff is inconsistent', 409)
    baseline=latest['observation'] if latest else session['observation']
    current=observe_repository(project.path)
    before,after=baseline['fingerprints'],current['fingerprints']
    return {'session':session,'checkpoint':latest,'current_observation':current,'changes':{'added':sorted(after.keys()-before.keys()),'removed':sorted(before.keys()-after.keys()),'modified':sorted(p for p in before.keys() & after.keys() if before[p]!=after[p]),'head_changed':baseline['head']!=current['head'],'branch_changed':baseline['branch']!=current['branch'],'complete':baseline['complete'] and current['complete']},'incomplete_sessions':[s for s in sessions if s['status']=='incomplete']}


def export_sessions(store, project_id):
    result = []
    for directory in store.names('sessions', ''):
        session_id = Path(directory).name
        session, _ = read_session(store, project_id, session_id)
        result.append({'session': session, 'checkpoints': checkpoints(store, project_id, session_id)})
    return result


def update_task(project, session_id, payload):
    from .services import new_event
    with FolderStore(project.path).locked() as store:
        store.read_project(project.id)
        session,raw=read_session(store,project.id,session_id)
        if session['revision']!=payload.revision or session['status']=='completed':
            raise Problem('conflict','Session changed or completed; reread before recording intent',409)
        value={k:v for k,v in session.items() if k!='revision'}
        value.update(task=payload.task,intent_recorded=True,updated_at=now())
        store.transaction({f'sessions/{session_id}/session.json':(raw,json_bytes(value))},new_event(project.id,'session',session_id,'Session intent updated',payload.actor))
        return read_session(store,project.id,session_id)[0]
