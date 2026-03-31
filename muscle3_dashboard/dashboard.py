from importlib.metadata import version
from pathlib import Path

import pandas as pd
import panel as pn
from bokeh.application.application import SessionContext

from muscle3_dashboard.components.crash_analysis import CrashAnalysisViewer
from muscle3_dashboard.components.log_files import LogFilesViewer
from muscle3_dashboard.components.log_messages_table import LogMessagesTableViewer
from muscle3_dashboard.components.overview import OverviewViewer
from muscle3_dashboard.components.profiling_information import (
    ProfilingInformationViewer,
)
from muscle3_dashboard.components.status_table import StatusTableViewer
from muscle3_dashboard.components.ymmsl_graph import YmmslGraphViewer
from muscle3_dashboard.loganalyzer.manager import ManagerLogAnalyzer
from muscle3_dashboard.loganalyzer.stderr import StderrLogAnalyzer
from muscle3_dashboard.loganalyzer.stdout import StdoutLogAnalyzer

pn.extension("tabulator")


class Dashboard(pn.viewable.Viewer):
    """Main dashboard for muscle3_dashboard app"""

    def __init__(self, run_folder: Path | None = None) -> None:
        self.run_folder: Path | None = run_folder
        self.manager_log_analyzer: ManagerLogAnalyzer | None = None
        self.stdout_log_analyzers: dict[str, StdoutLogAnalyzer] | None = None
        self.stderr_log_analyzers: dict[str, StderrLogAnalyzer] | None = None

        self.template = pn.template.VanillaTemplate(
            collapsed_sidebar=True,
            title=f"MUSCLE3 Dashboard | {version('muscle3-dashboard')}",
            # header=pn.widgets.Button(
            #     name=f"Selected run folder: {run_folder} (click to change)",
            #     button_style="outline",
            # ),
        )

        self.overview_viewer = OverviewViewer()
        self.status_table_viewer = StatusTableViewer()
        self.log_messages_table_viewer = LogMessagesTableViewer()
        self.ymmsl_graph_viewer = YmmslGraphViewer()
        self.log_files_viewer = LogFilesViewer()
        self.crash_analysis_viewer = CrashAnalysisViewer()
        self.profiling_information_viewer = ProfilingInformationViewer()

        self.template.main.append(
            pn.Column(
                pn.Row(
                    self.overview_viewer,
                    self.status_table_viewer,
                    self.log_messages_table_viewer,
                    max_height=200,
                ),
                self.ymmsl_graph_viewer,
                self.log_files_viewer,
                self.crash_analysis_viewer,
                self.profiling_information_viewer,
            )
        )

        if run_folder is not None:
            self.update_run_folder(run_folder)

        pn.state.on_session_created(self.session_created)
        pn.state.on_session_destroyed(self.session_destroyed)
        self.update_logfiles()

    def session_created(self, context: SessionContext) -> None:
        """Set up background tasks when a new session is created"""
        # Update log files
        # TODO: use watchfiles to subscribe to notifications instead of polling?
        pn.state.add_periodic_callback(self.update_logfiles, period=1000)

    def session_destroyed(self, context: SessionContext) -> None:
        """Close session"""
        print("Session destroyed, shutting down")
        raise SystemExit(0)

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
            self.stdout_log_analyzers[component.name] = StdoutLogAnalyzer(
                component / "stdout.txt"
            )
            self.stderr_log_analyzers[component.name] = StderrLogAnalyzer(
                component / "stderr.txt"
            )

        # TODO: create simulation graph from configuration.ymmsl
        ...

    def update_logfiles(self) -> None:
        """Update viewers whenever change in logfiles is detected"""
        self.update_manager_logfiles()
        self.update_stdout_logfiles()
        self.update_stderr_logfiles()

    def update_manager_logfiles(self) -> None:
        """Update manager logfile information in viewers"""
        if self.manager_log_analyzer is None:
            return

        self.manager_log_analyzer.update()
        # Update manager log items
        # TODO: fix 'Total' counter
        self.log_messages_table_viewer.log_table.patch(
            pd.DataFrame(
                self.manager_log_analyzer.messages_per_level,
                index=["muscle_manager"],
            )
        )
        # Update component status
        df = self.manager_log_analyzer.to_dataframe()
        self.status_table_viewer.component_status_table.value = df

        # Update log text
        self.log_files_viewer.update(
            manager_log_lines=self.manager_log_analyzer.pop_new_lines()
        )

    def update_stdout_logfiles(self) -> None:
        """Update stdout logfiles information in viewers"""
        log_lines = {}
        for component, analyzer in self.stdout_log_analyzers.items():
            analyzer.update()
            log_lines[component] = self.stdout_log_analyzers[component].pop_new_lines()

        self.log_files_viewer.update(stdout_log_lines=log_lines)

    def update_stderr_logfiles(self) -> None:
        """Update stderr logfiles information in viewers"""
        log_lines = {}
        for component, analyzer in self.stderr_log_analyzers.items():
            analyzer.update()
            log_lines[component] = self.stderr_log_analyzers[component].pop_new_lines()

        self.log_files_viewer.update(stderr_log_lines=log_lines)

    def __panel__(self):
        return self.template


# Allow serving with `panel serve muscle3_dashboard/dashboard.py`
if "bokeh" in __name__:
    Dashboard().__panel__().servable()
