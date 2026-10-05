#!/usr/bin/env python3
"""Create a disposable, no-Git project for real Codex interruption acceptance.

Run with stash's installed Python. Never points Codex at application source.
"""
import argparse
import json
from pathlib import Path
import shlex
import sys
from uuid import uuid4

from stash import services, sessions, watcher
from stash.db import open_database
from stash.schemas import Registration, Actor, SessionStart, CheckpointInput
from stash_cli.codex_install import install


def prepare(destination):
    destination=Path(destination).resolve()
    destination.mkdir(parents=True,exist_ok=False)
    root=destination/'project';root.mkdir()
    (root/'main.py').write_text('def greet(name):\n    return f"Hello, {name}"\n')
    (root/'README.md').write_text('# Acceptance fixture\nHuman product documentation: preserve this file.\n')
    (root/'test_main.py').write_text('from main import greet\n\ndef test_greet():\n    assert greet("Ada") == "Hello, Ada"\n')
    registry=destination/'registry.db'
    engine,factory=open_database(registry)
    with factory() as db:
        p=services.register(db,Registration(path=str(root)))
        # Existing human records provide a preservation gate.
        from stash.store import FolderStore, json_bytes
        with FolderStore(root).locked() as store:
            old=store.read('project.json');data=json.loads(old)
            data['description']='Human-owned description; preserve during initialization.'
            store.transaction({'project.json':(old,json_bytes(data))})
        actor=Actor(name='Test owner',kind='human')
        for task,next_step in [('Earlier unfinished task','Review greeting edge cases'),('Current interruption task','Add one behavior test then run pytest')]:
            s=sessions.start_session(p,SessionStart(id=str(uuid4()),task=task,actor=actor))
            sessions.save_checkpoint(p,s['id'],CheckpointInput(id=str(uuid4()),revision=s['revision'],progress='Prepared test conditions',next_actions=next_step,verification='No checks claimed yet',actor=actor))
        watcher.configure(p,True,actor);watcher.poll(p)
        pid=p.id
    engine.dispose()
    integration=install(root,'http://127.0.0.1:8000',with_skill=True)
    python=shlex.quote(sys.executable)
    cli=shlex.quote(str(Path(sys.executable).parent/'stash'))
    prompt='''Use $stash explicitly. Initialize this existing fixture without changing its human description or README. Resume and inspect both unfinished sessions. Record your actual task in the session supplied by SessionStart. Add a behavior test for an empty name, run pytest, and checkpoint the actual result. Then begin changing the implementation and keep working until I interrupt. Save checkpoints before risky/long operations. Never create a final checkpoint merely because a turn stops or is interrupted. Do not edit outside this fixture or record secrets.'''
    (destination/'codex-prompt.txt').write_text(prompt+'\n')
    (destination/'conditions.json').write_text(json.dumps({'project_id':pid,'project_path':str(root),'registry':str(registry),'client_version':integration['client_version'] if 'client_version' in integration else 'codex-cli 0.160.0'},indent=2)+'\n')
    instructions=f'''# Live interruption acceptance

This is a disposable fixture, with its own registry and no Git. Do not confuse it with your normal stash registry. No agent has run yet; preparation is not gate completion.

1. Stop any service occupying port 8000. In a terminal start the isolated backend:

   STASH_DB={shlex.quote(str(registry))} {python} -m uvicorn stash.api:create_app --factory --host 127.0.0.1 --port 8000

2. In another terminal: cd {shlex.quote(str(root))}, open Codex, review/trust `/hooks`, and paste codex-prompt.txt. Check that SessionStart supplies a stash session ID. Initialize twice and confirm human data remains.
3. After a real tool result and semantic checkpoint, interrupt the active turn. Verify Interrupt is observed without a final checkpoint. Then repeat, abruptly terminating the Codex process during work; no shutdown hook is assumed.
4. Stop the backend, make a saved editor change, and open a Codex session while it is offline. Interrupt. Check pending files under .stash/runtime/codex/outbox, preserving them.
5. Restart the backend with the same registry. Use `{cli} --project {pid} --json context` and integration status. Verify pending events drain once; prior progress, next actions, and incomplete sessions remain. New events do not mark work complete.
6. Resume in a fresh Codex session. Optionally use another editor/agent via the skill and watcher; no extra agent hook adapter is installed. Confirm saved changes are visible without a final handoff.
7. In the browser edit an issue while an agent holds its old revision. Require conflict handling, not a silent overwrite. Add human and agent comments and verify attribution/history. Stop services, rename the fixture project, update its registered path through Overview, restart, and confirm its ID, history, watcher baseline, and queued events remain recoverable.
8. Record actual commands/results and observed events in a checkpoint. The live gate is passed only after these observations, never merely because setup succeeded.

MCP command (project-scoped): `{python} -m stash.mcp_server --project {pid}`. See docs/mcp.md to connect it in Codex. Keep stash running for API operations.
'''
    (destination/'ACCEPTANCE.md').write_text(instructions)
    print(json.dumps({'conditions':str(destination/'conditions.json'),'instructions':str(destination/'ACCEPTANCE.md'),'prompt':str(destination/'codex-prompt.txt'),'project_id':pid}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('destination',type=Path);prepare(parser.parse_args().destination)
