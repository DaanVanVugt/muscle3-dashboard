"""Smoke tests for the m3dash CLI surface."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from muscle3_dashboard.m3dash import cli, discovery


@pytest.fixture
def assets_path():
    return Path(__file__).parent / "assets"


def test_all_commands_registered():
    # Guards against losing connect/sshline (e.g. a partial branch).
    assert set(cli.main.commands) == {
        "serve",
        "ensure",
        "ls",
        "urls",
        "sshline",
        "connect",
    }


def test_ls_json(assets_path, monkeypatch):
    # Isolate from the real cluster.
    monkeypatch.setattr(discovery, "scan_slurm_jobs", lambda: [])
    monkeypatch.setattr(discovery, "scan_processes", lambda: [])
    result = CliRunner().invoke(cli.main, ["ls", "--json", "--root", str(assets_path)])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    names = {r["name"] for r in data}
    assert {"run-accumulator", "run-chease"} <= names


def test_urls_on_synthetic_run(tmp_path):
    run = tmp_path / "run"
    (run / "instances" / "viz").mkdir(parents=True)
    (run / "instances" / "viz" / "stdout.txt").write_text(
        "Launching server at http://10.0.0.5:9000/"
    )
    (run / "instances" / "viz" / "stderr.txt").write_text("")
    (run / "muscle3_manager.log").write_text("x\n")
    result = CliRunner().invoke(cli.main, ["urls", str(run)])
    assert result.exit_code == 0, result.output
    assert "http://10.0.0.5:9000/" in result.output


def test_sshline_mentions_both_paths():
    result = CliRunner().invoke(cli.main, ["sshline", "--host", "login01.example"])
    assert result.exit_code == 0, result.output
    assert "LocalForward" in result.output  # forwarding-allowed recipe
    assert "m3dash connect login01.example" in result.output  # bridge recipe


def test_serve_open_browser_requires_tcp():
    result = CliRunner().invoke(cli.main, ["serve", "--no-tcp", "--open-browser"])
    assert result.exit_code != 0
    assert "open-browser" in result.output.lower()


def test_logviewer_absent_is_graceful(tmp_path, monkeypatch):
    # With no logdy binary, launch() returns None so the run page falls
    # back to the built-in terminals.
    from muscle3_dashboard.m3dash import logviewer

    monkeypatch.delenv("M3DASH_LOGDY", raising=False)
    monkeypatch.setattr(logviewer.shutil, "which", lambda _name: None)
    run = tmp_path / "run"
    (run / "instances").mkdir(parents=True)
    (run / "muscle3_manager.log").write_text("x\n")
    assert logviewer.find_logdy() is None
    assert logviewer.launch(run) is None
