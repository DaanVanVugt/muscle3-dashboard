from collections import defaultdict

import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN, MAX_LINES, TERMINAL_HEIGHT
from muscle3_dashboard.data_manager import DataManager


class LogFilesViewer(pn.viewable.Viewer):
    """Panel component showing the log files for the muscle manager and the
    separate components"""

    def __init__(self, data_manager: DataManager) -> None:
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
        self.data_manager = data_manager
        self.data_manager.param.watch(self.update, "data_updated")

    def components_tab_pane(self):
        """Tab for separate component logs"""
        self.component_terminals = {}
        self.select = pn.widgets.Select(name="Choose log", groups={})
        self.terminal_container = pn.pane.Placeholder(
            "", sizing_mode="stretch_width", styles={"overflow": "hidden"}
        )
        self.select.param.watch(self.update_component_logs, "value")
        return pn.Column(
            self.select, self.terminal_container, styles={"overflow": "hidden"}
        )

    def update_component_logs(self, event):
        """Update component logs on trigger"""
        if event.new not in self.component_terminals:
            self.component_terminals[event.new] = self.log_pane()
        self.terminal_container.object = self.component_terminals[event.new]

    def log_pane(self):
        """Get basic terminal"""
        return pn.widgets.Terminal(
            "",
            sizing_mode="stretch_width",
            height=TERMINAL_HEIGHT,
            options={"wrap": True},
            styles={"overflow": "hidden"},
            margin=CARD_MARGIN,
        )

    def update(self, event):
        """Method to update log file viewer from listener"""
        for line in self.data_manager.manager_log_lines[-MAX_LINES:]:
            self.muscle_manager_tab.write(line)

        for component, lines in self.data_manager.stdout_log_lines.items():
            key = f"{component} - stdout"
            if key not in self.component_terminals:
                self.component_terminals[key] = self.log_pane()
            for line in lines[-MAX_LINES:]:
                self.component_terminals[key].write(line)

        for component, lines in self.data_manager.stderr_log_lines.items():
            key = f"{component} - stderr"
            if key not in self.component_terminals:
                self.component_terminals[key] = self.log_pane()
            for line in lines[-MAX_LINES:]:
                self.component_terminals[key].write(line)

        groups = defaultdict(list)
        for key in self.component_terminals:
            component, _ = key.split("-")

            groups[component].append(key)
        self.select.groups = groups

    def __panel__(self):
        return self.card
