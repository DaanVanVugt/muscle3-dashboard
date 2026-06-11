import contextlib
import html
from datetime import datetime
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import panel as pn

from muscle3_dashboard.components.crash_analysis import CrashAnalysisViewer
from muscle3_dashboard.components.log_files import LogFilesViewer
from muscle3_dashboard.components.log_messages_table import LogMessagesTableViewer
from muscle3_dashboard.components.profiling_information import (
    ProfilingInformationViewer,
)
from muscle3_dashboard.components.status_table import StatusTableViewer
from muscle3_dashboard.components.ymmsl_graph import YmmslGraphViewer
from muscle3_dashboard.data_manager import DataManager
from muscle3_dashboard.pathlink import path_html

# Material design gives cleaner cards/typography than the default.
pn.extension("tabulator", design="material", sizing_mode="stretch_width")

#: Header status-dot colours, light Material shades for the dark header.
_STATE_COLORS = {
    "not started": "#ffb74d",
    "running": "#81c784",
    "finished": "#bdbdbd",
    "failed": "#e57373",
}


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


class Dashboard(pn.viewable.Viewer):
    """Main dashboard for muscle3_dashboard app.

    ``web_urls`` optionally maps a component name to an HTML link to its
    served UI; when given it is shown as a column in the status table.
    """

    def __init__(
        self,
        run_folder: Path,
        web_urls: dict[str, str] | None = None,
    ) -> None:
        self.run_folder = run_folder

        self.template = pn.template.MaterialTemplate(
            collapsed_sidebar=True,
            title=f"MUSCLE3 Dashboard | {_dashboard_version()}",
        )

        self.data_manager = DataManager(run_folder)

        self.status_table_viewer = StatusTableViewer(
            self.data_manager,
            web_urls=web_urls,
            on_select=self._show_logs_for,
        )
        self.log_messages_table_viewer = LogMessagesTableViewer(
            self.data_manager,
            on_select=self._show_logs_for,
        )
        self.ymmsl_graph_viewer = YmmslGraphViewer(self.data_manager)
        self.log_files_viewer = LogFilesViewer(self.data_manager)
        self.crash_analysis_viewer = CrashAnalysisViewer(self.data_manager)
        self.profiling_information_viewer = ProfilingInformationViewer(
            self.data_manager
        )

        # Header strip: status dot + state, the run name, the copyable run
        # directory, and (right-aligned) the time of the last log update.
        self.header_pane = pn.pane.HTML(
            self._header_html(), sizing_mode="stretch_width"
        )
        self.template.header.append(self.header_pane)
        self.data_manager.param.watch(self._update_header, "data_updated")

        # Single page, top to bottom: the component status table beside the
        # simulation graph (to be linked on hover, nodes coloured by status
        # once the ymmsl2svg graph lands), then all log messages, then log
        # files, then crash analysis.
        self.template.main.append(
            pn.Column(
                pn.Row(
                    self.status_table_viewer,
                    self.ymmsl_graph_viewer,
                    sizing_mode="stretch_width",
                ),
                self.log_messages_table_viewer,
                self.log_files_viewer,
                self.crash_analysis_viewer,
                sizing_mode="stretch_width",
            )
        )

        self.session_created()

    def _header_html(self) -> str:
        analyzer = self.data_manager.manager_log_analyzer
        state = analyzer.simulation_state
        tip = html.escape(analyzer.status_message or state)
        return (
            '<div style="display:flex;align-items:baseline;gap:0.6em;width:100%">'
            f'<span title="{tip}" style="white-space:nowrap">'
            f'<span style="color:{_STATE_COLORS[state]};font-size:1.1em">'
            f"&#x25cf;</span> {state}</span>"
            f"<b>{html.escape(self.run_folder.name)}</b>"
            f"<span>{path_html(self.run_folder)}</span>"
            f'<span style="margin-left:auto;opacity:0.7;font-size:0.85em;'
            f'white-space:nowrap">{self._updated_html()}</span>'
            "</div>"
        )

    def _updated_html(self) -> str:
        ts = self.data_manager.logs_last_updated
        if ts is None:
            return ""
        age = (datetime.now() - ts).total_seconds()
        if age < 60:
            return f"updated {max(0, int(age))} s ago"
        if age < 3600:
            return f"updated {int(age // 60)} min ago"
        return f"updated at {ts.strftime('%H:%M:%S')}"

    def _update_header(self, event) -> None:
        self.header_pane.object = self._header_html()

    def _show_logs_for(self, source: str) -> None:
        """Show the source's log and mirror the selection in both tables.

        Setting a table's selection programmatically does not fire its
        click handler, so this cannot loop.
        """
        self.log_files_viewer.show_source(source)
        self.status_table_viewer.select_source(source)
        self.log_messages_table_viewer.select_source(source)

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
            # Outside a server session (scripts, tests) there may be no
            # running event loop to attach the callback to.
            with contextlib.suppress(RuntimeError):
                _start_polling()

    def __panel__(self):
        return self.template
