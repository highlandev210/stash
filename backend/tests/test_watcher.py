from pathlib import Path
from uuid import uuid4
from support import TestClient
from stash.api import create_app
from stash import watcher, services, sessions
from stash.db import open_database
from stash.schemas import Registration, Actor, SessionStart, CheckpointInput


def test_watcher_independent_grouped_restart_move_exclusions(tmp_path):
    root=tmp_path/'project'; root.mkdir()
    engine,factory=open_database(tmp_path/'registry.db')
    actor=Actor(name='Owner',kind='human')
    with factory() as db:
        p=services.register(db,Registration(path=str(root)))
        (root/'source.py').write_text('v1')
        assert watcher.poll(p) is None
        watcher.configure(p,True,actor)
        assert watcher.poll(p) is None # baseline, not all existing files as new changes
        (root/'source.py').write_text('v2'); (root/'new.py').write_text('new')
        for name in ['.env','private.key','.stash/generated.txt','node_modules/dependency.js','dist/bundle.js']:
            path=root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text('secret')
        outside=tmp_path/'outside';outside.write_text('secret');(root/'escape').symlink_to(outside)
        observation=watcher.poll(p)
        assert observation['modified']==['source.py'] and observation['added']==['new.py']
        assert observation['removed']==[] and 'secret' not in str(observation)
        assert watcher.poll(p) is None # stash changes excluded, no self noise
        pid=p.id
    engine.dispose()
    # File changes while server/agent is stopped remain detectable after restart.
    (root/'source.py').unlink()
    moved=tmp_path/'moved';root.rename(moved)
    with TestClient(create_app(tmp_path/'registry.db',test=True)) as c:
        base=f'/api/v1/projects/{pid}'
        project=c.get(base).json()
        assert project['availability']=='missing'
        fields=['name','description','purpose','status','tags','stack','focus','next_step','brief','setup_command','run_command','test_command','services','env_names','repo_url','demo_url','screenshot','doc_roots','writable_doc_roots','revision']
        payload={k:project[k] for k in fields}; payload['path']=str(moved)
        assert c.put(base,json=payload).status_code==200
        watcher.sweep(c.app.state.session_factory)
        items=c.get(base+'/file-observations').json()
        assert len(items)==2 and items[0]['removed']==['source.py']
        assert c.get(base+'/records/'+items[0]['id']).json()['kind']=='file_observation'
        assert len(c.get(base+'/export').json()['file_observations'])==2
        assert c.get(base+'/sessions').json()==[] # never fabricate sessions or completion
        assert c.put(base+'/watcher',json={'enabled':False}).status_code==200
        assert c.get(base+'/watcher').json()['enabled'] is False


def test_partial_scan_never_invents_deletions_and_checkpoint_survives(tmp_path,monkeypatch):
    root=tmp_path/'repo';root.mkdir();(root/'source').write_text('old')
    engine,factory=open_database(tmp_path/'registry.db')
    with factory() as db:
        p=services.register(db,Registration(path=str(root)))
        s=sessions.start_session(p,SessionStart(id=str(uuid4()),task='Unfinished work'))
        sessions.save_checkpoint(p,s['id'],CheckpointInput(id=str(uuid4()),revision=s['revision'],next_actions='Continue reviewing source'))
        watcher.configure(p,True,Actor());watcher.poll(p)
        with monkeypatch.context() as m:
            m.setattr(watcher,'observe_repository',lambda *a,**kw: {'fingerprints':{},'complete':False,'warnings':['Scan limited'],'captured_at':s['created_at']})
            assert watcher.poll(p) is None
            assert watcher.status(p)['complete'] is False
        (root/'source').write_text('new')
        assert watcher.poll(p)['modified']==['source']
        r=sessions.resume(p)
        assert r['session']['status']=='incomplete' and r['checkpoint']['explanation']['next_actions']=='Continue reviewing source'
    engine.dispose()


def test_watcher_recovers_interrupted_baseline_history_transaction(tmp_path,monkeypatch):
    import pytest
    from stash.store import FolderStore
    root=tmp_path/'repo';root.mkdir();(root/'code').write_text('before')
    engine,factory=open_database(tmp_path/'db')
    with factory() as db:
        p=services.register(db,Registration(path=str(root)))
        watcher.configure(p,True,Actor());watcher.poll(p)
        (root/'code').write_text('after')
        original=FolderStore.write
        with monkeypatch.context() as m:
            def crash(store,path,content):
                if path.startswith('file_observations/'): raise RuntimeError('Simulated shutdown after baseline write')
                return original(store,path,content)
            m.setattr(FolderStore,'write',crash)
            with pytest.raises(RuntimeError): watcher.poll(p)
        # Folder lock recovery replays the journal before accepting the newer baseline.
        assert watcher.poll(p) is None
        history=watcher.list_observations(p)
        assert len(history)==1 and history[0]['modified']==['code']
        assert len([e for e in services.activities(db,p) if e['kind']=='file_observation'])==1
    engine.dispose()
