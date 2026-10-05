import json
import subprocess
from uuid import uuid4

import httpx
import pytest
from typer.testing import CliRunner

from stash.api import create_app
from stash.db import open_database
from stash import services as svc, sessions
from stash.schemas import Registration, SessionStart, CheckpointInput
from stash.store import FolderStore
from stash.filesystem import Problem
from support import TestClient
from stash_cli.main import app


def uid(): return str(uuid4())


def test_session_checkpoint_resume_git_and_restart(tmp_path):
    root=tmp_path/'repo';root.mkdir()
    def git(*args): return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True).stdout
    git('init');git('config','user.name','Fixture');git('config','user.email','fixture@example.invalid')
    (root/'code.py').write_text('before')
    (root/'.gitignore').write_text('.stash/\n')
    git('add','.');git('commit','-m','initial')
    original_head=git('rev-parse','HEAD')
    engine,factory=open_database(tmp_path/'db')
    with factory() as db:
        project=svc.register(db,Registration(path=str(root)))
        start=SessionStart(id=uid(),task='Improve code')
        session=sessions.start_session(project,start)
        assert sessions.start_session(project,start)==session
        (root/'code.py').write_text('first edit')
        checkpoint=CheckpointInput(id=uid(),revision=session['revision'],progress='Started',unfinished_work='Still needs tests',next_actions='Run tests',verification='Not run')
        saved=sessions.save_checkpoint(project,session['id'],checkpoint)
        assert saved['observation']['git'] and saved['observation']['dirty']
        assert saved['observation']['head']==original_head.decode().strip()
        (root/'code.py').write_text('second edit')
        (root/'new.py').write_text('new')
        r=sessions.resume(project)
        assert r['changes']['modified']==['code.py'] and r['changes']['added']==['new.py']
        assert r['session']['status']=='incomplete'
        assert sessions.save_checkpoint(project,session['id'],checkpoint)==saved
        assert len(sessions.session_detail(project,session['id'])['checkpoints'])==1
        with pytest.raises(Problem,match='Session changed'):
            sessions.save_checkpoint(project,session['id'],checkpoint.model_copy(update={'id':uid()}))
        context=svc.context_data(db,project)
        assert 'Run tests' in svc.context_markdown(context) and 'code.py' in svc.context_markdown(context)
        project_id=project.id
    engine.dispose()
    engine,factory=open_database(tmp_path/'db')
    with factory() as db:
        project=svc.get_project(db,project_id)
        detail=sessions.session_detail(project,session['id'])
        assert detail['checkpoints'][0]==saved
        final=CheckpointInput(id=uid(),revision=detail['session']['revision'],progress='Done',verification='pytest passed',verification_includes_uncommitted=True,next_actions='Review',final=True)
        sessions.save_checkpoint(project,session['id'],final)
        assert sessions.resume(project)['session']['status']=='completed'
        assert len(sessions.session_detail(project,session['id'])['checkpoints'])==2
        assert git('rev-parse','HEAD')==original_head
    engine.dispose()


def test_recovery_checkpoint_no_git_and_secret_exclusions(tmp_path,monkeypatch):
    root=tmp_path/'repo';root.mkdir();(root/'file.md').write_text('hello')
    (root/'.env').write_text('do not capture')
    (root/'node_modules').mkdir();(root/'node_modules/x').write_text('skip')
    engine,factory=open_database(tmp_path/'db')
    with factory() as db:
        project=svc.register(db,Registration(path=str(root)))
        s=sessions.start_session(project,SessionStart(id=uid(),task='Task'))
        assert not s['observation']['git']
        assert list(s['observation']['fingerprints'])==['file.md']
        payload=CheckpointInput(id=uid(),revision=s['revision'],next_actions='Continue')
        real=FolderStore.recover
        with monkeypatch.context() as patch:
            patch.setattr(FolderStore,'recover',lambda self: (_ for _ in ()).throw(RuntimeError('power loss')) if self.read('.transaction.json') else real(self))
            with pytest.raises(RuntimeError): sessions.save_checkpoint(project,s['id'],payload)
        restored=sessions.session_detail(project,s['id'])
        assert restored['session']['latest_checkpoint_id']==payload.id
        assert len(restored['checkpoints'])==1
        assert sessions.save_checkpoint(project,s['id'],payload)['id']==payload.id
        (root/'file.md').unlink()
        assert sessions.resume(project)['changes']['removed']==['file.md']
    engine.dispose()


def test_api_isolation_conflicts_and_invalid_ids(tmp_path):
    root=tmp_path/'repo';root.mkdir();other=tmp_path/'other';other.mkdir()
    with TestClient(create_app(tmp_path/'db',test=True)) as c:
        pid=c.post('/api/v1/projects',json={'path':str(root)}).json()['id']
        second=c.post('/api/v1/projects',json={'path':str(other)}).json()['id']
        base=f'/api/v1/projects/{pid}'
        assert c.post(base+'/sessions',json={'id':'../bad','task':'Task'}).status_code==409
        session=c.post(base+'/sessions',json={'id':uid(),'task':'Task'}).json()
        assert c.get(f"/api/v1/projects/{second}/sessions/{session['id']}").status_code==404
        payload={'id':uid(),'revision':session['revision'],'next_actions':'Continue'}
        path=base+f"/sessions/{session['id']}/checkpoints"
        assert c.post(path,json=payload).status_code==200
        assert c.post(path,json=payload).status_code==200
        assert c.post(path,json={**payload,'progress':'different'}).status_code==409
        assert c.post(path,json={**payload,'id':uid()}).status_code==409
        assert c.get(base+'/resume').json()['checkpoint']['id']==payload['id']
        assert 'Continue' in c.get(base+'/context').json()['markdown']
        exported=c.get(base+'/export').json()
        assert exported['format_version']==5 and exported['sessions'][0]['checkpoints'][0]['id']==payload['id']
        assert c.get(base+'/records/'+payload['id']).json()['session_id']==session['id']
        assert c.get(base+'/records/'+session['id']).json()['kind']=='session'


def test_cli_offline_draft_replay_and_checkpoint(tmp_path,monkeypatch):
    root=tmp_path/'repo';root.mkdir();monkeypatch.chdir(root)
    runner=CliRunner()
    def offline(*args,**kwargs): raise httpx.ConnectError('offline')
    monkeypatch.setattr('stash_cli.main.httpx.request',offline)
    result=runner.invoke(app,['--json','sessions','start','Task'])
    assert result.exit_code==1,result.output
    drafts=list((root/'.stash/drafts').glob('*.json'));assert len(drafts)==1
    draft=json.loads(drafts[0].read_text());assert draft['payload']['task']=='Task'
    with TestClient(create_app(tmp_path/'db',test=True)) as c:
        c.post('/api/v1/projects',json={'path':str(root)})
        monkeypatch.setattr('stash_cli.main.httpx.request',lambda method,url,**kw:c.request(method,url,**kw))
        replay=runner.invoke(app,['--json','sessions','replay',str(drafts[0])]);assert replay.exit_code==0,replay.output
        session=json.loads(replay.stdout)['result']
        assert runner.invoke(app,['--json','sessions','replay',str(drafts[0])]).exit_code==0
        payload=root/'payload.json';payload.write_text(json.dumps({'revision':session['revision'],'next_actions':'Test next'}))
        checkpoint=runner.invoke(app,['--json','sessions','checkpoint',session['id'],'--file',str(payload)])
        assert checkpoint.exit_code==0,checkpoint.output
        checkpoint_draft=json.loads(checkpoint.stdout)['draft']
        assert runner.invoke(app,['--json','sessions','replay',checkpoint_draft]).exit_code==0
        resumed=runner.invoke(app,['--json','sessions','resume']);assert resumed.exit_code==0
        assert json.loads(resumed.stdout)['checkpoint']['explanation']['next_actions']=='Test next'


def test_observation_limits_symlinks_and_git_branch_changes(tmp_path):
    root=tmp_path/'repo';root.mkdir()
    def git(*args): return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True).stdout
    git('init');git('config','user.name','Fixture');git('config','user.email','fixture@example.invalid')
    (root/'code').write_text('v1');git('add','code');git('commit','-m','initial')
    baseline=sessions.observe_repository(root)
    git('checkout','-b','feature');(root/'code').write_text('v2');git('add','code');git('commit','-m','change')
    outside=tmp_path/'outside';outside.write_text('private')
    (root/'escape').symlink_to(outside)
    (root/'big').write_bytes(b'x'*2_000_001)
    index=(root/'.git/index').read_bytes()
    current=sessions.observe_repository(root)
    assert current['branch']!=baseline['branch'] and current['head']!=baseline['head']
    assert current['fingerprints']['code']!=baseline['fingerprints']['code']
    assert 'escape' not in current['fingerprints'] and 'big' not in current['fingerprints']
    assert not current['complete'] and current['warnings']
    assert (root/'.git/index').read_bytes()==index
    nested=root/'nested';nested.mkdir();(nested/'file').write_text('nested')
    nested_observation=sessions.observe_repository(nested)
    assert nested_observation['git']
    assert nested_observation['working_tree']==[{'path':'file','status':'??'}]


def test_partial_checkpoint_transaction_and_corrupt_session(tmp_path,monkeypatch):
    root=tmp_path/'repo';root.mkdir()
    engine,factory=open_database(tmp_path/'db')
    with factory() as db:
        p=svc.register(db,Registration(path=str(root)))
        s=sessions.start_session(p,SessionStart(id=uid(),task='Task'))
        payload=CheckpointInput(id=uid(),revision=s['revision'],next_actions='Continue')
        real_write=FolderStore.write
        with monkeypatch.context() as patch:
            def interrupted(store,path,content):
                if path==f"sessions/{s['id']}/session.json": raise RuntimeError('interrupted after checkpoint file')
                return real_write(store,path,content)
            patch.setattr(FolderStore,'write',interrupted)
            with pytest.raises(RuntimeError): sessions.save_checkpoint(p,s['id'],payload)
        assert (root/f".stash/sessions/{s['id']}/checkpoints/{payload.id}.json").exists()
        detail=sessions.session_detail(p,s['id'])
        assert detail['session']['latest_checkpoint_id']==payload.id and len(detail['checkpoints'])==1
        path=root/f".stash/sessions/{s['id']}/session.json"
        external=json.loads(path.read_text());external['observation']={};path.write_text(json.dumps(external))
        with pytest.raises(Problem,match='Invalid session'): sessions.resume(p)
        assert json.loads(path.read_text())['observation']=={}
    engine.dispose()


def test_cli_drafts_reject_symlink_and_invalid_requests(tmp_path, monkeypatch):
    root=tmp_path/'repo';root.mkdir();outside=tmp_path/'outside';outside.mkdir()
    (root/'.stash').symlink_to(outside,target_is_directory=True)
    monkeypatch.chdir(root)
    runner=CliRunner()
    bad=runner.invoke(app,['--json','sessions','start','Task','--id','../invalid'])
    assert bad.exit_code==2 and 'invalid_input' in bad.stdout
    rejected=runner.invoke(app,['--json','sessions','start','Task'])
    assert rejected.exit_code==2 and list(outside.iterdir())==[]
    malformed=root/'malformed.json';malformed.write_text('{}')
    assert runner.invoke(app,['--json','sessions','replay',str(malformed)]).exit_code==2
