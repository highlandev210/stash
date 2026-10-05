import json
from pathlib import Path

from support import TestClient
from typer.testing import CliRunner

from stash.api import create_app
from stash_cli.main import app


def test_cli_uses_same_api_and_records(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    runner = CliRunner()
    with TestClient(create_app(tmp_path / "stash.db", test=True)) as client:
        def request(method, url, **kwargs):
            return client.request(method, url, **kwargs)
        monkeypatch.setattr("stash_cli.main.httpx.request", request)
        monkeypatch.chdir(root)
        registered = runner.invoke(app, ["--json", "register", str(root)])
        assert registered.exit_code == 0, registered.output
        project = json.loads(registered.stdout)
        created = runner.invoke(app, ["--json", "issues", "create", "Resume work", "--type", "task"])
        assert created.exit_code == 0, created.output
        issue = json.loads(created.stdout)
        assert client.get(f"/api/v1/projects/{project['id']}/issues/{issue['id']}").json()["title"] == "Resume work"
        updated = runner.invoke(app, ["--json", "issues", "update", issue["id"], "--status", "done", "--verification", "CLI workflow checked"])
        assert updated.exit_code == 0, updated.output
        assert json.loads(updated.stdout)["status"] == "done"
        decision = runner.invoke(app, ["--json", "decisions", "add", "Keep records local", "--reasoning", "Single-user tool"])
        assert decision.exit_code == 0, decision.output
        payload = root / "handoff.json"
        payload.write_text(json.dumps({"summary": "Connected CLI", "next_actions": "Check browser", "verification": "CLI test passed"}))
        saved = runner.invoke(app, ["--json", "handoffs", "add", str(payload), "--key", "checkpoint"])
        assert saved.exit_code == 0, saved.output
        context = runner.invoke(app, ["--json", "context"])
        assert context.exit_code == 0, context.output
        data = json.loads(context.stdout)
        assert "Check browser" in data["markdown"] and data["handoffs"][0]["actor"]["kind"] == "agent"
        unregistered = tmp_path / "unregistered"
        unregistered.mkdir()
        monkeypatch.chdir(unregistered)
        assert runner.invoke(app, ["--json", "context"]).exit_code == 3
        assert runner.invoke(app, ["--json", "--project", project["id"], "context"]).exit_code == 0
