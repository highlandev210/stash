"""Opt-in polling observer. Facts about saved files, never task completion."""
import json
from .filesystem import Problem, check_root, allowed_name
from .models import now, uid
from .schemas import Actor
from .sessions import observe_repository, validate_time
from .store import FolderStore, json_bytes, valid_id

CONFIG = 'runtime/watcher/config.json'
STATE = 'runtime/watcher/state.json'
ACTOR = Actor(name='File watcher', kind='agent')


def configure(project, enabled, actor):
    with FolderStore(check_root(project)).locked() as store:
        store.read_project(project.id)
        old = store.read(CONFIG)
        from .services import new_event
        store.transaction({CONFIG: (old, json_bytes({'enabled': enabled}))}, new_event(project.id, 'watcher', project.id, 'File watcher enabled' if enabled else 'File watcher disabled', actor))
    return {'enabled': enabled}


def status(project):
    with FolderStore(check_root(project)).locked() as store:
        store.read_project(project.id)
        config = store.json(CONFIG, required=False) or {}
        state = store.json(STATE, required=False) or {}
        return {'enabled': config.get('enabled') is True, 'checked_at': state.get('checked_at'), 'complete': state.get('complete'), 'warnings': state.get('warnings', [])}


def poll(project):
    """Group changes per scan; journal commits baseline and event together."""
    with FolderStore(check_root(project)).locked() as store:
        store.read_project(project.id)
        config = store.json(CONFIG, required=False) or {}
        if config.get('enabled') is not True: return None
        raw = store.read(STATE)
        old = json.loads(raw) if raw else None
        current = observe_repository(project.path, include_git=False)
        previous = old['fingerprints'] if old else {}
        hashes = current['fingerprints']
        # A partial scan must never turn omitted files into claimed deletions.
        added = sorted(set(hashes) - set(previous)) if old else []
        modified = sorted(p for p in hashes.keys() & previous.keys() if hashes[p] != previous[p])
        removed = sorted(set(previous) - set(hashes)) if old and current['complete'] else []
        retained = hashes if current['complete'] else {**previous, **hashes}
        state = {'fingerprints': retained, 'checked_at': current['captured_at'], 'complete': current['complete'], 'warnings': current['warnings']}
        changes = {STATE: (raw, json_bytes(state))}
        event = None
        value = None
        if added or modified or removed:
            from .services import new_event
            value = {'schema_version': 1, 'id': uid(), 'project_id': project.id, 'observed_at': now(), 'actor': ACTOR.model_dump(), 'added': added, 'modified': modified, 'removed': removed, 'complete': current['complete'], 'warnings': current['warnings']}
            changes[f"file_observations/{value['id']}.json"] = (None, json_bytes(value))
            event = new_event(project.id, 'file_observation', value['id'], f"Saved file changes: +{len(added)} ~{len(modified)} -{len(removed)} (not task completion)", ACTOR)
        store.transaction(changes, event)
        return value


def read_observations(store, project_id, limit=10000):
    result = []
    for path in store.names('file_observations', '.json'):
        value = store.json(path)
        try:
            valid_id(value['id']); validate_time(value['observed_at']); Actor.model_validate(value['actor'])
            if type(value['complete']) is not bool or not isinstance(value['warnings'],list) or not all(isinstance(w,str) for w in value['warnings']): raise ValueError()
            if path != f"file_observations/{value['id']}.json" or value['project_id'] != project_id or value['schema_version'] != 1: raise ValueError()
            for key in ('added', 'modified', 'removed'):
                if not isinstance(value[key], list): raise ValueError()
                for name in value[key]:
                    from pathlib import PurePosixPath
                    item = PurePosixPath(name)
                    if item.is_absolute() or '..' in item.parts or '\\' in name or not item.parts or not all(allowed_name(p) for p in item.parts): raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise Problem('invalid_memory', 'Invalid saved-file observation', 409)
        result.append(value)
    return sorted(result, key=lambda v: (v['observed_at'], v['id']), reverse=True)[:limit]


def list_observations(project, limit=50):
    with FolderStore(check_root(project)).locked() as store:
        store.read_project(project.id)
        return read_observations(store, project.id, limit)

def sweep(factory):
    from . import services
    with factory() as db:
        for project in services.all_projects(db):
            try: poll(project)
            except (OSError, Problem, ValueError, KeyError):
                # Missing/corrupt roots remain registered, with their previous baseline intact.
                continue
