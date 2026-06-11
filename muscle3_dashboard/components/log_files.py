import html
from pathlib import Path

import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN, MAX_LINES, TERMINAL_HEIGHT
from muscle3_dashboard.data_manager import DataManager
from muscle3_dashboard.pathlink import path_html

MANAGER = "muscle_manager"


class LogFilesViewer(pn.viewable.Viewer):
    """Panel component showing one log at a time: the muscle manager log
    or a component's stdout/stderr.

    The shown source follows row clicks in the status and log-messages
    tables (call ``show_source``; the ``muscle_manager`` source maps to
    the manager log). A stdout/stderr switcher sits on the right of the
    card header; it is disabled for the manager log, which has no
    separate streams.
    """

    def __init__(self, data_manager: DataManager) -> None:
        super().__init__()
        self.data_manager = data_manager
        self.data_manager.param.watch(self.update, "data_updated")
        self.log_path = self.data_manager.run_folder
        self.manager_terminal = self.log_terminal()
        self.manager_pane = self.log_pane(
            self.manager_terminal,
            self.data_manager.manager_log_analyzer.path,
        )
        self.component_terminals: dict[str, pn.widgets.Terminal] = {}
        self.component_panes: dict[str, pn.Column] = {}
        self._has_output: set[str] = set()
        self.source = MANAGER

        self.stream_toggle = pn.widgets.RadioButtonGroup(
            options=["stdout", "stderr"],
            value="stdout",
            align="center",
            width=160,
        )
        self.stream_toggle.param.watch(self._show_current, "value")
        self.title_pane = pn.pane.HTML("", align="center")
        self.container = pn.pane.Placeholder(
            self.manager_pane, sizing_mode="stretch_width"
        )
        self.card = pn.Card(
            self.container,
            margin=CARD_MARGIN,
            collapsible=False,
            header=pn.Row(
                self.title_pane,
                pn.HSpacer(),
                self.stream_toggle,
                sizing_mode="stretch_width",
            ),
        )
        self._show_current()

    def _show_current(self, *_events) -> None:
        """Point the container at the currently selected log"""
        if self.source == MANAGER:
            self.stream_toggle.disabled = True
            shown = MANAGER
            pane = self.manager_pane
        else:
            self.stream_toggle.disabled = False
            shown = f"{self.source} {self.stream_toggle.value}"
            key = f"{self.source} - {self.stream_toggle.value}"
            pane = self.component_panes.get(
                key, pn.pane.Markdown(f"No output for `{shown}` yet.")
            )
        self.title_pane.object = f"<b>Log files</b> — {html.escape(shown)}"
        self.container.object = pane

    def show_source(self, source: str) -> None:
        """Switch to and show the logs of the given source.

        Called when a row is clicked in the status table or in the
        log-messages table; ``muscle_manager`` shows the manager log.
        Picks the stream automatically: stderr when it has messages,
        stdout otherwise.
        """
        self.source = source
        if source != MANAGER:
            self.stream_toggle.value = (
                "stderr" if f"{source} - stderr" in self._has_output else "stdout"
            )
        self._show_current()

    def log_pane(self, terminal: pn.widgets.Terminal, path: Path) -> pn.Column:
        """Get basic log panel with terminal and filepath message.

        The path copies to the clipboard on click and links to the file.
        """
        return pn.Column(
            terminal,
            pn.pane.HTML(
                f"Logs are truncated at {MAX_LINES} lines. Full log: "
                + path_html(path, monospace=True),
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
        for line in self.data_manager.manager_log_lines[-MAX_LINES:]:
            self.manager_terminal.write(line)

        created = False
        for log_lines, analyzers, stream in [
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
                key = f"{component} - {stream}"
                if key not in self.component_terminals:
                    self.component_terminals[key] = self.log_terminal()
                    self.component_panes[key] = self.log_pane(
                        self.component_terminals[key],
                        analyzers[component].path,
                    )
                    created = True
                if lines:
                    self._has_output.add(key)
                for line in lines[-MAX_LINES:]:
                    self.component_terminals[key].write(line)

        # A selected source may have shown the "no output yet" fallback
        # before its terminal existed.
        if created and self.source != MANAGER:
            self._show_current()

    def __panel__(self):
        return self.card
