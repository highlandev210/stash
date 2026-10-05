"""Copy prior Trackle memory into stash without changing the original files."""
import json
import os
from pathlib import Path
import shutil

from .filesystem import Problem
from .models import uid


def migrate_memory(root):
    root = Path(root)
    legacy = root / '.trackle'
    target = root / '.stash'
    if target.exists() or not legacy.exists():
        return
    if legacy.is_symlink() or not legacy.is_dir():
        raise Problem('migration_conflict', 'Legacy project memory must be a real directory', 409)
    if (legacy / '.transaction.json').exists():
        raise Problem('migration_pending', 'Recover the pending legacy transaction with the previous app before migrating', 409)
    stage = root / ('.stash-migration-' + uid())
    stage.mkdir(mode=0o700)
    total, count = 0, 0
    try:
        for current, dirs, files in os.walk(legacy, followlinks=False):
            for name in dirs + files:
                if (Path(current) / name).is_symlink():
                    raise Problem('migration_conflict', 'Legacy memory contains a symlink; original files were preserved', 409)
            relative = Path(current).relative_to(legacy)
            (stage / relative).mkdir(exist_ok=True)
            for name in files:
                if name == '.lock': continue
                source = Path(current) / name
                count += 1
                size = source.stat().st_size
                total += size
                if not source.is_file() or count > 10000 or size > 2_000_000 or total > 50_000_000:
                    raise Problem('migration_conflict', 'Legacy memory exceeds migration limits or contains a special file', 409)
                raw = source.read_bytes()
                if relative == Path('.') and name == 'project.json':
                    metadata = json.loads(raw)
                    for field in ('doc_roots', 'writable_doc_roots'):
                        metadata[field] = [p.replace('.trackle/', '.stash/') for p in metadata.get(field, [])]
                    raw = (json.dumps(metadata, indent=2, ensure_ascii=False) + '\n').encode()
                elif name.endswith('.md'):
                    raw = raw.replace(b'<!-- trackle-record', b'<!-- stash-record').replace(b'<!-- trackle-field:', b'<!-- stash-field:').replace(b'<!-- /trackle-field -->', b'<!-- /stash-field -->')
                (stage / relative / name).write_bytes(raw)
        # Never activate stale hook configuration/queued delivery during a name migration.
        config = stage / 'runtime/codex/config.json'
        if config.exists(): config.rename(config.with_name('legacy-config.json'))
        os.rename(stage, target)
    except (OSError, ValueError) as error:
        raise Problem('migration_conflict', 'Legacy memory could not be migrated; original files were preserved', 409) from error
    finally:
        if stage.exists(): shutil.rmtree(stage)
