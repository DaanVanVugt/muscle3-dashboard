from importlib.metadata import version
from pathlib import Path

import pandas as pd
import panel as pn
from bokeh.application.application import SessionContext

from muscle3_dashboard.loganalyzer.manager import ManagerLogAnalyzer
from muscle3_dashboard.ymmsl_graph import YmmslGraphViewer

pn.extension("tabulator")


class Dashboard(pn.viewable.Viewer):
    def __init__(self, run_folder: Path | None = None) -> None:
        self.run_folder: Path | None = run_folder
        self.manager_log_analyzer: ManagerLogAnalyzer | None = None

        self.template = pn.template.VanillaTemplate(
            collapsed_sidebar=True,
            title=f"MUSCLE3 Dashboard | {version('muscle3-dashboard')}",
            # header=pn.widgets.Button(
            #     name=f"Selected run folder: {run_folder} (click to change)",
            #     button_style="outline",
            # ),
        )
        overview = pn.Card(
            pn.pane.Markdown(
                """
            *PLACEHOLDER!*

            - **Simulation status**: Running (?)
            - **Last log update**: 2026-03-25 10:41:32 (1 second ago)
            - **Components**
              - Found 20 components in the simulation
              - Found log files for 20 components in the run folder
            """,
            ),
            title="Overview",
            sizing_mode="stretch_both",
            # scroll=True,
            collapsible=False,
            # height=200,
            margin=5,
        )
        # TODO: these columns should be defined in a central place
        logmessages = pd.DataFrame(
            {
                "component": ["muscle_manager"],
                "DEBUG": [0],
                "INFO": [0],
                "WARNING": [0],
                "ERROR": [0],
                "CRITICAL": [0],
                "unknown": [0],
            }
        ).set_index("component")

        self.log_table = pn.widgets.Tabulator(
            pd.concat([logmessages, logmessages.sum().to_frame("Total").T]),
            frozen_rows=[-1],
            disabled=True,
            selectable=1,
            # header_filters=True,
            sizing_mode="stretch_both",
            sorters=[
                {"field": name, "dir": "desc"}
                for name in ("critical", "error", "warning", "info", "debug")
            ],
        )

        all_log_messages = pn.Card(
            self.log_table,
            title="All log messages",
            # height=200,
            sizing_mode="stretch_both",
            collapsible=False,
            margin=5,
        )

        self.component_status_table = pn.widgets.Tabulator(
            pd.DataFrame([], columns=["component", "status", "exitcode"]).set_index(
                "component"
            ),
            disabled=True,
            selectable=1,
            sizing_mode="stretch_both",
        )

        tabs = pn.Tabs(
            pn.pane.Markdown(
                """
                TODO: Show aggregated log files
                
                **N.B.** This will only show log messages appended since the dashboard
                started!
                """,
                name="Aggregated logs",
            ),
            pn.pane.Markdown(
                "TODO: Muscle manager log file", name="Muscle manager logs"
            ),
            pn.pane.Markdown(
                "TODO: `stdout.txt` and `stderr.txt` for each component",
                name="Component logs",
            ),
            sizing_mode="stretch_width",
            tabs_location="left",
            max_height=800,
            stylesheets=[".bk-tab {text-align: right;}"],
        )

        self.template.main.append(
            pn.Column(
                pn.Row(
                    overview,
                    pn.Card(
                        self.component_status_table,
                        title="Component status",
                        margin=5,
                        width_policy="min",
                        collapsible=False,
                        # height=200,
                        sizing_mode="stretch_both",
                    ),
                    all_log_messages,
                    max_height=200,
                ),
                pn.Card(
                    YmmslGraphViewer(),
                    title="Simulation graph (Placeholder)",
                    sizing_mode="stretch_width",
                    # scroll=True,
                    margin=5,
                ),
                pn.Card(tabs, margin=5, title="Log file viewer"),
                pn.Card(
                    "<em>Placeholder</em> No crash detected",
                    title="Crash analysis",
                    margin=5,
                    sizing_mode="stretch_width",
                ),
                pn.Card(
                    "<em>Placeholder</em> Profiling information",
                    title="Profiling information",
                    margin=5,
                    sizing_mode="stretch_width",
                ),
            )
        )

        if run_folder is not None:
            self.update_run_folder(run_folder)

        pn.state.on_session_created(self.session_created)
        pn.state.on_session_destroyed(self.session_destroyed)

    def session_created(self, context: SessionContext) -> None:
        """Set up background tasks when a new session is created"""
        # Update log files
        # TODO: use watchfiles to subscribe to notifications instead of polling?
        pn.state.add_periodic_callback(self.update_logfiles, period=1000)

    def session_destroyed(self, context: SessionContext) -> None:
        print("Session destroyed, shutting down")
        raise SystemExit(0)

    def update_run_folder(self, run_folder: Path) -> None:
        self.run_folder = run_folder
        # TODO: setup notifications / poll until file exists?
        logfile = run_folder / "muscle3_manager.log"
        components = []  # TODO: get components from configuration.ymmsl
        self.manager_log_analyzer = ManagerLogAnalyzer(logfile, components)

        # TODO: create simulation graph from configuration.ymmsl
        ...

    def update_logfiles(self) -> None:
        if self.manager_log_analyzer is not None:
            self.manager_log_analyzer.update()
            # Update manager log items
            self.log_table.patch(
                pd.DataFrame(
                    self.manager_log_analyzer.messages_per_level,
                    index=["muscle_manager"],
                )
            )
            # Update component status
            self.component_status_table.value = pd.DataFrame(
                {
                    # "status": self.manager_log_analyzer.component_status,
                    # "exitcode": self.manager_log_analyzer.component_exitcode,
                    "status": self.manager_log_analyzer.var_dict('status'),
                    "exitcode": self.manager_log_analyzer.var_dict('exit_code_message'),
                }
            )

    def __panel__(self):
        return self.template


# Allow serving with `panel serve muscle3_dashboard/dashboard.py`
if "bokeh" in __name__:
    Dashboard().__panel__().servable()
