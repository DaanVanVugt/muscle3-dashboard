import html
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
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


@lru_cache(maxsize=1)
def _dashboard_version() -> str:
    """Version for the title.

    When installed, read the distribution metadata. When run from a
    source checkout (no installed distribution), derive a version from
    git via setuptools_scm, which this project already uses. Fall back
    to 'dev' if neither is available (e.g. an unpacked tarball).
    """
    try:
        return version("muscle3-dashboard")
    except PackageNotFoundError:
        pass
    try:
        from setuptools_scm import get_version

        return get_version(root="..", relative_to=__file__)
    except Exception:
        return "dev"


def _path_html(run_folder: Path) -> str:
    """A run-dir string that copies its path on click and offers a
    file:// link to open it in the desktop file manager."""
    path = html.escape(str(run_folder.resolve()))
    return (
        f'<span title="click to copy" '
        f'onclick="navigator.clipboard.writeText(this.dataset.path)" '
        f'data-path="{path}" '
        f'style="cursor:pointer;color:#555;font-size:1em">{path}</span> '
        f'<a href="file://{path}" title="open in file manager" '
        f'target="_blank" style="text-decoration:none">&#x2197;</a>'
    )


class Dashboard(pn.viewable.Viewer):
    """Main dashboard for muscle3_dashboard app.

    ``web_urls`` optionally maps a component name to an HTML link to its
    served UI; when given it is shown as a column in the status table and
    summarised in the header.
    """

    def __init__(
        self,
        run_folder: Path | None = None,
        web_urls: dict[str, str] | None = None,
    ) -> None:
        self.run_folder: Path | None = run_folder

        self.template = pn.template.VanillaTemplate(
            collapsed_sidebar=True,
            title=f"MUSCLE3 Dashboard | {_dashboard_version()}",
        )

        self.data_manager = DataManager(run_folder)

        self.overview_viewer = OverviewViewer(self.data_manager)
        self.status_table_viewer = StatusTableViewer(
            self.data_manager, web_urls=web_urls
        )
        self.log_messages_table_viewer = LogMessagesTableViewer(self.data_manager)
        self.ymmsl_graph_viewer = YmmslGraphViewer(self.data_manager)
        self.log_files_viewer = LogFilesViewer(self.data_manager)
        self.crash_analysis_viewer = CrashAnalysisViewer(self.data_manager)
        self.profiling_information_viewer = ProfilingInformationViewer(
            self.data_manager
        )

        # Header strip: run name + copyable / openable run directory.
        self.template.header.append(
            pn.pane.HTML(
                f"<b>{html.escape(run_folder.name)}</b> &nbsp; "
                f"{_path_html(run_folder)}",
                sizing_mode="stretch_width",
            )
        )

        # Single page, top to bottom: overview, then the component status
        # table beside the simulation graph (linked on hover, nodes
        # coloured by status), then logs, then crash analysis.
        self.template.main.append(
            pn.Column(
                pn.Row(
                    self.overview_viewer,
                    self.log_messages_table_viewer,
                    height=200,
                ),
                pn.Row(
                    self.status_table_viewer,
                    self.ymmsl_graph_viewer,
                    sizing_mode="stretch_width",
                ),
                self.log_files_viewer,
                self.crash_analysis_viewer,
                sizing_mode="stretch_width",
            )
        )

        self.session_created()

    def session_created(self) -> None:
        """Set up background tasks when a new session is created"""
        # Update log files
        # TODO: use watchfiles to subscribe to notifications instead of polling?
        # Register the periodic callback once the session has loaded rather
        # than during construction: adding it here (mid-construction) makes
        # Bokeh replay a SessionCallbackAdded event on the first document
        # unhold, which raises "a callback ... has already been added with
        # this ID". Deferring to onload binds it to the live session cleanly.
        def _start_polling() -> None:
            pn.state.add_periodic_callback(self.data_manager.update, period=1000)

        if pn.state.curdoc:
            pn.state.onload(_start_polling)
        else:
            _start_polling()

    def __panel__(self):
        return self.template


# Allow serving with `panel serve muscle3_dashboard/dashboard.py`
if "bokeh" in __name__:
    Dashboard().__panel__().servable()
