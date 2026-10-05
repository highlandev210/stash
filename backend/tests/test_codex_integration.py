import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import httpx
import pytest
from typer.testing import CliRunner

from support import TestClient
from stash.api import create_app
from stash.codex_hook import capture
from stash.codex_runtime import Runtime, status
from stash.codex_worker import drain, sweep
from stash.db import open_database
from stash import services as svc
from stash.schemas import Registration
from stash_cli.main import app
from stash_cli.codex_install import install, uninstall


def payload(event='SessionStart',**changes):
    return {'hook_event_name':event,'session_id':'codex-thread-test','cwd':'unused','source':'startup',**changes}


@pytest.fixture
def integration(tmp_path):
    root=tmp_path/'project';root.mkdir()
    engine,factory=open_database(tmp_path/'registry.db')
    with factory() as db:
        p=svc.register(db,Registration(path=str(root)));project_id=p.id
    install(root,'http://127.0.0.1:8000',with_skill=False)
    with Runtime(root) as runtime:
        config=runtime.config();runtime.write('runtime/codex/config.json',{**config,'spawn_worker':False})
    yield root,factory,project_id,tmp_path/'registry.db'
    engine.dispose()


def transport(client):
    def send(method,path,value=None):
        result=client.request(method,'/api/v1'+path,json=value)
        return result.status_code,result.json()
    return send


def test_interrupt_offline_retry_preserves_semantic_history(integration,monkeypatch):
    root,factory,pid,db=integration
    captured=capture(payload(),root,False)
    with TestClient(create_app(db,test=True)) as client:
        assert drain(root,transport(client))['sent']==1
        base=f'/api/v1/projects/{pid}'
        sid=captured['session_id']
        original=client.get(base+f'/sessions/{sid}').json()['session']
        task=client.put(base+f'/sessions/{sid}/task',json={'revision':original['revision'],'task':'Fix filtering','actor':{'name':'Codex','kind':'agent'}}).json()
        checkpoint={'id':str(uuid4()),'revision':task['revision'],'progress':'Filter controls added','verification':'Not yet tested','next_actions':'Implement backend','actor':{'name':'Codex','kind':'agent'}}
        assert client.post(base+f'/sessions/{sid}/checkpoints',json=checkpoint).status_code==200
        (root/'code.py').write_text('unfinished edit')
        capture(payload('PostToolUse',turn_id='turn',tool_use_id='tool',tool_name='Bash',tool_input={'command':'secret command'},tool_response={'exit_code':1,'stdout':'secret output'}),root,False)
        capture(payload('Interrupt',turn_id='turn'),root,False)
        def offline(*args,**kwargs): raise httpx.ConnectError('offline')
        assert drain(root,offline)['error']=='server_unavailable'
        assert status(root)['pending']==2
        sweep(factory) # Same recovery path used when the real server starts/retries.
        assert status(root)['pending']==0
        facts=client.get(base+'/observations').json()
        assert len(facts)==3 and any(f['event']=='Interrupt' for f in facts)
        assert any(f.get('exit_code')==1 for f in facts)
        assert 'secret' not in json.dumps(facts)
        session=client.get(base+f'/sessions/{sid}').json()
        assert session['session']['status']=='incomplete' and len(session['checkpoints'])==1
        assert session['checkpoints'][0]['explanation']['progress']=='Filter controls added'
        context=client.get(base+'/context').json()
        assert 'Implement backend' in context['markdown'] and 'Interrupt' in context['markdown']
        assert context['resume']['changes']['added']==['code.py']
        capture(payload('Interrupt',turn_id='turn'),root,False)
        assert status(root)['pending']==0
        assert drain(root,transport(client))['sent']==0
        assert len(client.get(base+'/observations').json())==3
        export=client.get(base+'/export').json()
        assert export['format_version']==5 and len(export['observations'])==3
        assert client.get(base+'/records/'+facts[0]['id']).json()['kind']=='observation'


def test_generic_hook_session_does_not_replace_prior_meaningful_context(integration):
    root,factory,pid,db=integration
    with TestClient(create_app(db,test=True)) as c:
        base=f'/api/v1/projects/{pid}'
        s=c.post(base+'/sessions',json={'id':str(uuid4()),'task':'Existing unfinished task'}).json()
        c.post(base+f"/sessions/{s['id']}/checkpoints",json={'id':str(uuid4()),'revision':s['revision'],'next_actions':'Continue the old task'})
        capture(payload(),root,False);drain(root,transport(c))
        assert c.get(base+'/resume').json()['session']['id']==s['id']
        facts=c.get(base+'/observations').json();assert facts[0]['session_id']!=s['id']


def test_observation_conflicts_isolation_and_forbidden_fields(integration,tmp_path):
    root,factory,pid,db=integration
    with TestClient(create_app(db,test=True)) as c:
        base=f'/api/v1/projects/{pid}'
        item=capture(payload('PostToolUse',turn_id='t',tool_use_id='c',tool_name='apply_patch',tool_response='unstructured raw output'),root,False)
        with Runtime(root) as runtime: event=runtime.read(f"runtime/codex/outbox/{item['event_id']}.json")
        drain(root,transport(c))
        assert c.post(base+'/observations',json=event).status_code==200
        assert c.post(base+'/observations',json={**event,'tool':'other'}).status_code==409
        assert c.post(base+'/observations',json={**event,'stdout':'secret'}).status_code==422
        other=tmp_path/'other';other.mkdir()
        otherid=c.post('/api/v1/projects',json={'path':str(other)}).json()['id']
        assert c.post(f'/api/v1/projects/{otherid}/observations',json=event).status_code==404
        assert c.get(base+f"/sessions/{item['session_id']}").json()['session']['status']=='incomplete'
        assert c.get(base+'/observations').json()[0]['exit_code'] is None


def test_hook_subprocess_protocol_and_allowlist(integration):
    root,_,_,_=integration
    events=['SessionStart','PostToolUse','Stop','Interrupt','SessionEnd']
    for name in events:
        input=payload(name,cwd=str(root),turn_id='turn-'+name,tool_use_id='call',tool_name='Bash',tool_response={'exit_code':0,'isError':False,'output':'secret output'},transcript_path='/never/read',last_assistant_message='private text',prompt='private prompt')
        result=subprocess.run([sys.executable,'-m','stash.codex_hook','--no-worker'],input=json.dumps(input),text=True,capture_output=True,timeout=3)
        assert result.returncode==0,result.stderr
        if result.stdout: json.loads(result.stdout)
    assert status(root)['pending']==5
    files=list((root/'.stash/runtime/codex/outbox').glob('*.json'))
    assert all('private' not in f.read_text() and 'secret' not in f.read_text() and 'transcript' not in f.read_text() for f in files)


def test_install_remove_preserves_other_hooks_and_custom_skills(integration):
    root,_,_,_=integration
    path=root/'.codex/hooks.json'
    existing=json.loads(path.read_text());existing['description']='Keep this'
    existing['hooks']['Stop'].append({'hooks':[{'type':'command','command':'other-handler'}]})
    path.write_text(json.dumps(existing))
    install(root,'http://127.0.0.1:8000',with_skill=False)
    current=json.loads(path.read_text())
    assert current['description']=='Keep this' and len(current['hooks']['Stop'])==2
    uninstall(root)
    assert json.loads(path.read_text())['hooks']['Stop']==[{'hooks':[{'type':'command','command':'other-handler'}]}]
    assert (root/'.stash/project.json').exists() and not status(root)['enabled']
    custom=root/'.agents/skills/stash';custom.mkdir(parents=True);(custom/'SKILL.md').write_text('Customized')
    with pytest.raises(ValueError,match='customized'): install(root,'http://127.0.0.1:8000',with_skill=True)
    assert (custom/'SKILL.md').read_text()=='Customized'


def test_bind_and_task_revision(integration,monkeypatch):
    root,_,pid,db=integration
    runner=CliRunner();monkeypatch.chdir(root)
    capture_result=capture(payload(),root,False)
    with TestClient(create_app(db,test=True)) as c:
        monkeypatch.setattr('stash_cli.main.httpx.request',lambda method,url,**kw:c.request(method,url,**kw))
        drain(root,transport(c))
        created=runner.invoke(app,['--json','sessions','start','Continue meaningful task'])
        sid=json.loads(created.stdout)['result']['id']
        result=runner.invoke(app,['--json','integrations','codex','bind',capture_result['runtime_key'],'--session',sid])
        assert result.exit_code==0,result.output
        assert capture(payload('Stop',turn_id='next'),root,False)['session_id']==sid
        drain(root,transport(c))
        detail=c.get(f'/api/v1/projects/{pid}/sessions/{sid}').json()['session']
        payload_path=root/'task.json';payload_path.write_text(json.dumps({'revision':detail['revision'],'task':'Recorded task'}))
        task=runner.invoke(app,['--json','sessions','task',sid,'--file',str(payload_path)])
        assert task.exit_code==0,task.output
        assert runner.invoke(app,['--json','sessions','task',sid,'--file',str(payload_path)]).exit_code==4
        assert c.get(f'/api/v1/projects/{pid}/sessions/{sid}').json()['session']['status']=='incomplete'


def test_capture_survives_process_end_and_concurrent_duplicates(integration):
    from concurrent.futures import ThreadPoolExecutor
    root,_,_,db=integration
    event=payload('Interrupt',cwd=str(root),turn_id='interrupt-turn')
    # Hook process completes before any transport, simulating the agent disappearing.
    result=subprocess.run([sys.executable,'-m','stash.codex_hook','--no-worker'],input=json.dumps(event),text=True,capture_output=True,timeout=3)
    assert result.returncode==0 and status(root)['pending']==1
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _:capture(event,root,False),range(8)))
    assert status(root)['pending']==1
    with TestClient(create_app(db,test=True)) as c:
        assert drain(root,transport(c))['sent']==1
        assert drain(root,transport(c))['sent']==0
        capture(event,root,False)
        assert status(root)['pending']==0


def test_capture_rejects_runtime_symlink_and_disabling_preserves_outbox(integration,tmp_path):
    root,_,_,_=integration
    capture(payload(),root,False)
    uninstall(root)
    assert status(root)['pending']==1
    assert capture(payload('Interrupt',turn_id='later'),root,False) is None
    assert drain(root)['pending']==1
    other=tmp_path/'other';other.mkdir()
    (root/'.stash/runtime/codex/bindings').rename(root/'.stash/runtime/codex/old-bindings')
    (root/'.stash/runtime/codex/bindings').symlink_to(other,target_is_directory=True)
    install(root,'http://127.0.0.1:8000',with_skill=False)
    with pytest.raises(OSError): capture(payload(session_id='different'),root,False)
    assert list(other.iterdir())==[]


def test_queued_interrupt_survives_project_move_and_new_session(integration,tmp_path):
    root,_,pid,db=integration
    first=capture(payload(),root,False)
    with TestClient(create_app(db,test=True)) as c:
        base=f'/api/v1/projects/{pid}'
        drain(root,transport(c))
        detail=c.get(base+f"/sessions/{first['session_id']}").json()['session']
        task=c.put(base+f"/sessions/{first['session_id']}/task",json={'revision':detail['revision'],'task':'Prior unfinished work'}).json()
        c.post(base+f"/sessions/{first['session_id']}/checkpoints",json={'id':str(uuid4()),'revision':task['revision'],'next_actions':'Recover after move'})
        capture(payload('Interrupt',turn_id='move-turn'),root,False)
        moved=tmp_path/'relocated';root.rename(moved)
        project=c.get(base).json()
        fields=['revision','name','status','description','purpose','tags','stack','focus','next_step','brief','setup_command','run_command','test_command','services','env_names','repo_url','demo_url','screenshot','doc_roots','writable_doc_roots']
        update={key:project[key] for key in fields};update['path']=str(moved)
        assert c.put(base,json=update).status_code==200
        new=capture(payload(session_id='new-runtime-session'),moved,False)
        assert new['session_id']!=first['session_id']
        assert drain(moved,transport(c))['sent']==2
        context=c.get(base+'/context').json()
        assert context['resume']['session']['id']==first['session_id']
        assert 'Recover after move' in context['markdown']
        assert all(s['status']=='incomplete' for s in c.get(base+'/sessions').json())
        assert c.get(base).json()['id']==pid and status(moved)['pending']==0
