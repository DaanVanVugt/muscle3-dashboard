"""Tests for run discovery (filesystem scan + status detection)."""

from pathlib import Path

import pytest

from muscle3_dashboard.m3dash import discovery
from muscle3_dashboard.m3dash.discovery import RunStatus


@pytest.fixture
def assets_path():
    return Path(__file__).parent / "assets"


def test_status_finished_and_failed(assets_path):
    ok, _ = discovery._log_status(assets_path / "run-accumulator")
    bad, _ = discovery._log_status(assets_path / "run-chease")
    assert ok is RunStatus.FINISHED
    assert bad is RunStatus.FAILED


def test_scan_tree_finds_run_dirs(assets_path):
    found = discovery._scan_tree(assets_path)
    names = {p.name for p in found}
    assert {"run-accumulator", "run-chease"} <= names


def test_scan_tree_prunes_and_is_bounded(tmp_path):
    # a run dir nested under a pruned directory is not descended into
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "muscle3_manager.log").write_text("x")
    real = tmp_path / "run1"
    real.mkdir()
    (real / "muscle3_manager.log").write_text("x")
    found = {p.name for p in discovery._scan_tree(tmp_path)}
    assert "run1" in found
    assert ".git" not in found


def test_discover_runs_merges_and_sorts(tmp_path, monkeypatch):
    # isolate from the real cluster: no SLURM / process sources
    monkeypatch.setattr(discovery, "scan_slurm_jobs", lambda: [])
    monkeypatch.setattr(discovery, "scan_processes", lambda: [])
    older = tmp_path / "old"
    newer = tmp_path / "new"
    for d in (older, newer):
        d.mkdir()
        (d / "muscle3_manager.log").write_text(
            "muscle_manager 2026 INFO x: The simulation finished without error."
        )
    import os

    os.utime(older / "muscle3_manager.log", (1000, 1000))
    os.utime(newer / "muscle3_manager.log", (2000, 2000))
    runs = discovery.discover_runs([tmp_path])
    names = [r.name for r in runs]
    assert names == ["new", "old"]  # newest first
    assert all(r.status is RunStatus.FINISHED for r in runs)
