from pathlib import Path

import pytest

from muscle3_dashboard.loganalyzer.base import BaseLogAnalyzer


@pytest.fixture
def assets_path():
    return Path(__file__).parent / "assets"


def test_run_stdout(assets_path):
    log_file = assets_path / "run-accumulator" / "instances" / "source" / "stdout.txt"
    sla = BaseLogAnalyzer(log_file)
    assert sla._name == "source"
    assert sla._path == log_file
    assert len(sla.new_lines) == 8
    new_lines = sla.pop_new_lines()
    assert len(new_lines) == 8
    assert len(sla.new_lines) == 0


def test_run_stderr(assets_path):
    log_file = assets_path / "run-accumulator" / "instances" / "source" / "stderr.txt"
    sla = BaseLogAnalyzer(log_file)
    assert sla._name == "source"
    assert sla._path == log_file
    assert len(sla.new_lines) == 5
    new_lines = sla.pop_new_lines()
    assert len(new_lines) == 5
    assert len(sla.new_lines) == 0
