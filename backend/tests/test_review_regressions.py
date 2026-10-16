"""Regression coverage for storage, observation, export, and date filtering."""
import subprocess

import pytest
from support import TestClient
from stash.api import create_app
from stash.sessions import observe_repository


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    with TestClient(create_app(tmp_path / 'shelf.db', test=True)) as client:
        registered = client.post('/api/v1/projects', json={'path': str(root)}).json()
        yield client, '/api/v1/projects/' + registered['id'], root


@pytest.mark.parametrize("brief_path", [".stash/docs/brief.md", ".stash/docs//brief.md", ".stash/docs/./brief.md"])
def test_docs_cannot_invalidate_project_brief(project, brief_path):
    client, base, root = project
    original = client.get(base + '/document', params={'path': '.stash/docs/brief.md'}).json()
    response = client.put(base + '/document', json={
        'path': brief_path, 'revision': original['revision'], 'content': 'x' * 50001,
    })
    assert response.status_code == 422
    assert (root / '.stash/docs/brief.md').read_text() == original['content']
    assert client.get(base).json()['availability'] == 'available'
    assert client.get(base + '/issues').status_code == 200
    assert client.put(base + '/document', json={
        'path': original['path'], 'revision': original['revision'], 'content': 'x' * 50000,
    }).status_code == 200
    assert client.get(base).json()['brief'] == 'x' * 50000


def test_utf8_byte_limit_is_checked_before_writing(project):
    client, base, root = project
    path = '.stash/docs/note.md'
    response = client.put(base + '/document', json={'path': path, 'revision': None, 'content': 'é' * 260000})
    assert response.status_code == 422
    assert not (root / path).exists()
    response = client.put(base + '/document', json={'path': path, 'revision': None, 'content': 'é' * 250000})
    assert response.status_code == 200
    revision = response.json()['revision']
    response = client.put(base + '/document', json={'path': path, 'revision': revision, 'content': 'é' * 260000})
    assert response.status_code == 422
    assert client.get(base + '/document', params={'path': path}).json()['revision'] == revision


def test_inspection_never_invokes_git_fsmonitor(tmp_path):
    root = tmp_path.resolve()
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    marker = root / 'executed'
    monitor = root / 'monitor.sh'
    monitor.write_text('#!/bin/sh\nprintf called > "' + str(marker) + '"\nprintf "token\\000"\n')
    monitor.chmod(0o700)
    subprocess.run(['git', '-C', str(root), 'config', 'core.fsmonitor', str(monitor)], check=True)
    assert observe_repository(root)['git'] is True
    assert not marker.exists()


def test_markdown_exports_assessment_details(project):
    client, base, _ = project
    report = client.post(base + '/assessments', json={'goal': 'Unique assessment goal'}).json()
    markdown = client.get(base + '/export', params={'format': 'markdown'}).text
    assert '## Assessments' in markdown
    assert 'Unique assessment goal' in markdown
    assert report['id'] in markdown


def test_activity_filters_compare_instants_not_timestamp_strings(project):
    client, base, _ = project
    event = client.get(base + '/activity').json()['items'][0]
    from datetime import datetime, timedelta, timezone
    instant = datetime.fromisoformat(event['created_at'])
    local = timezone(timedelta(hours=5, minutes=30))
    response = client.get(base + '/activity', params={
        'since': (instant - timedelta(seconds=1)).astimezone(local).isoformat(),
        'until': (instant + timedelta(seconds=1)).astimezone(local).isoformat(),
    })
    assert response.status_code == 200
    assert event['id'] in [item['id'] for item in response.json()['items']]
    assert client.get(base + '/activity', params={'since': 'invalid'}).status_code == 422


def test_document_reads_do_not_scan_unrelated_issues_or_history(project, monkeypatch):
    client, base, _ = project
    from stash.store import FolderStore
    def unexpected_scan(*args, **kwargs):
        raise AssertionError("A document read must not load unrelated history")
    monkeypatch.setattr(FolderStore, 'issues', unexpected_scan)
    monkeypatch.setattr(FolderStore, 'activity', unexpected_scan)
    assert client.get(base + '/document', params={'path': '.stash/docs/brief.md'}).status_code == 200
