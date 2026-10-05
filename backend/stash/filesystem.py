"""Bounded access to registered roots. Never execute project commands."""
import fcntl
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
from uuid import uuid4

import bleach
from markdown_it import MarkdownIt

SKIP = {".git", ".venv", "venv", "node_modules", "dist", "build", ".output", ".next", "__pycache__", "target", "vendor", ".aws", ".ssh"}
MAX_BYTES = 500_000


class Problem(Exception):
    def __init__(self, code, message, status=422):
        self.code, self.message, self.status = code, message, status


def canonical(raw, require=True):
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        raise Problem("invalid_path", "Provide an absolute directory path")
    try:
        path = candidate.resolve(strict=require)
        if require and (not path.is_dir() or not os.access(path, os.R_OK | os.X_OK)):
            raise Problem("inaccessible", "Directory is not readable")
        return path
    except (OSError, RuntimeError):
        raise Problem("inaccessible", "Directory is missing or inaccessible")


def allowed_name(part):
    lower = part.lower()
    return part not in SKIP and not part.startswith(".") and not lower.endswith((".pem", ".key", ".p12", ".sqlite", ".db")) and lower not in {"credentials", "id_rsa", "id_ed25519"}


def relative(raw):
    path = PurePosixPath(raw)
    if path.is_absolute() or not path.parts or ".." in path.parts or "\\" in raw or any(not allowed_name(p) for p in (path.parts[1:] if path.parts[0] == ".stash" and len(path.parts) >= 2 and path.parts[1] in {"docs", "decisions", "handoffs"} else path.parts)):
        raise Problem("forbidden_path", "Path is outside permitted document scope", 403)
    return path


def check_root(project):
    root = canonical(project.path)
    if str(root) != project.path:
        raise Problem("moved_path", "Registered directory changed; update its path first", 409)
    return root


def scoped(project, raw, write=False, image=False):
    path = relative(raw)
    if image:
        if raw != project.details.get("screenshot") or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise Problem("forbidden_path", "Screenshot is not configured or supported", 403)
    else:
        roots = project.details.get("writable_doc_roots" if write else "doc_roots", ["docs"] if write else ["README.md", "docs"])
        valid = False
        for item in roots:
            configured = relative(item)
            if path == configured or configured in path.parents:
                valid = True
        if not valid or path.suffix.lower() != ".md":
            raise Problem("forbidden_path", "Only Markdown within configured documentation roots is allowed", 403)
    return check_root(project), path


def parent_fd(root, path, create=False):
    """Walk directory descriptors without following symlinks, including write parents."""
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[:-1]:
            if create:
                try:
                    os.mkdir(part, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except Exception:
        os.close(fd)
        raise


def read_at(fd, name, limit=MAX_BYTES):
    source = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    with os.fdopen(source, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise Problem("file_too_large", "File must be a regular file within the size limit")
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise Problem("file_too_large", "File exceeds the size limit")
        return data


def read_bytes(project, raw, image=False):
    root, path = scoped(project, raw, image=image)
    try:
        fd = parent_fd(root, path)
        try:
            return read_at(fd, path.name, 5_000_000 if image else MAX_BYTES)
        finally:
            os.close(fd)
    except FileNotFoundError:
        raise Problem("missing_file", "File is missing", 404)
    except OSError:
        raise Problem("inaccessible_file", "File is inaccessible or uses a symlink", 403)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def document(project, raw):
    data = read_bytes(project, raw)
    try:
        text = data.decode("utf-8")
    except UnicodeError:
        raise Problem("invalid_encoding", "Document must use UTF-8")
    render_text = text
    if raw.startswith((".stash/decisions/", ".stash/handoffs/")):
        import re
        render_text = re.sub(r"<!-- stash-record\n.*?\n-->\n", "", render_text, count=1, flags=re.DOTALL)
        render_text = re.sub(r"<!-- (?:stash-field:[a-z_]+|/stash-field) -->\n?", "", render_text)
    rendered = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"]).render(render_text)
    # Images are omitted: do not load arbitrary remote URLs or local secret assets.
    safe = bleach.clean(rendered, tags={"p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "pre", "code", "blockquote", "a", "strong", "em", "hr", "br", "table", "thead", "tbody", "tr", "th", "td", "s"}, attributes={"a": ["href", "title"], "code": ["class"]}, protocols={"http", "https"}, strip=True)
    return {"path": raw, "content": text, "html": safe, "revision": digest(data)}


def doc_tree(project):
    root = check_root(project)
    found = set()
    missing = []
    for item in project.details.get("doc_roots", ["README.md", "docs"]):
        # Docs is the development journal, separate from repository documentation.
        note_roots = (".stash/docs", ".stash/decisions", ".stash/handoffs")
        if not any(item == note or item.startswith(note + "/") for note in note_roots):
            continue
        path = relative(item)
        target = root / str(path)
        if any((root / str(parent)).is_symlink() for parent in [path, *path.parents] if str(parent) != "."):
            continue
        if not target.exists():
            missing.append(item)
            continue
        if target.is_symlink():
            continue
        if target.is_file():
            if target.suffix.lower() == ".md":
                found.add(item)
            continue
        count = 0
        for current, dirs, files in os.walk(target, followlinks=False):
            dirs[:] = sorted(d for d in dirs if allowed_name(d) and not (Path(current) / d).is_symlink())
            for name in sorted(files):
                file = Path(current) / name
                if allowed_name(name) and file.suffix.lower() == ".md" and not file.is_symlink():
                    found.add(file.relative_to(root).as_posix())
            count += 1
            if count > 2000 or len(found) >= 2000:
                raise Problem("scan_limit", "Document tree is too large; configure narrower roots")
    return {"files": sorted(found), "missing_roots": missing}


def write_document(project, payload, locks_dir, on_saved=None):
    root, path = scoped(project, payload.path, write=True)
    data = payload.content.encode("utf-8")
    if len(data) > MAX_BYTES:
        raise Problem("file_too_large", "Document exceeds the size limit")
    locks_dir.mkdir(parents=True, exist_ok=True)
    key = digest(f"{project.id}:{path}".encode())
    with (locks_dir / key).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            fd = parent_fd(root, path, create=True)
            temp = f".stash-{uuid4().hex}.tmp"
            try:
                try:
                    old = read_at(fd, path.name)
                except FileNotFoundError:
                    old = None
                expected = digest(old) if old is not None else None
                if expected != payload.revision:
                    raise Problem("conflict", "Document changed externally or was removed. Reload and compare before saving", 409)
                mode = stat.S_IMODE(os.stat(path.name, dir_fd=fd, follow_symlinks=False).st_mode) if old is not None else 0o644
                output = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=fd)
                with os.fdopen(output, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    latest = read_at(fd, path.name)
                except FileNotFoundError:
                    latest = None
                if latest != old:
                    raise Problem("conflict", "Document changed while saving; draft was not written", 409)
                if old is None:
                    # link is an atomic create-if-absent operation.
                    try:
                        os.link(temp, path.name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
                    except FileExistsError:
                        raise Problem("conflict", "Document was created externally", 409)
                else:
                    os.replace(temp, path.name, src_dir_fd=fd, dst_dir_fd=fd)
                os.fsync(fd)
            finally:
                try:
                    os.unlink(temp, dir_fd=fd)
                except FileNotFoundError:
                    pass
                os.close(fd)
        except OSError:
            raise Problem("inaccessible_file", "Cannot safely write this document", 403)
        if on_saved:
            on_saved()
    return document(project, payload.path)


def observe(project):
    result = {"observed_at": __import__("stash.models", fromlist=["now"]).now()}
    try:
        root = check_root(project)
    except Problem as error:
        return "missing" if not Path(project.path).exists() else "inaccessible", {**result, "error": error.message}
    # Bounded walk for latest known source mtime. No secret files or .git internals.
    latest, count = 0, 0
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if allowed_name(d) and not (Path(current) / d).is_symlink()]
        for name in files:
            file = Path(current) / name
            if allowed_name(name) and not file.is_symlink():
                try:
                    latest = max(latest, file.stat().st_mtime)
                except OSError:
                    pass
            count += 1
        if count > 5000:
            result["scan_truncated"] = True
            break
    if latest:
        from datetime import datetime, timezone
        result["code_activity_at"] = datetime.fromtimestamp(latest, timezone.utc).isoformat()
    # Presence of .git (including worktree marker) is checked, not scanned.
    if not (root / ".git").exists():
        result["git"] = {"available": False}
        return "available", result
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(Path.home()), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}
    def git(*args):
        run = subprocess.run(["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-C", str(root), *args], capture_output=True, text=True, timeout=5, env=env)
        if run.returncode:
            raise ValueError("Git observation unavailable")
        return run.stdout.strip()[:10000]
    try:
        branch = git("branch", "--show-current") or "Detached HEAD"
        status = git("status", "--porcelain", "--untracked-files=no")
        try:
            commit = git("log", "-1", "--format=%H%n%s%n%cI").splitlines()
        except ValueError:
            commit = []
        result["git"] = {"available": True, "branch": branch, "commit": commit[0] if commit else None, "subject": commit[1] if len(commit) > 1 else None, "committed_at": __import__("datetime").datetime.fromisoformat(commit[2]).astimezone(__import__("datetime").timezone.utc).isoformat() if len(commit) > 2 else None, "dirty": bool(status)}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        result["git"] = {"available": False, "error": "Git could not be inspected"}
    return "available", result
