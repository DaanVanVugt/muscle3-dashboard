import html
import re
from pathlib import Path

import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN, MAX_LINES, TERMINAL_HEIGHT
from muscle3_dashboard.data_manager import DataManager
from muscle3_dashboard.pathlink import path_html

MANAGER = "muscle_manager"


def _base_name(source: str) -> str:
    """Strip a multiplicity suffix: ``nice_inv[4]`` -> ``nice_inv``."""
    return re.sub(r"\[.*\]$", "", source)


def _instance_sort_key(name: str):
    """Sort instances by their numeric index (``nice_inv[2]`` before ``[10]``)."""
    match = re.search(r"\[(\d+)\]", name)
    return (int(match.group(1)),) if match else (-1,)


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

        # Picks which instance of a multi-instance component (e.g. nice_inv[4])
        # to show; hidden for the manager log and single-instance components.
        self.instance_selector = pn.widgets.Select(
            options=[], align="center", width=160, visible=False
        )
        self.instance_selector.param.watch(self._show_current, "value")
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
                self.instance_selector,
                self.stream_toggle,
                sizing_mode="stretch_width",
            ),
        )
        self._show_current()

    def _instances_for(self, source: str) -> list[str]:
        """Instance log names for a component (its own name if single)."""
        matches = sorted(
            (
                name
                for name in self.data_manager.stdout_log_analyzers
                if _base_name(name) == source
            ),
            key=_instance_sort_key,
        )
        return matches or [source]

    def _show_current(self, *_events) -> None:
        """Point the container at the currently selected log"""
        if self.source == MANAGER:
            self.stream_toggle.disabled = True
            self.instance_selector.visible = False
            shown = MANAGER
            pane = self.manager_pane
        else:
            self.stream_toggle.disabled = False
            instance = self.instance_selector.value or self.source
            shown = f"{instance} {self.stream_toggle.value}"
            key = f"{instance} - {self.stream_toggle.value}"
            pane = self.component_panes.get(
                key, pn.pane.Markdown(f"No output for `{shown}` yet.")
            )
        self.title_pane.object = f"<b>Log files</b> — {html.escape(shown)}"
        self.container.object = pane

    def show_source(self, source: str) -> None:
        """Switch to and show the logs of the given source.

        Called when a component is clicked in the graph or a row in the
        log-messages table; ``muscle_manager`` shows the manager log. For a
        component with multiple instances (multiplicity, e.g. ``nice_inv[4]``)
        an instance selector is shown. Picks the stream automatically: stderr
        when the chosen instance has messages there, stdout otherwise.
        """
        self.source = source
        if source != MANAGER:
            instances = self._instances_for(source)
            self.instance_selector.options = instances
            if self.instance_selector.value not in instances:
                self.instance_selector.value = instances[0]
            self.instance_selector.visible = len(instances) > 1
            instance = self.instance_selector.value
            self.stream_toggle.value = (
                "stderr" if f"{instance} - stderr" in self._has_output else "stdout"
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
