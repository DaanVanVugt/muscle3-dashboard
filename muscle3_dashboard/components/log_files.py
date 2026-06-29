import html

import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN, MAX_LINES, TERMINAL_HEIGHT
from muscle3_dashboard.data_manager import DataManager
from muscle3_dashboard.instances import base_name, instance_label, instance_sort_key
from muscle3_dashboard.pathlink import copy_link

MANAGER = "muscle_manager"

#: Above this many instances the side-by-side radio buttons get unwieldy, so a
#: dropdown is used instead.
_MAX_RADIO_INSTANCES = 20


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
        self.manager_terminal = self.log_terminal()
        self.component_terminals: dict[str, pn.widgets.Terminal] = {}
        self._has_output: set[str] = set()
        self.source = MANAGER

        # Picks which instance of a multi-instance component (e.g. nice_inv[4])
        # to show. Holds a RadioButtonGroup of instance numbers, or a dropdown
        # when there are too many; hidden for the manager log and single
        # instances. _instance is the chosen instance name.
        self._instance: str | None = None
        self.instance_slot = pn.Row(align="center", margin=0, visible=False)
        self.stream_toggle = pn.widgets.RadioButtonGroup(
            options=["stdout", "stderr"],
            value="stdout",
            align="center",
            width=160,
        )
        self.stream_toggle.param.watch(self._show_current, "value")
        # The muscle_manager has no component box in the graph, so its log is
        # reached from this button. It's an action ("show the manager log"), so
        # it's de-emphasised (light) while that log is already shown.
        self.manager_button = pn.widgets.Button(
            name="muscle_manager log",
            button_type="default",
            width=150,
            margin=(5, 12),
            align="center",
        )
        self.manager_button.on_click(lambda event: self.show_source(MANAGER))
        self.title_pane = pn.pane.HTML("", align="center")
        self.container = pn.pane.Placeholder(
            self.manager_terminal, sizing_mode="stretch_width"
        )
        self.card = pn.Card(
            self.container,
            margin=CARD_MARGIN,
            collapsible=False,
            header=pn.Row(
                self.title_pane,
                pn.HSpacer(),
                self.manager_button,
                self.instance_slot,
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
                if base_name(name) == source
            ),
            key=instance_sort_key,
        )
        return matches or [source]

    def _build_instance_selector(self, instances: list[str]) -> None:
        """(Re)build the instance selector for ``instances`` and pick one.

        Side-by-side number buttons for a handful of instances, a dropdown when
        there are many. Sets ``self._instance`` to the chosen instance name.
        """
        self._instance = self._instance if self._instance in instances else instances[0]
        if len(instances) <= _MAX_RADIO_INSTANCES:
            widget = pn.widgets.RadioButtonGroup(
                # label = instance number, value = full instance name
                options={instance_label(name): name for name in instances},
                value=self._instance,
                align="center",
            )
        else:
            widget = pn.widgets.Select(
                options=instances, value=self._instance, align="center", width=160
            )
        widget.param.watch(self._on_instance_change, "value")
        self.instance_slot.objects = [widget]
        self.instance_slot.visible = len(instances) > 1

    def _on_instance_change(self, event) -> None:
        self._instance = event.new
        self._show_current()

    def _show_current(self, *_events) -> None:
        """Point the container at the currently selected log"""
        path = None
        # De-emphasise the button (light) while the manager log is already the
        # one shown; offer it as a normal action (default) otherwise.
        self.manager_button.button_type = (
            "light" if self.source == MANAGER else "default"
        )
        if self.source == MANAGER:
            # The manager log is a single stream: the stdout/stderr toggle is
            # irrelevant, so hide it rather than show it disabled.
            self.stream_toggle.visible = False
            self.instance_slot.visible = False
            shown = MANAGER
            pane = self.manager_terminal
            path = self.data_manager.manager_log_analyzer.path
        else:
            self.stream_toggle.visible = True
            instance = self._instance or self.source
            stream = self.stream_toggle.value
            shown = f"{instance} {stream}"
            key = f"{instance} - {stream}"
            pane = self.component_terminals.get(
                key, pn.pane.Markdown(f"No output for `{shown}` yet.")
            )
            analyzers = (
                self.data_manager.stdout_log_analyzers
                if stream == "stdout"
                else self.data_manager.stderr_log_analyzers
            )
            analyzer = analyzers.get(instance)
            path = analyzer.path if analyzer is not None else None
        # The shown name is itself the click-to-copy link for the log path, so
        # the long path doesn't show (or wrap) in the subtitle.
        name = copy_link(shown, path) if path is not None else html.escape(shown)
        self.title_pane.object = (
            f'<span style="white-space:nowrap"><b>Log files</b> — {name}</span>'
        )
        self.container.object = pane

    def show_source(self, source: str) -> None:
        """Switch to and show the logs of the given source.

        Called when a component is clicked in the graph or a row in the
        log-messages table; ``muscle_manager`` shows the manager log. For a
        component with multiple instances (multiplicity, e.g. ``nice_inv[4]``)
        an instance selector is shown. Lands on the instance that actually has
        stderr output (the crashing one for an auto-opened crash, not just
        instance 0), and picks the stream automatically: stderr when the chosen
        instance has messages there, stdout otherwise.
        """
        self.source = source
        if source != MANAGER:
            instances = self._instances_for(source)
            # Prefer the first instance with stderr output so an auto-opened
            # crash shows the traceback rather than instance 0's empty stdout.
            preferred = next(
                (i for i in instances if f"{i} - stderr" in self._has_output), None
            )
            if preferred is not None:
                self._instance = preferred
            self._build_instance_selector(instances)
            self.stream_toggle.value = (
                "stderr"
                if f"{self._instance} - stderr" in self._has_output
                else "stdout"
            )
        self._show_current()

    def log_terminal(self) -> pn.widgets.Terminal:
        """Create a blank terminal widget for a log."""
        return pn.widgets.Terminal(
            "",
            sizing_mode="stretch_width",
            height=TERMINAL_HEIGHT,
            options={"wrap": True},
            margin=CARD_MARGIN,
        )

    def update(self, event) -> None:
        """Append new log lines to the manager and per-component terminals."""
        for line in self.data_manager.manager_log_lines[-MAX_LINES:]:
            self.manager_terminal.write(line)

        created = False
        for log_lines, stream in [
            (self.data_manager.stdout_log_lines, "stdout"),
            (self.data_manager.stderr_log_lines, "stderr"),
        ]:
            for component, lines in log_lines.items():
                key = f"{component} - {stream}"
                if key not in self.component_terminals:
                    self.component_terminals[key] = self.log_terminal()
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
