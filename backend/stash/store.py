"""Portable project memory. No database writes and no mirrored document bodies.

All app writers share the folder lock. A recovery journal makes multi-file changes
and their append-only event durable across interruptions. Every overwrite checks
content hashes, including changes made by editors that don't increment revisions.
"""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
from uuid import UUID

from pydantic import ValidationError

from .filesystem import Problem, digest, read_at
from .models import now, uid
from .schemas import Actor, Comment, Decision, Handoff, IssueInput, ProjectPatch

FORMAT = 1
BRIEF = "docs/brief.md"
METADATA_FIELDS = set(ProjectPatch.model_fields) - {"revision", "actor", "path", "brief"}
RECORD_FIELDS = {
    "decision": ["choice", "reasoning", "alternatives", "reference"],
    "handoff": ["summary", "completed_work", "changed_files", "verification", "unresolved_problems", "blockers", "next_actions", "commit"],
}


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def valid_id(value):
    try:
        if str(UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise Problem("invalid_memory", "stash record ID must be a canonical UUID", 409)
    return value


def validate_record_metadata(item, actor_field="actor"):
    from datetime import datetime
    try:
        valid_id(item["id"])
        valid_id(item["project_id"])
        Actor.model_validate(item[actor_field])
        timestamp = datetime.fromisoformat(item["created_at"])
        if timestamp.tzinfo is None:
            raise ValueError()
    except (KeyError, TypeError, ValueError, ValidationError):
        raise Problem("invalid_memory", "Record identity, attribution, or timestamp is invalid", 409)


def markdown_bytes(record):
    fields = RECORD_FIELDS[record["kind"]]
    header = {k: v for k, v in record.items() if k not in fields}
    text = "<!-- stash-record\n" + json.dumps(header, indent=2, ensure_ascii=False) + "\n-->\n\n"
    text += "# " + ("Session handoff" if record["kind"] == "handoff" else "Decision") + "\n"
    for field in fields:
        value = record.get(field, "")
        # Delimiters are reserved, ordinary Markdown headings remain editable.
        if "<!-- stash-field:" in value or "<!-- /stash-field -->" in value:
            raise Problem("invalid_memory", "stash section markers are reserved")
        text += f"\n<!-- stash-field:{field} -->\n## {field.replace('_', ' ').title()}\n\n{value}\n<!-- /stash-field -->\n"
    return text.encode("utf-8")


def parse_markdown(raw):
    try:
        text = raw.decode("utf-8")
        header, body = text.removeprefix("<!-- stash-record\n").split("\n-->\n", 1)
        record = json.loads(header)
        fields = RECORD_FIELDS[record["kind"]]
        for field in fields:
            marker = f"<!-- stash-field:{field} -->"
            if body.count(marker) != 1:
                raise ValueError()
            section = body.split(marker, 1)[1].split("<!-- /stash-field -->", 1)
            if len(section) != 2:
                raise ValueError()
            lines = section[0].lstrip("\n").split("\n", 1)
            if len(lines) != 2 or not lines[0].startswith("## "):
                raise ValueError()
            record[field] = lines[1].removeprefix("\n").removesuffix("\n")
        schema = Handoff if record["kind"] == "handoff" else Decision
        schema.model_validate({**{k: record[k] for k in fields}, "actor": record["actor"]})
        validate_record_metadata(record)
        return record
    except (UnicodeError, ValueError, KeyError, TypeError, ValidationError):
        raise Problem("invalid_memory", "Invalid stash Markdown record; retain its metadata and section markers", 409)


class FolderStore:
    def __init__(self, project_path):
        self.project_root = Path(project_path)
        self.root = self.project_root / ".stash"
        self.fd = None
        self.project_snapshot = {}
        self.issue_snapshots = {}

    @contextmanager
    def locked(self, create=False):
        if not self.project_root.is_dir() or self.project_root.resolve() != self.project_root:
            raise Problem("missing_project", "Project directory is missing or changed; update its path", 409)
        base = lock = None
        try:
            from .legacy import migrate_memory
            migrate_memory(self.project_root)
            base = os.open(self.project_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            if create:
                try:
                    os.mkdir(".stash", dir_fd=base)
                except FileExistsError:
                    pass
            self.fd = os.open(".stash", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=base)
            lock = os.open(".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=self.fd)
            import stat
            if not stat.S_ISREG(os.fstat(lock).st_mode):
                raise Problem("invalid_memory", "stash lock must be a regular file", 409)
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.recover()
            yield self
        except FileNotFoundError:
            raise Problem("missing_memory", "Project .stash folder or a referenced file is missing", 409)
        except OSError:
            raise Problem("inaccessible_memory", "Project memory is inaccessible or contains a symlink", 403)
        finally:
            if lock is not None:
                os.close(lock)
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
            if base is not None:
                os.close(base)

    def _parent(self, raw, create=False):
        path = PurePosixPath(raw)
        if path.is_absolute() or ".." in path.parts or not path.parts or "\\" in raw:
            raise Problem("invalid_memory", "Invalid stash storage path", 403)
        fd = os.dup(self.fd)
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
            return fd, path.name
        except Exception:
            os.close(fd)
            raise

    def read(self, path):
        try:
            parent, name = self._parent(path)
            try:
                return read_at(parent, name, 2_000_000)
            finally:
                os.close(parent)
        except FileNotFoundError:
            return None

    def write(self, path, content):
        parent, name = self._parent(path, create=True)
        temp = f".write-{uid()}"
        try:
            output = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=parent)
            with os.fdopen(output, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        finally:
            try:
                os.unlink(temp, dir_fd=parent)
            except FileNotFoundError:
                pass
            os.close(parent)

    def json(self, path, required=True):
        raw = self.read(path)
        if raw is None and not required:
            return None
        try:
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, TypeError, UnicodeError):
            raise Problem("invalid_memory", f"Missing or invalid JSON: .stash/{path}", 409)

    def read_project(self, expected_id=None):
        raw = self.read("project.json")
        p = self.json("project.json")
        if p.get("schema_version") != FORMAT:
            raise Problem("unsupported_format", "Unsupported .stash format version", 409)
        valid_id(p.get("id"))
        if expected_id and p["id"] != expected_id:
            raise Problem("identity_conflict", "This folder belongs to a different stash project", 409)
        brief = self.read(BRIEF)
        if brief is None:
            raise Problem("missing_memory", "Project brief is missing: .stash/docs/brief.md", 409)
        try:
            text = brief.decode("utf-8")
            values = {k: p[k] for k in METADATA_FIELDS if k in p}
            validated = ProjectPatch.model_validate({**values, "path": str(self.project_root), "brief": text, "revision": digest(raw + b"\0" + brief)})
        except (UnicodeError, ValidationError):
            raise Problem("invalid_memory", "Project metadata or brief is invalid", 409)
        for field in ["created_at", "updated_at"]:
            if not isinstance(p.get(field), str):
                raise Problem("invalid_memory", f"Missing project {field}", 409)
        self.project_snapshot = {"project.json": raw, BRIEF: brief}
        return {**validated.model_dump(exclude={"actor", "path"}), "id": p["id"], "schema_version": FORMAT, "created_at": p["created_at"], "tracker_updated_at": p["updated_at"]}

    def names(self, directory, suffix):
        try:
            parent, name = self._parent(directory)
            try:
                fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            finally:
                os.close(parent)
        except FileNotFoundError:
            return []
        try:
            names = sorted(name for name in os.listdir(fd) if name.endswith(suffix) and not name.startswith("."))
            if len(names) > 10000:
                raise Problem("scan_limit", "Too many stash records in one directory")
            return [f"{directory}/{name}" for name in names]
        finally:
            os.close(fd)

    def issue(self, issue_id, project_id):
        valid_id(issue_id)
        raw = self.read(f"issues/{issue_id}.json")
        if raw is None:
            raise Problem("not_found", "Issue not found in this project", 404)
        item = self.json(f"issues/{issue_id}.json")
        if item.get("id") != issue_id or item.get("project_id") != project_id:
            raise Problem("invalid_memory", "Issue identity does not match its file", 409)
        try:
            parsed = IssueInput.model_validate({k: item[k] for k in IssueInput.model_fields if k in item})
            Actor.model_validate(item["creator"])
            if not isinstance(item["number"], int) or item["number"] < 1:
                raise ValueError()
        except (ValidationError, KeyError, ValueError):
            raise Problem("invalid_memory", "Issue fields are invalid", 409)
        validate_record_metadata(item, "creator")
        self.issue_snapshots[issue_id] = raw
        return {**parsed.model_dump(exclude={"actor"}), **item, "revision": digest(raw)}

    def issues(self, project_id):
        items = [self.issue(PurePosixPath(path).stem, project_id) for path in self.names("issues", ".json")]
        if len({item["number"] for item in items}) != len(items):
            raise Problem("invalid_memory", "Issue numbers must be unique within a project", 409)
        return items

    def records(self, kind, project_id):
        directory = {"comment": "comments", "decision": "decisions", "handoff": "handoffs"}[kind]
        result = []
        for path in self.names(directory, ".json" if kind == "comment" else ".md"):
            item = self.json(path) if kind == "comment" else parse_markdown(self.read(path))
            if item.get("kind") != kind or item.get("project_id") != project_id or item.get("id") != PurePosixPath(path).stem:
                raise Problem("invalid_memory", "Record identity does not match its file", 409)
            validate_record_metadata(item)
            if kind == "comment":
                try:
                    Comment.model_validate({"body": item["body"], "actor": item["actor"]})
                except (ValidationError, KeyError):
                    raise Problem("invalid_memory", "Comment is invalid", 409)
            result.append(item)
        return sorted(result, key=lambda i: (i["created_at"], i["id"]), reverse=True)

    def activity(self):
        try:
            parent, name = self._parent("activity.jsonl")
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            finally:
                os.close(parent)
        except FileNotFoundError:
            return []
        result = []
        try:
            import stat
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                os.close(fd)
                raise Problem("invalid_memory", "Activity log must be a regular file", 409)
            with os.fdopen(fd, "rb") as stream:
                for line in stream:
                    if len(line) > 2_000_000:
                        raise ValueError()
                    item = json.loads(line)
                    if not isinstance(item, dict) or not {"id", "project_id", "kind", "record_id", "summary", "actor", "created_at"} <= item.keys():
                        raise ValueError()
                    validate_record_metadata(item)
                    if not all(isinstance(item[field], str) for field in ["kind", "record_id", "summary"]):
                        raise ValueError()
                    result.append(item)
        except (ValueError, UnicodeError, TypeError):
            raise Problem("invalid_memory", "Activity log contains an invalid or incomplete entry", 409)
        return result

    def log_bytes(self):
        parent, name = self._parent("activity.jsonl")
        try:
            try:
                return read_at(parent, name, 64_000_000)
            except FileNotFoundError:
                return b""
        finally:
            os.close(parent)

    @staticmethod
    def valid_destination(path):
        item = PurePosixPath(path)
        if item.is_absolute() or ".." in item.parts or "\\" in path:
            raise Problem("invalid_memory", "Invalid recovery destination", 409)
        if path in {"project.json", "runtime/watcher/config.json", "runtime/watcher/state.json"}:
            return
        if len(item.parts) in {3, 4} and item.parts[0] == "sessions":
            valid_id(item.parts[1])
            if len(item.parts) == 3 and item.parts[2] == "session.json":
                return
            if len(item.parts) == 4 and item.parts[2] == "checkpoints" and item.suffix == ".json":
                valid_id(item.stem)
                return
        if len(item.parts) >= 2 and item.parts[0] == "docs" and item.suffix == ".md" and all(not part.startswith(".") for part in item.parts):
            return
        if len(item.parts) == 2 and item.parts[0] in {"issues", "comments", "decisions", "handoffs", "observations", "file_observations", "assessments"}:
            valid_id(item.stem)
            if item.suffix == (".json" if item.parts[0] in {"issues", "comments", "observations", "file_observations", "assessments"} else ".md"):
                return
        raise Problem("invalid_memory", "Recovery destination is not a project record", 409)

    def transaction(self, changes, event=None):
        journal = {"schema_version": 1, "changes": [], "event": event}
        for path, (old, new) in changes.items():
            self.valid_destination(path)
            if len(new) > 2_000_000:
                raise Problem("file_too_large", "stash record exceeds the size limit")
            if self.read(path) != old:
                raise Problem("conflict", "Project files changed externally; reload before saving", 409)
            journal["changes"].append({"path": path, "old_hash": digest(old) if old is not None else None, "content": new.decode("utf-8")})
        if event:
            existing = self.activity()  # reject malformed external history before changing records
            if any(e["id"] == event["id"] for e in existing):
                if next(e for e in existing if e["id"] == event["id"]) == event:
                    event = journal["event"] = None
                else:
                    raise Problem("invalid_memory", "Activity event ID conflict", 409)
            if event:
                log = self.log_bytes()
                journal["activity_base"] = {"size": len(log), "hash": digest(log)}
        if self.read(".transaction.json") is not None:
            raise Problem("conflict", "An earlier stash transaction requires recovery", 409)
        self.write(".transaction.json", json_bytes(journal))
        self.recover()

    def recover(self):
        journal = self.json(".transaction.json", required=False)
        if journal is None:
            return
        if journal.get("schema_version") != 1 or not isinstance(journal.get("changes"), list):
            raise Problem("invalid_memory", "Invalid stash recovery journal", 409)
        try:
            for change in journal["changes"]:
                self.valid_destination(change["path"])
                content = change["content"].encode("utf-8")
                current = self.read(change["path"])
                actual = digest(current) if current is not None else None
                if actual not in {change["old_hash"], digest(content)}:
                    raise Problem("conflict", "Recovery found an external edit. Preserve .transaction.json and resolve the conflict", 409)
            event = journal.get("event")
            remaining = None
            if event:
                base = journal["activity_base"]
                log = self.log_bytes()
                prefix, tail = log[:base["size"]], log[base["size"]:]
                line = (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
                if digest(prefix) != base["hash"] or not line.startswith(tail):
                    raise Problem("conflict", "Activity changed during recovery; existing history was preserved", 409)
                remaining = line[len(tail):]
            for change in journal["changes"]:
                content = change["content"].encode("utf-8")
                current = self.read(change["path"])
                actual = digest(current) if current is not None else None
                if actual not in {change["old_hash"], digest(content)}:
                    raise Problem("conflict", "Project file changed during recovery", 409)
                if current != content:
                    self.write(change["path"], content)
            if remaining:
                # Complete only this journal's known append, including an interrupted final line.
                fd = os.open("activity.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o644, dir_fd=self.fd)
                try:
                    import stat
                    if not stat.S_ISREG(os.fstat(fd).st_mode):
                        raise Problem("invalid_memory", "Activity log must be a regular file", 409)
                    current_log = self.log_bytes()
                    if current_log != log:
                        raise Problem("conflict", "Activity changed while saving", 409)
                    with os.fdopen(fd, "ab", closefd=False) as stream:
                        stream.write(remaining)
                        stream.flush()
                        os.fsync(fd)
                finally:
                    os.close(fd)
        except (KeyError, TypeError, AttributeError, UnicodeError):
            raise Problem("invalid_memory", "Invalid stash recovery journal", 409)
        os.unlink(".transaction.json", dir_fd=self.fd)
        os.fsync(self.fd)

    def initialize(self, project, issues=(), records=(), events=()):
        """Create only missing files. Used by fresh registration and legacy migration."""
        current = self.json("project.json", required=False)
        if current and current.get("id") != project["id"]:
            raise Problem("identity_conflict", "Existing .stash belongs to a different project", 409)
        p = {k: v for k, v in project.items() if k in METADATA_FIELDS}
        p.update(schema_version=FORMAT, id=project["id"], created_at=project["created_at"], updated_at=project["tracker_updated_at"])
        files = {"project.json": json_bytes(p), BRIEF: project.get("brief", "").encode("utf-8")}
        for item in issues:
            files[f"issues/{item['id']}.json"] = json_bytes({k: v for k, v in item.items() if k != "revision"})
        for item in records:
            kind = item["kind"]
            directory = {"comment": "comments", "decision": "decisions", "handoff": "handoffs"}[kind]
            files[f"{directory}/{item['id']}{'.json' if kind == 'comment' else '.md'}"] = json_bytes(item) if kind == "comment" else markdown_bytes(item)
        changes = {}
        for path, content in files.items():
            old = self.read(path)
            if old is None:
                changes[path] = (None, content)
            elif old != content:
                # Retry of a migration must never overwrite independently edited folder files.
                raise Problem("migration_conflict", f"Existing .stash/{path} differs from the database; migration preserved both", 409)
        if changes:
            self.transaction(changes)
        for item in events:
            self.transaction({}, item)
        for name in ["docs", "issues", "comments", "decisions", "handoffs"]:
            parent, leaf = self._parent(name)
            try:
                try:
                    os.mkdir(leaf, dir_fd=parent)
                except FileExistsError:
                    pass
            finally:
                os.close(parent)
        return self.read_project(project["id"])
