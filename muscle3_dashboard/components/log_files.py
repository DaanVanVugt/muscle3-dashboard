import os
from collections import defaultdict

import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN, MAX_LINES, TERMINAL_HEIGHT
from muscle3_dashboard.data_manager import DataManager


class LogFilesViewer(pn.viewable.Viewer):
    """Panel component showing the log files for the muscle manager and the
    separate components"""

    def __init__(self, data_manager: DataManager) -> None:
        super().__init__()
        self.data_manager = data_manager
        self.data_manager.param.watch(self.update, "data_updated")
        self.log_path = self.data_manager.run_folder
        # TODO: add aggregated logs tab
        self.manager_terminal = self.log_pane()
        self.truncate_message_container = pn.pane.Markdown(self.truncate_message)
        self.muscle_manager_tab = pn.Column(
            self.manager_terminal,
            self.truncate_message_container,
            sizing_mode="stretch_width",
        )
        self.component_tabs = self.components_tab_pane()
        self.tabs = pn.Tabs(
            ("Muscle manager logs", self.muscle_manager_tab),
            ("Component logs", self.component_tabs),
            sizing_mode="stretch_width",
            tabs_location="above",
            max_height=800,
            stylesheets=[".bk-tab {text-align: right;}"],
        )
        self.tabs.param.watch(self.update_truncate_message, "active")
        self.card = pn.Card(self.tabs, margin=CARD_MARGIN, title="Log files")

    def components_tab_pane(self):
        """Tab for separate component logs"""
        self.component_terminals = {}
        self.select = pn.widgets.Select(name="Choose log", groups={})
        self.terminal_container = pn.pane.Placeholder(
            "",
            sizing_mode="stretch_width",
        )
        self.select.param.watch(self.update_truncate_message, "value")
        self.select.param.watch(self.update_component_logs, "value")
        return pn.Column(
            self.select,
            self.terminal_container,
            self.truncate_message_container,
            sizing_mode="stretch_width",
        )

    def update_truncate_message(self, event):
        select_component, select_type = self.current_select.split(" - ")
        if self.current_tab == "Muscle manager logs":
            self.log_path = self.data_manager.manager_log_analyzer._path
        elif select_type == "stdout":
            print("beep")
            self.log_path = self.data_manager.stdout_log_analyzers[
                select_component
            ]._path
            print(self.log_path)
        elif select_type == "stderr":
            print("boop")
            self.log_path = self.data_manager.stderr_log_analyzers[
                select_component
            ]._path
        else:
            self.log_path = self.data_manager.run_folder
        self.truncate_message_container.object = self.truncate_message

    @property
    def current_tab(self):
        return self.tabs._names[self.tabs.active]

    @property
    def current_select(self):
        return self.select.value

    @property
    def truncate_message(self):
        return (
            f"Logs are truncated at {MAX_LINES} lines. "
            f"Full logs found at {os.path.abspath(self.log_path)}"
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
            margin=CARD_MARGIN,
        )

    def update(self, event):
        """Method to update log file viewer from listener"""
        for line in self.data_manager.manager_log_lines[-MAX_LINES:]:
            self.manager_terminal.write(line)

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
        self.select.groups = dict(sorted(groups.items()))

    def __panel__(self):
        return self.card
