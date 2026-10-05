import json
from pathlib import Path

import pytest
from stash.api import create_app
from support import TestClient


@pytest.fixture
def app_client(tmp_path):
    with TestClient(create_app(db_path=tmp_path / 'shelf.db', test=True)) as client:
        yield client


def register(client, root):
    root.mkdir()
    response = client.post('/api/v1/projects', json={'path': str(root)})
    assert response.status_code == 200, response.text
    return '/api/v1/projects/' + response.json()['id']


def inspect(client, base, **values):
    response = client.post(base + '/assessments', json=values)
    assert response.status_code == 200, response.text
    return response.json()


def accept(client, base, report, **values):
    return client.post(base + '/assessments/' + report['id'] + '/approve', json={'revision': report['revision'], **values})


def test_existing_inspection_review_preservation_dedup_and_tracking(app_client, tmp_path):
    c = app_client
    root = tmp_path / 'existing'
    base = register(c, root)
    (root / 'README.md').write_text('# Existing app\n\nOrganizes books for readers.\n')
    (root / 'main.py').write_text('def broken(:\n    pass\n')
    (root / '.env').write_text('PASSWORD=NEVER_INCLUDE_ME')
    (root / 'node_modules').mkdir()
    (root / 'node_modules' / 'bad.py').write_text('INVALID')
    current = c.get(base).json()
    update = {k: current[k] for k in ('revision', 'name', 'path')}
    update.update(description='Human description', purpose='Human purpose', brief='Human brief')
    assert c.put(base, json=update).status_code == 200
    old = c.post(base + '/issues', json={'title': 'Fix Python syntax in main.py', 'description': 'Human diagnosis'}).json()
    report = inspect(c, base, goal='Help readers organize books')
    assert report['memory']['brief'] == 'Human brief'
    assert report['candidates'][0]['existing_issue_id'] == old['id']
    assert 'NEVER_INCLUDE_ME' not in json.dumps(report)
    assert not any('node_modules' in e['path'] for e in report['evidence'])
    assert c.get(base).json()['description'] == 'Human description'
    result = accept(c, base, report, fields=['purpose'], candidates=[report['candidates'][0]['id']], enable_watcher=True)
    assert result.status_code == 200, result.text
    assert result.json()['applied']['created_issues'] == []
    assert result.json()['applied']['linked_issues'] == [old['id']]
    assert c.get(base).json()['description'] == 'Human description'
    assert c.get(base).json()['brief'] == 'Human brief'
    assert c.get(base).json()['purpose'] == 'Help readers organize books'
    assert c.get(base + '/issues/' + old['id']).json()['description'] == 'Human diagnosis'
    assert c.get(base + '/watcher').json()['enabled'] is True
    resume = c.get(base + '/context').json()['resume']
    assert resume['session']['status'] == 'incomplete'
    assert 'failed' in resume['checkpoint']['explanation']['verification']
    # Retry acceptance never duplicates records.
    assert accept(c, base, report, fields=['purpose'], candidates=[report['candidates'][0]['id']]).status_code == 200
    assert len(c.get(base + '/issues').json()['items']) == 1
    # First subsequent change compares against the acceptance baseline.
    (root / 'main.py').write_text('print("fixed")\n')
    from stash import watcher, services
    with c.app.state.session_factory() as db:
        observation = watcher.poll(services.get_project(db, base.rsplit('/', 1)[-1]))
        assert observation['modified'] == ['main.py']
    second = inspect(c, base, goal='Help readers organize books')
    assert not any(x['title'] == old['title'] for x in second['candidates'])
    assert c.get(base + '/issues/' + old['id']).json()['status'] == 'backlog'


def test_stale_source_metadata_and_cross_project(app_client, tmp_path):
    c = app_client
    base = register(c, tmp_path / 'a')
    other = register(c, tmp_path / 'b')
    report = inspect(c, base, goal='Build an app')
    assert accept(c, other, report).status_code == 409
    (tmp_path / 'a' / 'new.py').write_text('print(1)')
    assert accept(c, base, report).status_code == 409
    report = inspect(c, base, goal='Build an app')
    project = c.get(base).json()
    assert c.put(base, json={k: project[k] for k in ('revision', 'name', 'path')} | {'focus': 'Human changed focus'}).status_code == 200
    assert accept(c, base, report).status_code == 409


def test_new_folder_goal_requirements_and_review(app_client, tmp_path):
    c = app_client
    root = tmp_path / 'brand-new'
    created = c.post('/api/v1/projects/create', json={'path': str(root)})
    assert created.status_code == 200
    assert c.post('/api/v1/projects/create', json={'path': str(root)}).status_code == 409
    base = '/api/v1/projects/' + created.json()['id']
    missing = inspect(c, base, mode='new')
    assert missing['needs_goal'] is True
    assert accept(c, base, missing).status_code == 422
    report = inspect(c, base, mode='new', goal='A reading list', requirements=['Add books', 'Mark books as read'])
    assert c.get(base + '/issues').json()['total'] == 0
    assert accept(c, base, report, fields=['purpose'], candidates=[x['id'] for x in report['candidates']], enable_watcher=False).status_code == 200
    assert c.get(base + '/issues').json()['total'] == 2
    assert c.get(base + '/watcher').json()['enabled'] is False
    assert (root / '.stash/runtime/watcher/state.json').is_file()


def test_explicit_checks_and_semantic_refinement(app_client, tmp_path):
    c = app_client
    root = tmp_path / 'checked'
    base = register(c, root)
    (root / 'package.json').write_text(json.dumps({'description': 'Test app', 'scripts': {'check': 'node -e "process.exit(2)"'}}))
    initial = inspect(c, base)
    assert any(x['name'] == 'npm:check' and x['status'] == 'not_run' for x in initial['checks'])
    assert c.post(base + '/assessments', json={'run_checks': ['arbitrary:shell']}).status_code == 422
    report = inspect(c, base, run_checks=['npm:check'])
    assert any(x.get('exit_code') == 2 for x in report['checks'])
    response = c.put(base + '/assessments/' + report['id'], json={'revision': report['revision'], 'proposed': {'brief': 'Inspected architecture and observed limitations'}, 'findings': [{'title': 'Improve checks', 'description': 'The check command exits unconditionally.', 'evidence': ['package.json'], 'confidence': 'observed'}], 'actor': {'name': 'Agent', 'kind': 'agent'}})
    assert response.status_code == 200, response.text
    refined = response.json()
    assert refined['revision'] != report['revision']
    assert accept(c, base, report).status_code == 409
    assert accept(c, base, refined, fields=['brief'], candidates=[x['id'] for x in refined['candidates']]).status_code == 200
    assert c.get(base).json()['brief'] == 'Inspected architecture and observed limitations'
    assert c.get(base + '/assessments').json()[0]['reviewed_by']['kind'] == 'agent'


def test_legacy_memory_preserves_identity_and_original_files(app_client, tmp_path):
    c = app_client
    root = tmp_path / 'legacy'
    base = register(c, root)
    old_project = c.get(base).json()
    issue = c.post(base + '/issues', json={'title': 'Human issue', 'description': 'Keep this text'}).json()
    stash = root / '.stash'
    stash.rename(root / '.trackle')
    legacy = root / '.trackle'
    metadata = legacy / 'project.json'
    metadata.write_text(metadata.read_text().replace('.stash/', '.trackle/'))
    before = {p.relative_to(legacy).as_posix(): p.read_bytes() for p in legacy.rglob('*') if p.is_file()}
    registered = c.post('/api/v1/projects', json={'path': str(root)})
    assert registered.status_code == 200, registered.text
    assert registered.json()['id'] == old_project['id']
    assert '.stash/docs' in registered.json()['doc_roots']
    assert c.get(base + '/issues/' + issue['id']).json()['description'] == 'Keep this text'
    assert {p.relative_to(legacy).as_posix(): p.read_bytes() for p in legacy.rglob('*') if p.is_file()} == before


def test_assessment_approval_recovers_after_interruption(app_client, tmp_path, monkeypatch):
    c = app_client
    root = tmp_path / 'crash'
    base = register(c, root)
    report = inspect(c, base, mode='new', goal='Reader app', requirements=['Add books'])
    from stash.store import FolderStore
    original = FolderStore.write
    crashed = False
    def fail_once(self, path, content):
        nonlocal crashed
        if path.startswith('sessions/') and not crashed:
            crashed = True
            raise OSError('simulated interrupted write')
        return original(self, path, content)
    monkeypatch.setattr(FolderStore, 'write', fail_once)
    response = accept(c, base, report, fields=['purpose'], candidates=[report['candidates'][0]['id']])
    assert response.status_code == 403
    assert (root / '.stash/.transaction.json').exists()
    monkeypatch.setattr(FolderStore, 'write', original)
    # The next read recovers all writes, including issue/checkpoint and watcher baseline.
    assert c.get(base).json()['purpose'] == 'Reader app'
    assert c.get(base + '/issues').json()['total'] == 1
    assert c.get(base + '/context').json()['resume']['checkpoint']
    assert not (root / '.stash/.transaction.json').exists()
    assert accept(c, base, report, fields=['purpose'], candidates=[report['candidates'][0]['id']]).status_code == 200
    assert c.get(base + '/issues').json()['total'] == 1


def test_cli_init_inspects_without_metadata_payload(app_client, tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from stash_cli.main import app
    c = app_client
    root = tmp_path / 'cli-project'
    root.mkdir()
    (root / 'main.py').write_text('def broken(:\n    pass\n')
    monkeypatch.setattr('stash_cli.main.httpx.request', lambda method, url, **kwargs: c.request(method, url, **kwargs))
    result = CliRunner().invoke(app, ['--json', 'init', str(root), '--goal', 'Reader app', '--requirement', 'Add books'])
    assert result.exit_code == 0, result.output
    value = json.loads(result.output)
    assert value['assessment']['goal'] == 'Reader app'
    assert any(x['type'] == 'bug' and x['evidence'] == 'main.py:1' for x in value['assessment']['candidates'])
    assert any(x['title'] == 'Add books' for x in value['assessment']['candidates'])
    assert value['project']['purpose'] == ''
    assert value['assessment']['status'] == 'draft'
    history = c.get('/api/v1/projects/' + value['project']['id'] + '/assessments').json()
    assert len(history) == 1
