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
    assert set(cli.main.commands) == {"serve", "open", "ls"}


def test_ls_json(assets_path, monkeypatch):
    # Isolate from the real cluster.
    monkeypatch.setattr(discovery, "scan_slurm_jobs", lambda: [])
    monkeypatch.setattr(discovery, "scan_processes", lambda: [])
    result = CliRunner().invoke(cli.main, ["ls", "--json", str(assets_path)])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    names = {r["name"] for r in data}
    assert {"run-accumulator", "run-chease"} <= names


def test_ls_defaults_to_cwd(assets_path, monkeypatch):
    monkeypatch.setattr(discovery, "scan_slurm_jobs", lambda: [])
    monkeypatch.setattr(discovery, "scan_processes", lambda: [])
    monkeypatch.chdir(assets_path)
    result = CliRunner().invoke(cli.main, ["ls", "--json"])
    assert result.exit_code == 0, result.output
    names = {r["name"] for r in json.loads(result.output)}
    assert {"run-accumulator", "run-chease"} <= names


def test_serve_has_no_tcp_options():
    # TCP and the browser now live on `m3dash open`, not `serve`.
    result = CliRunner().invoke(cli.main, ["serve", "--tcp", "5006"])
    assert result.exit_code != 0
