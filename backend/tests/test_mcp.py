import json
import subprocess
import sys
from uuid import uuid4
import httpx
from support import TestClient
from stash.api import create_app
from stash.mcp_server import Bridge


def test_mcp_human_agent_conflicts_comments_and_shared_records(tmp_path):
    root=tmp_path/'project';root.mkdir()
    with TestClient(create_app(tmp_path/'db',test=True)) as c:
        pid=c.post('/api/v1/projects',json={'path':str(root)}).json()['id']
        base=f'/api/v1/projects/{pid}'
        bridge=Bridge('http://127.0.0.1:8000',pid,request=lambda method,path,**kw:c.request(method,'/api/v1'+path,**kw))
        def call(name,args={}):
            response=bridge.call(name,args)
            return response,json.loads(response['content'][0]['text'])
        response,issue=call('issue_create',{'issue':{'title':'Shared task'}})
        assert not response['isError'] and issue['creator']['kind']=='agent'
        # The browser writes after the agent reads the issue.
        human={k:issue[k] for k in ['title','type','status','priority','description','acceptance_criteria','reproduction_steps','expected_behavior','actual_behavior','affected_version','verification','labels','links','revision']}
        human['description']='Human detail';human['actor']={'name':'Owner','kind':'human'}
        assert c.put(base+'/issues/'+issue['id'],json=human).status_code==200
        stale={**human,'description':'Agent stale detail'};stale.pop('actor')
        response,error=call('issue_update',{'issue_id':issue['id'],'issue':stale})
        assert response['isError'] and error['code']=='conflict'
        assert c.get(base+'/issues/'+issue['id']).json()['description']=='Human detail'
        _,fresh=call('issue_get',{'issue_id':issue['id']})
        update={k:fresh[k] for k in human if k!='actor'};update['status']='in_progress'
        assert not call('issue_update',{'issue_id':issue['id'],'issue':update})[0]['isError']
        c.post(base+'/issues/'+issue['id']+'/comments',json={'body':'Human discussion','actor':{'name':'Owner','kind':'human'}})
        args={'issue_id':issue['id'],'body':'Agent discussion','request_id':str(uuid4())}
        first=call('comment_add',args)[1];second=call('comment_add',args)[1]
        assert first['id']==second['id']
        response,error=call('comment_add',{**args,'body':'Different content with old request ID'})
        assert response['isError'] and error['code']=='conflict'
        _,comments=call('comments_list',{'issue_id':issue['id']})
        assert len(comments)==2 and {v['actor']['kind'] for v in comments}=={'human','agent'}
        assert len(call('issues_list')[1]['items'])==1
        assert 'Shared task' in call('project_context')[1]['markdown']
        response,error=call('issue_get',{'issue_id':'../outside'})
        assert response['isError'] and error['code']=='invalid_input'
        assert call('issue_update',{'issue_id':issue['id'],'issue':{'title':'Missing revision'}})[0]['isError']


def test_stdio_handshake_actual_process(tmp_path):
    pid=str(uuid4())
    messages=[{'jsonrpc':'2.0','id':0,'method':'tools/list'}, {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'test','version':'1'}}}, {'jsonrpc':'2.0','method':'notifications/initialized'}, {'jsonrpc':'2.0','id':2,'method':'tools/list'}, {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'unknown','arguments':{}}}]
    process=subprocess.run([sys.executable,'-m','stash.mcp_server','--project',pid],input='\n'.join(json.dumps(v) for v in messages)+'\n',text=True,capture_output=True,timeout=5)
    assert process.returncode==0,process.stderr
    results=[json.loads(v) for v in process.stdout.splitlines()]
    assert len(results)==4 and results[0]['error']['code']==-32002
    assert results[1]['result']['protocolVersion']=='2025-06-18'
    assert len(results[2]['result']['tools'])==7
    assert results[3]['result']['isError']


def test_unavailable_server_and_remote_origin_rejected():
    import pytest
    def offline(*a,**kw): raise httpx.ConnectError('offline')
    bridge=Bridge('http://127.0.0.1:8000',str(uuid4()),request=offline)
    assert bridge.call('project_context',{})['isError']
    with pytest.raises(ValueError): Bridge('http://example.com',str(uuid4()))
