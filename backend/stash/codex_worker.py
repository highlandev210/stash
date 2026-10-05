"""Drain a durable queue separately from hook deadlines; never write semantic progress."""
import argparse
import os
import time
from datetime import datetime, timezone
from .codex_runtime import Runtime


def drain(root,send=None):
    import httpx
    with Runtime(root) as runtime:
        config=runtime.config()
        if config is None:
            pending=len(runtime.names('runtime/codex/outbox'))
            return {'sent':0,'pending':pending,'error':'disabled' if pending else None}
        try: lock=runtime.lock('runtime/codex/worker.lock')
        except BlockingIOError: return {'sent':0,'pending':len(runtime.names('runtime/codex/outbox')),'error':'worker_busy'}
        count=0;error=None
        try:
            if send is None:
                def send(method,path,payload=None):
                    response=httpx.request(method,config['server'].rstrip('/')+'/api/v1'+path,json=payload,timeout=10,trust_env=False)
                    return response.status_code,response.json() if response.headers.get('content-type','').startswith('application/json') else {}
            files=runtime.names('runtime/codex/outbox')
            entries=sorted(((name,runtime.read('runtime/codex/outbox/'+name)) for name in files),key=lambda pair:(pair[1]['observed_at'],pair[0]))
            deadline=time.monotonic()+20
            for name,event in entries[:50]:
                if time.monotonic()>=deadline: break
                receipt=f"runtime/codex/receipts/{event['id']}.json"
                if runtime.read(receipt): runtime.delete('runtime/codex/outbox/'+name);continue
                base=f"/projects/{config['project_id']}"
                try:
                    code,existing=send('GET',base+f"/sessions/{event['session_id']}")
                    if code==404:
                        code,existing=send('POST',base+'/sessions',{'id':event['session_id'],'origin':'codex_hook','task':'Codex session; task intent not recorded','actor':{'name':'Codex','kind':'agent'}})
                    if code>=400: error=f'http_{code}';break
                    code,result=send('POST',base+'/observations',event)
                    if code>=400: error=f'http_{code}';break
                except httpx.HTTPError:
                    error='server_unavailable';break
                runtime.write(receipt,{'id':event['id'],'accepted':True},immutable=True)
                runtime.delete('runtime/codex/outbox/'+name)
                count+=1
            pending=len(runtime.names('runtime/codex/outbox'))
            value={'sent':count,'pending':pending,'error':error,'checked_at':datetime.now(timezone.utc).isoformat()}
            runtime.write('runtime/codex/status.json',value)
            return value
        finally: os.close(lock)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--once',action='store_true');args=parser.parse_args()
    deadline=time.monotonic()+30
    while True:
        try: result=drain(args.root)
        except Exception: return 1
        if args.once or time.monotonic()>=deadline: return 0 if not result['error'] else 1
        # Stay around briefly for bursts and retry offline delivery. Queue remains after exit.
        time.sleep(2)


if __name__=='__main__': raise SystemExit(main())


def sweep(factory):
    """Server restart/periodic recovery uses the same service layer without self-HTTP."""
    from . import services as svc, sessions, observations
    from .schemas import SessionStart, HookObservation
    from .filesystem import Problem
    with factory() as db:
        for project in svc.all_projects(db):
            try:
                with Runtime(project.path) as runtime:
                    if not runtime.config() or not runtime.names('runtime/codex/outbox'): continue
                def send(method,path,payload=None):
                    try:
                        base=f'/projects/{project.id}'
                        if path==base+'/sessions' and method=='POST':
                            return 200,sessions.start_session(project,SessionStart.model_validate(payload))
                        if path==base+'/observations' and method=='POST':
                            return 200,observations.ingest(project,HookObservation.model_validate(payload))
                        if path.startswith(base+'/sessions/') and method=='GET':
                            return 200,sessions.session_detail(project,path.removeprefix(base+'/sessions/'))
                        return 404,{}
                    except Problem as problem: return problem.status,{}
                drain(project.path,send)
            except Exception:
                # Preserve an inaccessible or malformed outbox; other projects still recover.
                continue
