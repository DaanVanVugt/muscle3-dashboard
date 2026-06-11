import html
from collections import defaultdict
from pathlib import Path

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
        self.manager_terminal = self.log_terminal()
        self.muscle_manager_tab = self.log_pane(
            self.manager_terminal,
            self.data_manager.manager_log_analyzer.path,
        )
        self.component_tabs = self.components_tab_pane()
        self.tabs = pn.Tabs(
            ("Muscle manager logs", self.muscle_manager_tab),
            ("Component logs", self.component_tabs),
            sizing_mode="stretch_width",
            max_height=800,
        )
        # Last-update timestamp shown top-right of the card header.
        self.last_update_pane = pn.pane.HTML(
            self._last_update_html(),
            align="center",
            styles={"color": "#888", "font-size": "0.85em"},
        )
        self.card = pn.Card(
            self.tabs,
            margin=CARD_MARGIN,
            header=pn.Row(
                pn.pane.HTML("<b>Log files</b>", align="center"),
                pn.HSpacer(),
                self.last_update_pane,
                sizing_mode="stretch_width",
            ),
        )

    def _last_update_html(self) -> str:
        ts = self.data_manager.logs_last_updated
        return f"updated {ts.strftime('%H:%M:%S')}" if ts else ""

    def components_tab_pane(self) -> pn.Column:
        """Tab for separate component logs"""
        self.component_terminals = {}
        self.component_panes = {}
        self.select = pn.widgets.Select(name="Choose log", groups={})
        self.component_container = pn.pane.Placeholder(
            "",
            sizing_mode="stretch_width",
        )
        self.select.param.watch(self.update_component_logs, "value")
        return pn.Column(
            self.select,
            self.component_container,
            sizing_mode="stretch_width",
        )

    def update_component_logs(self, event) -> None:
        """Update component logs on trigger"""
        self.component_container.object = self.component_panes[event.new]

    def log_pane(self, terminal: pn.widgets.Terminal, path: Path) -> pn.Column:
        """Get basic log panel with terminal and filepath message.

        The path copies to the clipboard on click and offers a file://
        link to open it in the desktop editor / file manager.
        """
        resolved = html.escape(str(path.resolve()))
        return pn.Column(
            terminal,
            pn.pane.HTML(
                f"Logs are truncated at {MAX_LINES} lines. Full log: "
                f'<span title="click to copy" '
                f'onclick="navigator.clipboard.writeText(this.dataset.path)" '
                f'data-path="{resolved}" '
                f'style="cursor:pointer;font-family:monospace">{resolved}</span> '
                f'<a href="file://{resolved}" title="open in editor" '
                f'target="_blank" style="text-decoration:none">&#x2197;</a>',
                sizing_mode="stretch_width",
            ),
            sizing_mode="stretch_width",
        )

    def log_terminal(self) -> pn.widgets.Terminal:
        """Get basic terminal"""
        return pn.widgets.Terminal(
            "",
            sizing_mode="stretch_width",
            height=TERMINAL_HEIGHT,
            options={"wrap": True},
            margin=CARD_MARGIN,
        )

    def update(self, event) -> None:
        """Method to update log file viewer from listener"""
        self.last_update_pane.object = self._last_update_html()
        for line in self.data_manager.manager_log_lines[-MAX_LINES:]:
            self.manager_terminal.write(line)

        for log_lines, analyzers, type in [
            (
                self.data_manager.stdout_log_lines,
                self.data_manager.stdout_log_analyzers,
                "stdout",
            ),
            (
                self.data_manager.stderr_log_lines,
                self.data_manager.stderr_log_analyzers,
                "stderr",
            ),
        ]:
            for component, lines in log_lines.items():
                key = f"{component} - {type}"
                if key not in self.component_terminals:
                    self.component_terminals[key] = self.log_terminal()
                    self.component_panes[key] = self.log_pane(
                        self.component_terminals[key],
                        analyzers[component].path,
                    )
                for line in lines[-MAX_LINES:]:
                    self.component_terminals[key].write(line)

        groups = defaultdict(list)
        for key in self.component_terminals:
            component, _ = key.split(" - ")

            groups[component].append(key)
        self.select.groups = dict(sorted(groups.items()))

    def show_component(self, component: str) -> None:
        """Switch to and show the logs of the given component.

        Called when a component is clicked in the status table.
        """
        for keys in self.select.groups.values():
            for key in keys:
                if key.split(" - ")[0] == component:
                    self.select.value = key
                    self.tabs.active = 1  # the "Component logs" tab
                    return

    def __panel__(self):
        return self.card
