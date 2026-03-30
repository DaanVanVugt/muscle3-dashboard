import datetime

import pytest

from muscle3_dashboard import get_project_root
from muscle3_dashboard.loganalyzer.manager import ComponentStatus, ManagerLogAnalyzer


@pytest.fixture
def assets_path():
    return get_project_root() / "tests" / "assets"


def test_successful_run(assets_path):
    log_file = assets_path / "run-accumulator" / "muscle3_manager.log"
    mla = ManagerLogAnalyzer(log_file, [])
    expected_components = [
        "accumulator",
        "accumulator_optional_port",
        "sink",
        "sink_optional_port",
        "source",
    ]
    assert sorted(mla.components.keys()) == sorted(expected_components)
    assert mla.components["accumulator"].status == ComponentStatus.FINISHED
    assert mla.components["accumulator"].exit_code == "0"
    assert mla.components["accumulator"].exit_code_message == "0"
    expected_update_time = datetime.datetime(2026, 3, 27, 11, 40, 11, 36000)
    assert mla.last_update_time == expected_update_time
    assert mla.lines_parsed == 30
    assert mla.lines_read == 30
    assert mla.messages_per_level == {
        "DEBUG": 0,
        "INFO": 30,
        "WARNING": 0,
        "ERROR": 0,
        "CRITICAL": 0,
        "unknown": 0,
    }
    assert mla.muscle_manager_version == "unknown"
    assert mla.status == "The simulation finished without error."


def test_unsuccessful_run(assets_path):
    log_file = assets_path / "run-chease" / "muscle3_manager.log"
    mla = ManagerLogAnalyzer(log_file, [])
    expected_components = ["chease", "sink", "source"]
    assert sorted(mla.components.keys()) == sorted(expected_components)
    assert mla.components["chease"].status == ComponentStatus.FINISHED
    assert mla.components["chease"].exit_code == "127"
    assert mla.components["chease"].exit_code_message == "127"
    assert mla.components["source"].status == ComponentStatus.FINISHED
    assert mla.components["source"].exit_code == "-9"
    assert mla.components["source"].exit_code_message == "-9: Killed"
    assert mla.components["sink"].status == ComponentStatus.FINISHED
    assert mla.components["sink"].exit_code == "crashed"
    assert mla.components["sink"].exit_code_message == "crashed"
    expected_update_time = datetime.datetime(2026, 3, 27, 11, 40, 15, 936000)
    assert mla.last_update_time == expected_update_time
    assert mla.lines_parsed == 22
    assert mla.lines_read == 31
    assert mla.messages_per_level == {
        "DEBUG": 0,
        "INFO": 10,
        "WARNING": 1,
        "ERROR": 11,
        "CRITICAL": 0,
        "unknown": 0,
    }
    assert mla.muscle_manager_version == "unknown"
    assert mla.status == ""
