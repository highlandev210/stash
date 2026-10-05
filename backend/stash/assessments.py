"""Evidence-based onboarding and reassessment; proposals never overwrite human work."""
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import signal
import sys
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from pydantic import ValidationError

from . import services as svc
from .filesystem import Problem, check_root, parent_fd, read_at
from .models import now, uid
from .schemas import IssueInput, ProjectPatch
from .sessions import observe_repository, validate_observation, validate_time
from .store import FolderStore, BRIEF, METADATA_FIELDS, digest, json_bytes, valid_id

FIELDS = {'description', 'purpose', 'stack', 'brief', 'focus', 'next_step', 'setup_command', 'run_command', 'test_command'}


def read_source(root, path):
    fd = parent_fd(root, Path(path))
    try:
        return read_at(fd, Path(path).name, 100_000).decode('utf-8')
    finally:
        os.close(fd)


def history(project):
    with FolderStore(check_root(project)).locked() as store:
        store.read_project(project.id)
        return sorted([{**load(store, Path(name).stem, project.id), 'revision': digest(store.read(name))} for name in store.names('assessments', '.json')], key=lambda a: a['created_at'], reverse=True)


def load(store, assessment_id, project_id):
    valid_id(assessment_id)
    value = store.json(f'assessments/{assessment_id}.json')
    try:
        if value['id'] != assessment_id or value['project_id'] != project_id or value['status'] not in {'draft', 'accepted'}:
            raise ValueError()
        validate_time(value['created_at'])
        validate_observation(value['observation'])
        if not isinstance(value['proposed'], dict) or set(value['proposed']) - FIELDS:
            raise ValueError()
        if not isinstance(value['needs_goal'], bool) or not isinstance(value['project_revision'], str):
            raise ValueError()
        if not isinstance(value['candidates'], list) or len(value['candidates']) > 400:
            raise ValueError()
        for candidate in value['candidates']:
            if not re.fullmatch(r'[0-9a-f]{64}', candidate['id']) or candidate['confidence'] not in {'observed', 'inferred', 'needs_review', 'user_supplied'}:
                raise ValueError()
            IssueInput(title=candidate['title'], description=candidate['description'], type=candidate['type'])
            if not isinstance(candidate['evidence'], str) or not candidate['evidence']:
                raise ValueError()
            if candidate.get('existing_issue_id'): valid_id(candidate['existing_issue_id'])
        if not isinstance(value['checks'], list) or any(c['status'] not in {'passed', 'failed', 'not_run', 'unavailable'} for c in value['checks']):
            raise ValueError()
    except (KeyError, ValueError, TypeError, ValidationError):
        raise Problem('invalid_memory', 'Invalid project assessment record', 409)
    return value


def assess(db, project, payload):
    root = check_root(project)
    current = svc.project_dict(db, project)
    observation = observe_repository(root)
    warnings = list(observation['warnings'])
    evidence, candidates, checks = [], [], []
    sources = {}
    total = 0
    # Fingerprint scan already excludes hidden files, secrets, dependencies and symlinks.
    paths = sorted(observation['fingerprints'], key=lambda p: (p.count('/'), p.lower()))
    preferred = [p for p in paths if Path(p).name.lower().startswith('readme') or p in {'package.json', 'pyproject.toml'} or p.startswith(('docs/', 'src/', 'tests/', 'backend/', 'app/')) or Path(p).suffix.lower() in {'.py', '.tsx', '.ts', '.jsx', '.js'}]
    for path in preferred[:120]:
        if Path(path).suffix.lower() not in {'.md', '.json', '.toml', '.py', '.tsx', '.ts', '.jsx', '.js', '.html', '.css'}:
            continue
        try:
            text = read_source(root, path)
            total += len(text.encode())
            if total > 1_000_000:
                warnings.append('Assessment content limit reached; remaining files were not inspected')
                break
            sources[path] = text
            evidence.append({'path': path, 'hash': digest(text.encode()), 'kind': 'inspected'})
        except (OSError, UnicodeError, Problem):
            warnings.append(f'Could not inspect {path}')
    if len(preferred) > 120:
        warnings.append('Assessment file limit reached; inspection is partial')

    def candidate(title, description, reference, kind='task', confidence='observed'):
        key = digest((kind + '\0' + title.casefold() + '\0' + reference).encode())
        candidates.append({'id': key, 'title': title, 'description': description, 'evidence': reference, 'type': kind, 'confidence': confidence})

    package = {}
    if 'package.json' in sources:
        try:
            package = json.loads(sources['package.json'])
            if not isinstance(package, dict): raise ValueError()
            checks.append({'name': 'package.json syntax', 'status': 'passed', 'evidence': 'package.json'})
        except ValueError:
            package = {}
            candidate('Fix invalid package.json', 'The package manifest could not be parsed as a JSON object.', 'package.json', 'bug')
            checks.append({'name': 'package.json syntax', 'status': 'failed', 'evidence': 'package.json'})
    python_manifest = {}
    if 'pyproject.toml' in sources:
        try:
            python_manifest = tomllib.loads(sources['pyproject.toml'])
            checks.append({'name': 'pyproject.toml syntax', 'status': 'passed', 'evidence': 'pyproject.toml'})
        except tomllib.TOMLDecodeError:
            candidate('Fix invalid pyproject.toml', 'The Python manifest could not be parsed.', 'pyproject.toml', 'bug')
            checks.append({'name': 'pyproject.toml syntax', 'status': 'failed', 'evidence': 'pyproject.toml'})
    for path, text in sources.items():
        if path.endswith('.py'):
            try:
                ast.parse(text, filename=path)
            except SyntaxError as error:
                reference = f'{path}:{error.lineno}'
                candidate(f'Fix Python syntax in {path}', error.msg, reference, 'bug')
                checks.append({'name': f'Python syntax: {path}', 'status': 'failed', 'evidence': reference})
                continue
            checks.append({'name': f'Python syntax: {path}', 'status': 'passed', 'evidence': path})
        for number, line in enumerate(text.splitlines(), 1):
            match = re.search(r'\b(TODO|FIXME)\b[:\s-]*(.{3,200})', line)
            if match and len(candidates) < 80:
                candidate(match.group(2).strip()[:250], 'Source annotation requires review; it is not a confirmed bug.', f'{path}:{number}', 'task', 'needs_review')

    scripts = package.get('scripts', {})
    if not isinstance(scripts, dict): scripts = {}
    available = {f'npm:{name}': ['npm', 'run', name] for name in ('test', 'check', 'lint', 'build') if isinstance(scripts.get(name), str)}
    if python_manifest or any(p.endswith('.py') for p in sources):
        available['python:pytest'] = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider']
    if set(payload.run_checks) - set(available):
        raise Problem('invalid_check', 'Select only checks advertised by the repository assessment')
    for name in payload.run_checks:
        try:
            # The user explicitly selects execution; no manifest command runs during inspection.
            process = subprocess.Popen(available[name], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, env={**os.environ, 'CI': '1', 'PYTHONDONTWRITEBYTECODE': '1'})
            try:
                process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise
            status = 'passed' if process.returncode == 0 else 'failed'
            checks.append({'name': name, 'status': status, 'exit_code': process.returncode, 'evidence': 'Explicitly executed in project directory'})
            if process.returncode:
                candidate(f'Investigate failing {name} check', f'Explicit check exited with code {process.returncode}. Rerun locally for diagnostics; failure alone does not identify a code defect.', name, 'task')
        except (OSError, subprocess.TimeoutExpired):
            checks.append({'name': name, 'status': 'unavailable', 'evidence': 'Could not launch or exceeded 60-second limit'})
    for name in available:
        if name not in payload.run_checks:
            checks.append({'name': name, 'status': 'not_run', 'evidence': 'Available command; execution requires selection'})
    readmes = [text for path, text in sources.items() if Path(path).name.lower().startswith('readme')]
    inferred_description = ''
    if readmes:
        paragraphs = re.split(r'\n\s*\n', readmes[0])
        inferred_description = next((p.strip().replace('\n', ' ')[:1000] for p in paragraphs if p.strip() and not p.lstrip().startswith(('#', '```', '!', '|', '['))), '')
    if not inferred_description and package.get('description'):
        inferred_description = str(package['description'])[:1000]
    goal = payload.goal.strip()
    if not goal and not inferred_description and not current.get('purpose'):
        warnings.append('Project intent is unknown. Supply an intended goal before accepting initialization.')
    deps = package.get('dependencies', {})
    stack = [name for name in ('react', 'next', 'vue', 'svelte', 'express', 'vite') if isinstance(deps, dict) and name in deps]
    if python_manifest: stack.append('Python')
    if package: stack.append('Node.js')
    for requirement in payload.requirements:
        if requirement.strip():
            candidate(requirement.strip()[:250], 'User-supplied requirement. Implementation and acceptance criteria need review.', 'User requirements', 'task', 'user_supplied')
    documented_features = []
    for text in readmes:
        for line in text.splitlines():
            if line.startswith(('- ', '* ')) and len(documented_features) < 15:
                documented_features.append(line[2:][:300])
    modules = sorted({p.split('/')[0] for p in sources if '/' in p and not p.startswith('docs/')})
    summary = '\n'.join([
        f'# Repository assessment ({payload.mode})',
        f'Assessed: {now()}',
        f'Intended goal: {goal or current.get("purpose") or inferred_description or "Unknown"}',
        'Purpose inferred from documentation: ' + (inferred_description or 'Unknown'),
        'Architecture evidence: ' + ', '.join(p for p in sources if p.endswith(('package.json', 'pyproject.toml'))) + '; observed source areas: ' + ', '.join(modules) + '; detected stack: ' + ', '.join(stack),
        'Source entry points inspected: ' + ', '.join(p for p in sources if Path(p).name in {'main.py', 'main.tsx', 'App.tsx', 'index.ts', 'index.js', 'app.py'}),
        'Test files inspected: ' + ', '.join(p for p in sources if 'test' in p.lower()),
        'Documented features (inferred, not behaviorally verified): ' + '; '.join(documented_features or ['Unknown; semantic source review is needed.']),
        'Current work: ' + (current.get('focus') or 'Unknown; saved file and Git observations are available separately.'),
        'Existing memory: retained brief, issues, decisions and handoffs; no historical records were replaced.',
        'Requirements: ' + '; '.join(payload.requirements),
        'Checks: ' + '; '.join(f'{c["name"]}: {c["status"]}' for c in checks),
        'Limitations: bounded inspection; inferred context and source annotations need review. ' + '; '.join(warnings),
        'Next action: review proposed context and issue candidates, then continue the highest-priority supported task.',
    ])
    proposed = {'description': inferred_description, 'purpose': goal or current.get('purpose') or inferred_description,
                'stack': stack, 'brief': summary, 'focus': current.get('focus') or (payload.requirements[0] if payload.mode == 'new' and payload.requirements else ''), 'next_step': 'Review assessment findings and choose the next task.'}
    if 'dev' in scripts: proposed['run_command'] = 'npm run dev'
    if 'test' in scripts: proposed['test_command'] = 'npm test'
    if package: proposed['setup_command'] = 'npm ci' if (root / 'package-lock.json').is_file() else 'npm install'
    elif python_manifest: proposed['setup_command'] = 'python -m pip install -e .'
    existing = svc.list_issues(db, project)
    def memory_summary(records):
        return [{k: (v[:2000] if isinstance(v, str) else v) for k, v in record.items() if k in {'id', 'title', 'status', 'description', 'choice', 'reasoning', 'summary', 'next_actions', 'verification', 'created_at', 'actor', 'creator'}} for record in records]
    memory = {'brief': current.get('brief', ''), 'issues': memory_summary(existing[:50]), 'decisions': memory_summary(svc.records(db, project.id, 'decision', 5)), 'handoffs': memory_summary(svc.records(db, project.id, 'handoff', 5))}
    for c in candidates:
        matches = [i for i in existing if i['title'].strip().casefold() == c['title'].strip().casefold() or 'assessment:' + c['id'] in i.get('labels', [])]
        c['existing_issue_id'] = matches[0]['id'] if matches else None
    assessment_id = uid()
    # Checks may alter files. Capture the actual post-check state used for approval freshness.
    after = observe_repository(root)
    checks_changed_source = any(after['fingerprints'].get(e['path']) != e['hash'] for e in evidence)
    if checks_changed_source:
        warnings.append('Checks changed inspected files. Inspect again before accepting this assessment.')
    result = {'id': assessment_id, 'project_id': project.id, 'created_at': now(), 'actor': payload.actor.model_dump(),
              'checks_changed_source': checks_changed_source, 'mode': payload.mode, 'goal': goal, 'requirements': payload.requirements,
              'project_revision': current['revision'], 'observation': after, 'inspection_observation': observation,
              'memory': memory, 'evidence': evidence, 'warnings': warnings, 'checks': checks, 'available_checks': list(available),
              'proposed': proposed, 'candidates': candidates, 'status': 'draft', 'applied': None,
              'needs_goal': not bool(goal or inferred_description or current.get('purpose'))}
    with FolderStore(root).locked() as store:
        store.read_project(project.id)
        store.transaction({f'assessments/{assessment_id}.json': (None, json_bytes(result))}, svc.new_event(project.id, 'assessment', assessment_id, 'Repository assessed; review required', payload.actor))
    return {**result, 'revision': digest(json_bytes(result))}


def approve(db, project, assessment_id, payload):
    root = check_root(project)
    observed = observe_repository(root)
    with FolderStore(root).locked() as store:
        current = store.read_project(project.id)
        path = f'assessments/{valid_id(assessment_id)}.json'
        raw = store.read(path)
        report = load(store, assessment_id, project.id)
        if report.get('status') == 'accepted':
            if report.get('approval') != payload.model_dump():
                raise Problem('conflict', 'Assessment was already accepted with different selections', 409)
            return report
        if digest(raw) != payload.revision or current['revision'] != report['project_revision']:
            raise Problem('conflict', 'Project or assessment changed. Reassess before applying this draft', 409)
        baseline = report['observation']
        if observed['fingerprints'] != baseline['fingerprints'] or observed['head'] != baseline['head'] or observed['working_tree'] != baseline['working_tree']:
            raise Problem('stale_assessment', 'Repository changed since assessment. Reassess before accepting', 409)
        if report.get('checks_changed_source'):
            raise Problem('stale_assessment', 'Checks changed inspected files; reassess before accepting', 409)
        if report['needs_goal']:
            raise Problem('missing_goal', 'Supply the intended project goal and reassess')
        selected = set(payload.fields)
        ids = set(payload.candidates)
        known = {c['id'] for c in report['candidates']}
        if selected - FIELDS or selected - report['proposed'].keys() or ids - known:
            raise Problem('invalid_selection', 'Unknown context field or candidate')
        merged = {**current, **{k: report['proposed'][k] for k in selected}}
        try:
            validated = ProjectPatch.model_validate({**{k: merged[k] for k in ProjectPatch.model_fields if k in merged}, 'path': project.path})
        except ValidationError as error:
            raise Problem('invalid_memory', 'Assessment proposes invalid context; preserve and reconcile the draft', 409) from error
        writes = {}
        if selected:
            metadata = {k: v for k, v in validated.model_dump().items() if k in METADATA_FIELDS}
            metadata.update(schema_version=1, id=project.id, created_at=current['created_at'], updated_at=now())
            writes['project.json'] = (store.project_snapshot['project.json'], json_bytes(metadata))
            writes[BRIEF] = (store.project_snapshot[BRIEF], validated.brief.encode())
        existing = store.issues(project.id)
        number = max((i['number'] for i in existing), default=0)
        created, linked = [], []
        for c in report['candidates']:
            if c['id'] not in ids: continue
            duplicate = next((i for i in existing if i['title'].strip().casefold() == c['title'].strip().casefold() or 'assessment:' + c['id'] in i.get('labels', [])), None)
            if duplicate:
                linked.append(duplicate['id'])
                continue
            number += 1
            issue = IssueInput(title=c['title'], type=c['type'], description=c['description'] + '\n\nEvidence: ' + c['evidence'], labels=['assessment:' + c['id']])
            item = {**issue.model_dump(exclude={'actor'}), 'id': uid(), 'project_id': project.id, 'number': number, 'creator': payload.actor.model_dump(), 'created_at': now(), 'updated_at': now()}
            writes[f'issues/{item["id"]}.json'] = (None, json_bytes(item))
            existing.append(item)
            created.append(item['id'])
        session_id, checkpoint_id = uid(), uid()
        timestamp = now()
        session = {'schema_version': 1, 'origin': 'explicit', 'intent_recorded': True, 'id': session_id, 'project_id': project.id,
                   'actor': payload.actor.model_dump(), 'created_at': timestamp, 'updated_at': timestamp,
                   'task': 'Initialize project context' if report['mode'] == 'new' else 'Assess existing repository',
                   'status': 'incomplete', 'latest_checkpoint_id': checkpoint_id, 'observation': observed}
        from .schemas import CheckpointInput
        explanation = CheckpointInput(id=checkpoint_id, revision='assessment', progress=f'Assessment {assessment_id} accepted; {len(created)} issues created and {len(linked)} linked.',
                                      unfinished_work='Review unresolved issues and complete any verification not run.',
                                      next_actions=merged.get('next_step') or 'Choose the next supported task.',
                                      verification='; '.join(f'{c["name"]}: {c["status"]}' for c in report['checks']), final=False).model_dump(exclude={'actor', 'id', 'revision'})
        checkpoint = {'schema_version': 1, 'id': checkpoint_id, 'project_id': project.id, 'session_id': session_id,
                      'created_at': timestamp, 'actor': payload.actor.model_dump(), 'base_revision': 'assessment', 'explanation': explanation, 'observation': observed}
        writes[f'sessions/{session_id}/session.json'] = (None, json_bytes(session))
        writes[f'sessions/{session_id}/checkpoints/{checkpoint_id}.json'] = (None, json_bytes(checkpoint))
        report.update(status='accepted', approval=payload.model_dump(), applied={'fields': sorted(selected), 'created_issues': created, 'linked_issues': linked, 'session_id': session_id, 'checkpoint_id': checkpoint_id, 'actor': payload.actor.model_dump(), 'at': now()})
        writes[path] = (raw, json_bytes(report))
        # Preserve an initial baseline even if tracking is disabled; acceptance and baseline are atomic.
        from .watcher import CONFIG, STATE
        old_state = store.read(STATE)
        if old_state is None:
            writes[STATE] = (None, json_bytes({'checked_at': observed['captured_at'], 'fingerprints': observed['fingerprints'], 'complete': observed['complete'], 'warnings': observed['warnings']}))
        writes[CONFIG] = (store.read(CONFIG), json_bytes({'enabled': payload.enable_watcher}))
        store.transaction(writes, svc.new_event(project.id, 'assessment', assessment_id, f'Assessment accepted: {len(created)} issues created, {len(linked)} linked', payload.actor))
    svc.project_dict(db, project)
    return report


def refine(db, project, assessment_id, payload):
    """Human corrections or an external agent's semantic analysis, kept as a reviewable draft."""
    root = check_root(project)
    observed = observe_repository(root)
    with FolderStore(root).locked() as store:
        current = store.read_project(project.id)
        path = f'assessments/{valid_id(assessment_id)}.json'
        raw = store.read(path)
        report = load(store, assessment_id, project.id)
        if report['status'] != 'draft' or digest(raw) != payload.revision or current['revision'] != report['project_revision']:
            raise Problem('conflict', 'Assessment or project changed; reload before refining', 409)
        if observed['fingerprints'] != report['observation']['fingerprints']:
            raise Problem('stale_assessment', 'Repository changed; reassess before refining', 409)
        if set(payload.proposed) - FIELDS:
            raise Problem('invalid_field', 'Only reviewable context fields can be proposed')
        proposed = {**report['proposed'], **payload.proposed}
        # Validate metadata types and bounds before storing a proposal.
        try:
            ProjectPatch.model_validate({**{k: current[k] for k in ProjectPatch.model_fields if k in current}, **proposed, 'path': project.path})
        except ValidationError as error:
            raise Problem('invalid_context', 'Proposed context has invalid types or exceeds field limits') from error
        existing = store.issues(project.id)
        candidates = {c['id']: c for c in report['candidates']}
        for finding in payload.findings:
            for reference in finding.evidence:
                source = reference.rsplit(':', 1)[0] if re.search(r':\d+$', reference) else reference
                if source not in report['observation']['fingerprints'] and source not in {c['name'] for c in report['checks']}:
                    raise Problem('invalid_evidence', 'Findings must reference observed project files or recorded checks')
            reference = '; '.join(finding.evidence)
            key = digest((finding.type + '\0' + finding.title.casefold() + '\0' + reference).encode())
            duplicate = next((i for i in existing if i['title'].strip().casefold() == finding.title.strip().casefold()), None)
            candidates[key] = {**finding.model_dump(exclude={'evidence'}), 'id': key, 'evidence': reference, 'existing_issue_id': duplicate['id'] if duplicate else None}
        if len(candidates) > 400:
            raise Problem('candidate_limit', 'Limit each assessment to 400 candidate issues')
        report.update(proposed=proposed, candidates=list(candidates.values()), analysis=payload.analysis,
                      reviewed_by=payload.actor.model_dump(), needs_goal=not bool(proposed.get('purpose')))
        store.transaction({path: (raw, json_bytes(report))}, svc.new_event(project.id, 'assessment', assessment_id, 'Assessment analysis refined; review required', payload.actor))
        return {**report, 'revision': digest(json_bytes(report))}
