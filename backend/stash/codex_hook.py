"""Fast, allowlisted hook recorder. No raw commands, output, prompts or transcripts."""
import argparse
from datetime import datetime, timezone
import json
import os
import subprocess
import sys
from uuid import UUID, uuid4, uuid5

from .codex_runtime import Runtime, EVENTS, find_root, key


def capture(payload,root=None,spawn=True):
    if payload.get('hook_event_name') not in EVENTS: return None
    root=find_root(payload['cwd']) if root is None else root
    with Runtime(root) as runtime:
        config=runtime.config()
        if config is None: return None
        runtime_key=key(payload['session_id'])
        binding_path=f'runtime/codex/bindings/{runtime_key}.json'
        session_id=str(uuid5(UUID(config['project_id']),'codex:'+runtime_key))
        runtime.write(binding_path,{'runtime_key':runtime_key,'session_id':session_id},immutable=True)
        binding=runtime.read(binding_path)
        session_id=binding['session_id']
        if str(UUID(session_id))!=session_id: raise ValueError('Invalid session binding')
        event=payload['hook_event_name']
        turn=key(payload['turn_id']) if payload.get('turn_id') else None
        call=key(payload['tool_use_id']) if payload.get('tool_use_id') else None
        identity=f'{event}:{turn}:{call}' if turn and (call or event in {'Stop','Interrupt'}) else str(uuid4())
        event_id=str(uuid5(UUID(session_id),identity))
        value={'id':event_id,'session_id':session_id,'runtime_key':runtime_key,'event':event,'observed_at':datetime.now(timezone.utc).isoformat(),'turn_key':turn,'tool_call_key':call,'actor':{'name':'Codex','kind':'agent'}}
        if event=='SessionStart' and payload.get('source') in {'startup','resume','clear','compact'}: value['source']=payload['source']
        if event=='PostToolUse':
            name=payload.get('tool_name','')
            value['tool']='shell' if name in {'Bash','exec_command'} else 'edit' if name in {'apply_patch','Write','Edit'} else 'mcp' if isinstance(name,str) and name.startswith('mcp__') else 'other'
            response=payload.get('tool_response')
            if isinstance(response,dict):
                code=response.get('exit_code')
                if type(code) is int and -65535<=code<=65535: value['exit_code']=code
                if type(response.get('isError')) is bool: value['tool_error']=response['isError']
        receipt=f'runtime/codex/receipts/{event_id}.json'
        if runtime.read(receipt) is None:
            # Concurrent duplicate deliveries retain the first exact payload for replay.
            runtime.write(f'runtime/codex/outbox/{event_id}.json',value,immutable=True)
        if spawn and config.get('spawn_worker',True):
            try:
                fd=runtime.lock('runtime/codex/worker.lock')
            except BlockingIOError: pass
            else:
                os.close(fd)
                subprocess.Popen([sys.executable,'-m','stash.codex_worker','--root',str(root)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True,close_fds=True)
        return {'session_id':session_id,'runtime_key':runtime_key,'event_id':event_id}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root');parser.add_argument('--no-worker',action='store_true');args=parser.parse_args()
    payload={}
    try:
        raw=sys.stdin.buffer.read(2_000_001)
        if len(raw)>2_000_000: raise ValueError('Hook payload too large')
        payload=json.loads(raw)
        result=capture(payload,args.root,not args.no_worker)
        if result and payload.get('hook_event_name')=='SessionStart':
            print(json.dumps({'hookSpecificOutput':{'hookEventName':'SessionStart','additionalContext':f"Use the stash skill explicitly for this project. Codex runtime key {result['runtime_key']} is bound to stash session {result['session_id']}. Read project context, inspect current code, then record actual task intent with sessions task before editing. Observations may be pending offline; hooks do not write semantic progress or complete tasks."}}))
        elif payload.get('hook_event_name')=='Stop': print('{}')
    except Exception:
        # Never expose payload text or block coding. Protocol outputs remain valid.
        print(json.dumps({'systemMessage':'stash could not save this hook event. Check integrations codex status; earlier records remain available.'}))
    return 0


if __name__=='__main__': raise SystemExit(main())
