from pathlib import Path

import param

from muscle3_dashboard.loganalyzer.base import BaseLogAnalyzer
from muscle3_dashboard.loganalyzer.manager import ManagerLogAnalyzer


class DataManager(param.Parameterized):
    data_updated = param.Event()

    def __init__(self, run_folder: Path):
        super().__init__()
        self.run_folder = run_folder
        self.logs_last_updated = None
        self.manager_log_analyzer: ManagerLogAnalyzer | None = None
        self.stdout_log_analyzers: dict[str, BaseLogAnalyzer] = {}
        self.stderr_log_analyzers: dict[str, BaseLogAnalyzer] = {}
        self.update_run_folder(run_folder)

    def update_run_folder(self, run_folder: Path) -> None:
        """Set up log analyzers and simulation graph from run_folder"""
        self.run_folder = run_folder
        # TODO: setup notifications / poll until file exists?
        logfile = run_folder / "muscle3_manager.log"
        components = []  # TODO: get components from configuration.ymmsl
        self.manager_log_analyzer = ManagerLogAnalyzer(logfile, components)
        self.stdout_log_analyzers = {}
        self.stderr_log_analyzers = {}
        for component in (run_folder / "instances").iterdir():
            self.stdout_log_analyzers[component.name] = BaseLogAnalyzer(
                component / "stdout.txt"
            )
            self.stderr_log_analyzers[component.name] = BaseLogAnalyzer(
                component / "stderr.txt"
            )
        self.manager_log_lines: list[str] = []
        self.stdout_log_lines: dict[str, list[str]] = {}
        self.stderr_log_lines: dict[str, list[str]] = {}

    def update(self) -> None:
        """Update viewers whenever change in logfiles is detected"""
        self.update_manager_logfiles()
        self.update_stdout_logfiles()
        self.update_stderr_logfiles()
        self.data_updated = True

    def update_logs_last_updated(self, log_analyzer: BaseLogAnalyzer) -> None:
        """Update logs_last_updated based on last time given file was
        modified"""
        file_time = log_analyzer.file_last_updated()
        self.logs_last_updated = max(self.logs_last_updated or file_time, file_time)

    def update_manager_logfiles(self) -> None:
        """Update manager logfile information in viewers"""
        self.manager_log_analyzer.update()
        self.manager_log_lines = self.manager_log_analyzer.pop_new_lines()
        self.update_logs_last_updated(self.manager_log_analyzer)

    def update_stdout_logfiles(self) -> None:
        """Update stdout logfiles information in viewers"""
        log_lines = {}
        for component, analyzer in self.stdout_log_analyzers.items():
            analyzer.update()
            log_lines[component] = self.stdout_log_analyzers[component].pop_new_lines()
            self.update_logs_last_updated(self.stdout_log_analyzers[component])

        self.stdout_log_lines = log_lines

    def update_stderr_logfiles(self) -> None:
        """Update stderr logfiles information in viewers"""
        log_lines = {}
        for component, analyzer in self.stderr_log_analyzers.items():
            analyzer.update()
            log_lines[component] = self.stderr_log_analyzers[component].pop_new_lines()
            self.update_logs_last_updated(self.stderr_log_analyzers[component])

        self.stderr_log_lines = log_lines
