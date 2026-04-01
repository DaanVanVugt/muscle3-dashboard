from collections import defaultdict
from typing import List, Dict

import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN


class LogFilesViewer(pn.viewable.Viewer):
    """Panel component showing the log files for the muscle manager and the
    separate components"""

    def __init__(self) -> None:
        super().__init__()
        # TODO: add aggregated logs tab
        self.muscle_manager_tab = self.log_pane()
        self.component_tabs = self.components_tab_pane()
        self.tabs = pn.Tabs(
            ("Muscle manager logs", self.muscle_manager_tab),
            ("Component logs", self.component_tabs),
            sizing_mode="stretch_width",
            tabs_location="left",
            max_height=800,
            stylesheets=[".bk-tab {text-align: right;}"],
        )
        self.card = pn.Card(self.tabs, margin=CARD_MARGIN, title="Log files")

    def components_tab_pane(self):
        """Tab for separate component logs"""
        self.component_terminals = {}
        self.select = pn.widgets.Select(name="Choose log", groups={})
        self.terminal_container = pn.pane.Placeholder('')
        self.select.param.watch(self.update_component_logs, "value")
        return pn.Column(self.select, self.terminal_container)

    def update_component_logs(self, event):
        """Update component logs on trigger"""
        if event.new not in self.component_terminals:
            self.component_terminals[event.new] = self.log_pane()
        self.terminal_container.object = self.component_terminals[event.new]

    def log_pane(self):
        """Get basic terminal"""
        return pn.widgets.Terminal(
            "",
            sizing_mode="stretch_both",
            options={"wrap": False},
        )

    def update(
        self,
        manager_log_lines: List[str] = None,
        stdout_log_lines: Dict[str, List[str]] = None,
        stderr_log_lines: Dict[str, List[str]] = None,
    ):
        """Method to update log file viewer state from outside"""
        if manager_log_lines is not None:
            for line in manager_log_lines:
                self.muscle_manager_tab.write(line)

        if stdout_log_lines is not None:
            for component, lines in stdout_log_lines.items():
                key = f"{component} - stdout"
                if key not in self.component_terminals:
                    self.component_terminals[key] = self.log_pane()
                for line in lines:
                    self.component_terminals[key].write(line)

        if stderr_log_lines is not None:
            for component, lines in stderr_log_lines.items():
                key = f"{component} - stderr"
                if key not in self.component_terminals:
                    self.component_terminals[key] = self.log_pane()
                for line in lines:
                    self.component_terminals[key].write(line)

        groups = defaultdict(list)
        for key in self.component_terminals:
            component, _ = key.split("-")

            groups[component].append(key)
        self.select.groups = groups

    def __panel__(self):
        return self.card
