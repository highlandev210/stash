"""Append-only hook facts, never semantic progress or completion."""
from pydantic import ValidationError
from .filesystem import Problem
from .models import now
from .schemas import HookObservation
from .sessions import read_session, validate_time
from .store import FolderStore, valid_id, json_bytes


def read_observations(store, project_id):
    result=[]
    for path in store.names('observations','.json'):
        value=store.json(path)
        try:
            fields={key:value[key] for key in HookObservation.model_fields if key in value}
            parsed=HookObservation.model_validate(fields)
            valid_id(parsed.id);valid_id(parsed.session_id);validate_time(parsed.observed_at)
            if path != f'observations/{parsed.id}.json' or value['project_id']!=project_id or value['schema_version']!=1: raise ValueError()
        except (KeyError, TypeError, ValueError, ValidationError):
            raise Problem('invalid_memory','Invalid hook observation',409)
        result.append(value)
    return sorted(result,key=lambda x:(x['observed_at'],x['id']),reverse=True)


def ingest(project,payload):
    from .services import new_event
    valid_id(payload.id);valid_id(payload.session_id)
    try: validate_time(payload.observed_at)
    except (TypeError, ValueError): raise Problem('invalid_input','Observation needs a timezone-aware timestamp')
    content=payload.model_dump()
    with FolderStore(project.path).locked() as store:
        store.read_project(project.id)
        read_session(store,project.id,payload.session_id)
        path=f'observations/{payload.id}.json'
        previous=store.json(path,required=False)
        if previous:
            if any(previous.get(k)!=v for k,v in content.items()): raise Problem('conflict','Observation ID reused with different facts',409)
            return previous
        value={**content,'project_id':project.id,'schema_version':1,'received_at':now()}
        store.transaction({path:(None,json_bytes(value))},new_event(project.id,'observation',payload.id,f'Codex observation: {payload.event}',payload.actor))
        return value


def list_observations(project,limit=50):
    with FolderStore(project.path).locked() as store:
        store.read_project(project.id)
        return read_observations(store,project.id)[:limit]
