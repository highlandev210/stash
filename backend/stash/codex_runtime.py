"""POSIX, stdlib-only durable Codex queue. Hook capture never uses HTTP or scans code."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
from uuid import UUID, uuid4

EVENTS=('SessionStart','PostToolUse','Stop','Interrupt','SessionEnd')


def key(value):
    if not isinstance(value,str) or not value or len(value)>4096:
        raise ValueError('Invalid runtime identity')
    return hashlib.sha256(value.encode()).hexdigest()


def find_root(cwd):
    cwd=Path(cwd).resolve(strict=True)
    for path in [cwd,*cwd.parents]:
        if (path/'.stash/project.json').is_file():
            return path
    raise ValueError('Project is not initialized')


class Runtime:
    def __init__(self,root):
        self.root=Path(root)
        if not self.root.is_absolute() or self.root.resolve()!=self.root:
            raise ValueError('Noncanonical project root')
        self.fd=None

    def __enter__(self):
        base=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try: self.fd=os.open('.stash',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=base)
        finally: os.close(base)
        return self

    def __exit__(self,*_): os.close(self.fd)

    def parent(self,path,create=False):
        parts=Path(path).parts
        if Path(path).is_absolute() or '..' in parts or not parts: raise ValueError('Invalid runtime path')
        fd=os.dup(self.fd)
        try:
            for part in parts[:-1]:
                if create:
                    try: os.mkdir(part,mode=0o700,dir_fd=fd)
                    except FileExistsError: pass
                new=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                os.close(fd);fd=new
            return fd,parts[-1]
        except BaseException:
            os.close(fd);raise

    def read(self,path):
        try: parent,name=self.parent(path)
        except FileNotFoundError: return None
        try:
            try: fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
            except FileNotFoundError: return None
            with os.fdopen(fd,'rb') as stream:
                info=os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size>(2_000_000 if path=='project.json' else 128_000): raise ValueError('Invalid runtime record')
                limit=2_000_000 if path=='project.json' else 128_000
                content=stream.read(limit+1)
                if len(content)>limit: raise ValueError('Runtime record too large')
                return json.loads(content)
        finally: os.close(parent)

    def write(self,path,value,immutable=False):
        content=(json.dumps(value,sort_keys=True)+'\n').encode()
        if len(content)>128_000: raise ValueError('Runtime record too large')
        parent,name=self.parent(path,create=True)
        temporary='.write-'+str(uuid4())
        try:
            fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
            with os.fdopen(fd,'wb') as stream: stream.write(content);stream.flush();os.fsync(stream.fileno())
            if immutable:
                try: os.link(temporary,name,src_dir_fd=parent,dst_dir_fd=parent,follow_symlinks=False)
                except FileExistsError: return False
            else: os.replace(temporary,name,src_dir_fd=parent,dst_dir_fd=parent)
            os.fsync(parent)
            return True
        finally:
            try: os.unlink(temporary,dir_fd=parent)
            except FileNotFoundError: pass
            os.close(parent)

    def delete(self,path):
        parent,name=self.parent(path)
        try:
            try: os.unlink(name,dir_fd=parent);os.fsync(parent)
            except FileNotFoundError: pass
        finally: os.close(parent)

    def names(self,path):
        try:
            parent,name=self.parent(path)
            try: fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
            finally: os.close(parent)
        except FileNotFoundError: return []
        try:
            result=sorted(name for name in os.listdir(fd) if name.endswith('.json'))
            if len(result)>10000: raise ValueError('Queue limit reached')
            return result
        finally: os.close(fd)

    def lock(self,path):
        parent,name=self.parent(path,create=True)
        try: fd=os.open(name,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600,dir_fd=parent)
        finally: os.close(parent)
        if not stat.S_ISREG(os.fstat(fd).st_mode): os.close(fd);raise ValueError('Invalid runtime lock')
        try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BaseException: os.close(fd);raise
        return fd

    def config(self):
        value=self.read('runtime/codex/config.json')
        if not value or not value.get('enabled'): return None
        from urllib.parse import urlsplit
        url=urlsplit(value['server'])
        if url.scheme!='http' or url.hostname not in {'localhost','127.0.0.1','::1'} or url.username or url.password or url.path not in {'','/'} or url.query or url.fragment:
            raise ValueError('Integration server must be loopback HTTP')
        project=self.read('project.json')
        if project['id']!=value['project_id'] or str(UUID(project['id']))!=project['id']: raise ValueError('Project identity mismatch')
        return value


def status(root):
    with Runtime(root) as runtime:
        config=runtime.config()
        pending=runtime.names('runtime/codex/outbox')
        bindings=[runtime.read('runtime/codex/bindings/'+name) for name in runtime.names('runtime/codex/bindings')]
        return {'enabled':bool(config),'pending':len(pending),'bindings':bindings,'worker':runtime.read('runtime/codex/status.json')}
