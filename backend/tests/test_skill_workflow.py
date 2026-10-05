"""Executable contract acceptance for the explicit skill workflow, not a simulated model."""
import json
import subprocess
import sys
from typer.testing import CliRunner
from support import TestClient
from stash.api import create_app
from stash_cli.main import app


def test_explicit_workflow_preserves_human_records_and_handles_offline_conflicts(tmp_path,monkeypatch):
    root=tmp_path/'repo';root.mkdir()
    source=root/'main.py';source.write_text('def hello():\n    return "hello"\n')
    (root/'README.md').write_text('# Product README\nDo not replace this with development logs.\n')
    runner=CliRunner();monkeypatch.chdir(root)
    with TestClient(create_app(tmp_path/'db',test=True)) as client:
        monkeypatch.setattr('stash_cli.main.httpx.request',lambda method,url,**kw:client.request(method,url,**kw))
        def run(*args):
            result=runner.invoke(app,['--actor','Codex','--kind','agent','--json',*args])
            assert result.exit_code==0,result.output
            return json.loads(result.stdout)
        registered=run('register',str(root));pid=registered['id'];base=f'/api/v1/projects/{pid}'
        fields=['revision','name','path','status','description','purpose','tags','stack','focus','next_step','brief','setup_command','run_command','test_command','services','env_names','repo_url','demo_url','screenshot','doc_roots','writable_doc_roots']
        human={k:registered[k] for k in fields};human.update(description='Human description',brief='Human brief',actor={'name':'Owner','kind':'human'})
        client.put(base,json=human)
        init=root/'init.json';init.write_text(json.dumps({'description':'Agent alternative','purpose':'A Python greeting fixture','stack':['Python'],'brief':'Agent alternative','next_step':'Inspect greeting'}))
        first=run('init','.', '--file',str(init));second=run('init','.', '--file',str(init))
        assert first['project']['id']==second['project']['id']==pid
        assert second['project']['description']=='Human description' and second['project']['brief']=='Human brief'
        note=root/'note.md';note.write_text('Inspected main.py and README.md. Python compile check not yet run.\n')
        written=run('docs','write','.stash/docs/inspection.md','--file',str(note),'--create')
        assert run('docs','read','.stash/docs/inspection.md')['content']==note.read_text()
        session=run('sessions','start','Inspect and verify greeting')['result']
        issue=run('issues','create','Verify greeting syntax','--type','task')
        run('issues','update',issue['id'],'--status','in_progress')
        run('issues','comment',issue['id'],'Inspecting current source before trusting recorded context')
        run('decisions','add','Keep product README separate','--reasoning','stash docs record development evidence')
        check=subprocess.run([sys.executable,'-m','py_compile',str(source)],capture_output=True)
        assert check.returncode==0
        checkpoint=root/'checkpoint.json';checkpoint.write_text(json.dumps({'revision':session['revision'],'progress':'Inspected greeting and recorded development notes','verification':'python -m py_compile main.py passed (actually executed in this test)','next_actions':'Review the greeting behavior'}))
        run('sessions','checkpoint',session['id'],'--file',str(checkpoint))
        detail=run('sessions','show',session['id'])
        assert detail['session']['status']=='incomplete'
        run('issues','update',issue['id'],'--status','done','--verification','Python compilation passed')
        context=run('context');assert 'Review the greeting behavior' in context['markdown']
        external=root/'.stash/docs/inspection.md';external.write_text('Human updated notes\n')
        stale=runner.invoke(app,['--json','docs','write','.stash/docs/inspection.md','--file',str(note),'--revision',written['revision']])
        assert stale.exit_code==4 and external.read_text()=='Human updated notes\n'
        checkpoint.write_text(json.dumps({'revision':detail['session']['revision'],'progress':'Finished explicit skill workflow','verification':'Python compile check passed; no behavior tests claimed','next_actions':'Review behavior separately','final':True}))
        final=run('sessions','checkpoint',session['id'],'--file',str(checkpoint))
        assert final['result']['explanation']['final']
        assert len(run('sessions','show',session['id'])['checkpoints'])==2
        assert run('projects','show')['description']=='Human description'
        assert (root/'README.md').read_text().startswith('# Product README')
