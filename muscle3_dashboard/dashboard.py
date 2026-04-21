from importlib.metadata import version
from pathlib import Path

import panel as pn

from muscle3_dashboard.components.crash_analysis import CrashAnalysisViewer
from muscle3_dashboard.components.log_files import LogFilesViewer
from muscle3_dashboard.components.log_messages_table import LogMessagesTableViewer
from muscle3_dashboard.components.overview import OverviewViewer
from muscle3_dashboard.components.profiling_information import (
    ProfilingInformationViewer,
)
from muscle3_dashboard.components.status_table import StatusTableViewer
from muscle3_dashboard.components.ymmsl_graph import YmmslGraphViewer
from muscle3_dashboard.data_manager import DataManager

pn.extension("tabulator")


class Dashboard(pn.viewable.Viewer):
    """Main dashboard for muscle3_dashboard app"""

    def __init__(self, run_folder: Path | None = None) -> None:
        self.run_folder: Path | None = run_folder

        self.template = pn.template.VanillaTemplate(
            collapsed_sidebar=True,
            title=f"MUSCLE3 Dashboard | {version('muscle3-dashboard')} | {run_folder.name}",
        )

        self.data_manager = DataManager(run_folder)

        self.overview_viewer = OverviewViewer(self.data_manager)
        self.status_table_viewer = StatusTableViewer(self.data_manager)
        self.log_messages_table_viewer = LogMessagesTableViewer(self.data_manager)
        self.ymmsl_graph_viewer = YmmslGraphViewer(self.data_manager)
        self.log_files_viewer = LogFilesViewer(self.data_manager)
        self.crash_analysis_viewer = CrashAnalysisViewer(self.data_manager)
        self.profiling_information_viewer = ProfilingInformationViewer(
            self.data_manager
        )

        self.template.main.append(
            pn.Column(
                pn.Row(
                    self.overview_viewer,
                    self.status_table_viewer,
                    self.log_messages_table_viewer,
                    height=200,
                ),
                # self.ymmsl_graph_viewer,
                self.log_files_viewer,
                self.crash_analysis_viewer,
                # self.profiling_information_viewer,
            )
        )

        self.session_created()

    def session_created(self) -> None:
        """Set up background tasks when a new session is created"""
        # Update log files
        # TODO: use watchfiles to subscribe to notifications instead of polling?
        pn.state.add_periodic_callback(self.data_manager.update, period=1000)

    def __panel__(self):
        return self.template


# Allow serving with `panel serve muscle3_dashboard/dashboard.py`
if "bokeh" in __name__:
    Dashboard().__panel__().servable()
