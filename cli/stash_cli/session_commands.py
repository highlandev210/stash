"""Persist requests before HTTP so an unavailable server cannot lose intent."""
import json
import os
from pathlib import Path
from typing import Optional
from uuid import uuid4
import typer
from stash.filesystem import Problem


def install(app, main):
    group = typer.Typer(no_args_is_help=True)
    app.add_typer(group, name='sessions')

    def draft_write(path, value):
        from stash.filesystem import parent_fd, read_at, Problem
        path = path.expanduser().absolute()
        parent = None
        try:
            parent = parent_fd(Path('/'), path.relative_to('/'), create=True)
            try:
                old = json.loads(read_at(parent, path.name, 2_000_000))
            except FileNotFoundError:
                old = None
            if old is not None:
                if old != value:
                    main.fail('conflict', 'Existing draft differs; replay it or choose another path', 4)
                return path
            temporary = '.stash-draft-' + str(uuid4())
            fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            try:
                with os.fdopen(fd, 'w') as handle:
                    json.dump(value, handle, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.link(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
                os.fsync(parent)
            finally:
                os.unlink(temporary, dir_fd=parent)
            return path
        except (OSError, ValueError, Problem):
            main.fail('invalid_input', 'Draft could not be saved safely; choose a writable path without symlinks', 2)
        finally:
            if parent is not None:
                os.close(parent)

    def send(draft, path):
        main.state['pending_draft'] = str(path)
        if draft.get('server', main.state['server']) != main.state['server']:
            main.fail('invalid_input', 'Replay using the same --server as the original draft', 2)
        project_id = draft['project_id'] or main.request('GET','/resolve',params={'path':draft['project_path']})['id']
        route = f'/projects/{project_id}/sessions' + (f"/{draft['session_id']}/checkpoints" if draft['operation']=='checkpoint' else '')
        result = main.request('POST', route, draft['payload'])
        # Keep receipts too: rerunning a draft is safe after an ambiguous response.
        main.state.pop('pending_draft', None)
        main.emit({'result':result,'draft':str(path),'saved':True})

    def persist(operation, payload, session_id, draft_path):
        filename=Path(draft_path) if draft_path else Path.cwd()/'.stash/drafts'/f"{payload['id']}.json"
        value={'server':main.state['server'],'schema_version':1,'operation':operation,'project_id':main.state['project'],'project_path':str(Path.cwd().resolve()),'session_id':session_id,'payload':payload}
        path=draft_write(filename,value)
        send(value,path)

    @group.command('start')
    def start(task: str, id: Optional[str] = None, draft: Optional[str] = None):
        from stash.schemas import SessionStart
        from stash.store import valid_id
        from pydantic import ValidationError
        from stash.filesystem import Problem
        try:
            payload=SessionStart(id=id or str(uuid4()),task=task,actor=main.state['actor']).model_dump()
            valid_id(payload['id'])
        except (ValidationError, Problem):
            main.fail('invalid_input', 'Provide a nonempty task and canonical UUID session ID', 2)
        persist('start',payload,None,draft)

    @group.command('list')
    def listing(): main.emit(main.request('GET',main.base()+'/sessions'))

    @group.command('show')
    def show(session_id: str): main.emit(main.request('GET',main.base()+f'/sessions/{session_id}'))

    @group.command('task')
    def task(session_id: str, file: str = typer.Option(...,'--file')):
        from stash.schemas import SessionTask
        from pydantic import ValidationError
        try: payload=SessionTask.model_validate(main.load_payload(file)).model_dump()
        except ValidationError: main.fail('invalid_input','Task update needs the original revision and actual task',2)
        main.emit(main.request('PUT',main.base()+f'/sessions/{session_id}/task',payload))

    @group.command('checkpoint')
    def checkpoint(session_id: str, file: str = typer.Option(...,'--file'), draft: Optional[str] = None):
        from stash.schemas import CheckpointInput
        from stash.store import valid_id
        payload=main.load_payload(file)
        payload.setdefault('id',str(uuid4()))
        from pydantic import ValidationError
        from stash.filesystem import Problem
        try:
            parsed=CheckpointInput.model_validate(payload)
            valid_id(parsed.id)
            valid_id(session_id)
        except (ValidationError, Problem):
            main.fail('invalid_input', 'Checkpoint requires canonical IDs, the original revision, and next_actions', 2)
        persist('checkpoint',parsed.model_dump(),session_id,draft)

    @group.command('replay')
    def replay(file: Path):
        try:
            value=json.loads(file.read_text())
            if value['schema_version']!=1 or value['operation'] not in {'start','checkpoint'}: raise ValueError()
            if not isinstance(value['project_path'],str) or not Path(value['project_path']).is_absolute(): raise ValueError()
            if value['project_id'] is not None and not isinstance(value['project_id'],str): raise ValueError()
            if not isinstance(value['server'],str): raise ValueError()
            from stash.schemas import SessionStart, CheckpointInput
            from stash.store import valid_id
            parsed=(SessionStart if value['operation']=='start' else CheckpointInput).model_validate(value['payload'])
            valid_id(parsed.id)
            if value['operation']=='checkpoint': valid_id(value['session_id'])
        except (OSError, ValueError, KeyError, TypeError, Problem):
            main.fail('invalid_input','Provide an intact stash request draft',2)
        send(value,file)

    @group.command('resume')
    def resume(): main.emit(main.request('GET',main.base()+'/resume'))
