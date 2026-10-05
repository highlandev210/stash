"""Project-only integration install/remove; preserve unrelated hooks and custom skills."""
import json
import os
from pathlib import Path
import shlex
import sys
import subprocess
from stash.codex_runtime import Runtime
from stash.filesystem import parent_fd, read_at


def project_read(root,path):
    try: parent=parent_fd(root,Path(path))
    except FileNotFoundError: return None
    try:
        try: return read_at(parent,Path(path).name,2_000_000)
        except FileNotFoundError: return None
    finally: os.close(parent)


def project_write(root,path,content):
    from uuid import uuid4
    parent=parent_fd(root,Path(path),create=True)
    temporary='.stash-install-'+str(uuid4())
    try:
        # Reject a destination symlink before atomic replacement too.
        project_read(root,path)
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
        with os.fdopen(fd,'wb') as stream: stream.write(content);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,Path(path).name,src_dir_fd=parent,dst_dir_fd=parent);os.fsync(parent)
    finally:
        try: os.unlink(temporary,dir_fd=parent)
        except FileNotFoundError: pass
        os.close(parent)


def without_command(hooks,command):
    for event,groups in hooks.get('hooks',{}).items():
        kept=[]
        for group in groups:
            handlers=[h for h in group.get('hooks',[]) if h.get('command')!=command]
            if handlers: kept.append({**group,'hooks':handlers})
        hooks['hooks'][event]=kept
    return hooks


def install(root,server,with_skill=True):
    root=Path(root).resolve(strict=True)
    probe=subprocess.run(['codex','--version'],capture_output=True,text=True,timeout=5)
    version=probe.stdout.strip()
    if probe.returncode or version!='codex-cli 0.160.0':
        raise ValueError('This adapter is currently verified against codex-cli 0.160.0; verify another client/version before installation')
    with Runtime(root) as runtime:
        project=runtime.read('project.json')
        previous=runtime.read('runtime/codex/config.json')
        raw=project_read(root,'.codex/hooks.json')
        hooks=json.loads(raw) if raw else {'hooks':{}}
        if not isinstance(hooks.get('hooks'),dict): raise ValueError('Existing hooks have an unsupported structure')
        if previous and previous.get('command'): without_command(hooks,previous['command'])
        command=shlex.quote(sys.executable)+' -m stash.codex_hook'
        for event in ('SessionStart','PostToolUse','Stop','Interrupt','SessionEnd'):
            group={'hooks':[{'type':'command','command':command,'timeout':3 if event in {'Interrupt','SessionEnd'} else 5,'statusMessage':'stash: queue lifecycle observation'}]}
            hooks['hooks'].setdefault(event,[]).append(group)
        config={'schema_version':1,'project_id':project['id'],'server':server.rstrip('/'),'enabled':False,'spawn_worker':True,'client':'codex-cli','client_version':'0.160.0','command':command}
        from urllib.parse import urlsplit
        url=urlsplit(config['server'])
        if url.scheme!='http' or url.hostname not in {'localhost','127.0.0.1','::1'} or url.username or url.password or url.path not in {'','/'} or url.query or url.fragment:
            raise ValueError('Integration server must be loopback HTTP')
        if with_skill:
            source=Path(__file__).resolve().parents[2]/'agent-skills/stash'
            if not (source/'SKILL.md').is_file(): raise ValueError('Skill source unavailable; install with --no-skill and use the documented skill copy')
            for file in source.rglob('*'):
                if file.is_symlink(): raise ValueError('Skill source must not contain symlinks')
                if file.is_file():
                    target='.agents/skills/stash/'+file.relative_to(source).as_posix()
                    existing=project_read(root,target)
                    if existing is not None and existing!=file.read_bytes(): raise ValueError('Existing customized skill preserved; reconcile it or install with --no-skill')
            for file in source.rglob('*'):
                if file.is_file(): project_write(root,'.agents/skills/stash/'+file.relative_to(source).as_posix(),file.read_bytes())
        project_write(root,'.codex/hooks.json',(json.dumps(hooks,indent=2)+'\n').encode())
        runtime.write('runtime/codex/config.json',{**config,'enabled':True})
        return {'root':str(root),'hooks':'.codex/hooks.json','skill':'.agents/skills/stash' if with_skill else None,'trust_required':True,'next':'Restart Codex and review/trust the project hooks with /hooks. Installation does not bypass trust.'}


def uninstall(root):
    root=Path(root).resolve(strict=True)
    with Runtime(root) as runtime:
        config=runtime.read('runtime/codex/config.json')
        if not config: return {'removed':False,'records_preserved':True}
        runtime.write('runtime/codex/config.json',{**config,'enabled':False})
        raw=project_read(root,'.codex/hooks.json')
        if raw:
            hooks=without_command(json.loads(raw),config['command'])
            project_write(root,'.codex/hooks.json',(json.dumps(hooks,indent=2)+'\n').encode())
        return {'removed':True,'records_preserved':True,'skill_preserved':True,'outbox_preserved':True}
