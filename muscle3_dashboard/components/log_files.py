import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN


class LogFilesViewer(pn.viewable.Viewer):
    def __init__(self) -> None:
        super().__init__()
        self.aggregated_tab = self.aggregated_tab_pane()
        self.muscle_manager_tab = self.muscle_manager_tab_pane()
        self.component_tabs = self.components_tab_pane()
        self.tabs = pn.Tabs(
            # ("Aggregated logs", self.aggregated_tab), # TODO
            ("Muscle manager logs", self.muscle_manager_tab),
            ("Component logs", self.component_tabs),
            sizing_mode="stretch_width",
            tabs_location="left",
            max_height=800,
            stylesheets=[".bk-tab {text-align: right;}"],
        )
        self.card = pn.Card(self.tabs, margin=CARD_MARGIN, title="Log files")

    def aggregated_tab_pane(self):
        return self.log_pane()

    def muscle_manager_tab_pane(self):
        return self.log_pane()

    def components_tab_pane(self):
        self.component_terminals = {}
        self.select = pn.widgets.Select(name="Choose log", groups={})
        self.terminal_container = pn.Column()
        self.select.param.watch(self.update_component_logs, "value")
        return pn.Column(self.select, self.terminal_container)

    def update_component_logs(self, event):
        if event.new not in self.component_terminals:
            self.component_terminals[event.new] = self.log_pane()
        self.terminal_container.clear()
        self.terminal_container.append(self.component_terminals[event.new])

    def log_pane(self):
        return pn.widgets.Terminal(
            "",
            sizing_mode="stretch_both",
            options={"wrap": False},
        )

    def update(
        self,
        manager_log_lines=None,
        stdout_log_lines=None,
        stderr_log_lines=None,
    ):
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

        from collections import defaultdict

        groups = defaultdict(list)
        for key in self.component_terminals:
            component, _ = key.split("-")

            groups[component].append(key)
        self.select.groups = groups

    def __panel__(self):
        return self.card
