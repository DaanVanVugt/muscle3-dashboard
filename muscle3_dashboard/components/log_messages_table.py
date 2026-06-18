import re
from collections.abc import Callable

import pandas as pd
import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN
from muscle3_dashboard.data_manager import DataManager

_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "unknown"]
#: Highlight colours for nonzero counts of the levels that need attention.
_LEVEL_COLORS = {"WARNING": "#ef6c00", "ERROR": "#c62828", "CRITICAL": "#c62828"}

#: Detect a log level near the start of a component log line, after an optional
#: ANSI colour code and up to three leading date/time tokens. Handles both
#: ``INFO:logger:msg`` (stdlib logging) and ``2026-06-18 08:55 INFO ...`` forms.
_LEVEL_RE = re.compile(
    r"^(?:\x1b\[[0-9;]*m)?\s*(?:[\d:.,\-]+\s+){0,3}"
    r"(DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL|FATAL)\b"
)
_LEVEL_ALIASES = {"WARN": "WARNING", "FATAL": "CRITICAL"}


def _detect_level(line: str) -> str | None:
    """Return the log level of a component log line, or None if not found."""
    match = _LEVEL_RE.match(line)
    if match is None:
        return None
    return _LEVEL_ALIASES.get(match.group(1), match.group(1))


def _count_html(level: str, count: int) -> str:
    if not count:
        return '<span style="opacity:0.4">0</span>'
    color = _LEVEL_COLORS.get(level)
    if color:
        return f'<b style="color:{color}">{count}</b>'
    return str(count)


class LogMessagesTableViewer(pn.viewable.Viewer):
    """Panel component showing the number of log messages per log level,
    per source (the muscle_manager itself and each remote component).

    Pass ``on_select`` to be notified (with the source name) when a row
    is clicked, e.g. to show that source's log file.
    """

    def __init__(
        self,
        data_manager: DataManager,
        on_select: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self.data_manager = data_manager
        self.on_select = on_select
        # Cumulative per-component level counts derived from the components' own
        # stdout/stderr (the manager log only carries the manager's messages and
        # whatever components forward to it, often nothing).
        self._component_levels: dict[str, dict[str, int]] = {}

        # NB: no frozen_rows -- freezing rows renders them in a separate
        # layer offset from the headers.
        self.log_table = pn.widgets.Tabulator(
            self._to_dataframe(),
            disabled=True,
            selectable=1,
            show_index=True,
            layout="fit_data_table",
            formatters={level: {"type": "html"} for level in _LEVELS},
        )
        self.log_table.on_click(self._handle_click)

        self.card = pn.Card(
            self.log_table,
            title="Log messages",
            sizing_mode="stretch_width",
            collapsible=False,
            margin=CARD_MARGIN,
        )
        self.data_manager.param.watch(self.update, "data_updated")

    def _accumulate_component_levels(self) -> None:
        """Fold the latest component log lines into cumulative level counts."""
        dm = self.data_manager
        for lines_by_component in (dm.stdout_log_lines, dm.stderr_log_lines):
            for component, lines in lines_by_component.items():
                counts = self._component_levels.setdefault(
                    component, dict.fromkeys(_LEVELS, 0)
                )
                for line in lines:
                    level = _detect_level(line)
                    if level:
                        counts[level] += 1

    def _to_dataframe(self) -> pd.DataFrame:
        """Counts per source, muscle_manager first, components sorted.

        The muscle_manager row comes from the manager log; component rows come
        from each component's own stdout/stderr (so they match the log shown
        when that row is clicked), overriding any forwarded counts.
        """
        analyzer = self.data_manager.manager_log_analyzer
        by_source = dict(analyzer.messages_per_level_by_source)
        for component, counts in self._component_levels.items():
            if any(counts.values()):
                by_source[component] = counts
        if not by_source:
            by_source = {"muscle_manager": {}}
        rows = {
            source: [_count_html(level, counts.get(level, 0)) for level in _LEVELS]
            for source, counts in sorted(
                by_source.items(), key=lambda kv: (kv[0] != "muscle_manager", kv[0])
            )
        }
        df = pd.DataFrame.from_dict(rows, orient="index", columns=_LEVELS)
        df.index.name = "source"
        return df

    def update(self, event):
        """Method to update log messages table viewer from listener"""
        self._accumulate_component_levels()
        df = self._to_dataframe()
        if df.index.equals(self.log_table.value.index):
            self.log_table.patch(df)
        else:
            self.log_table.value = df

    def _handle_click(self, event) -> None:
        if self.on_select is None:
            return
        self.on_select(str(self.log_table.value.index[event.row]))

    def select_source(self, source: str) -> None:
        """Highlight the row of the given source, clearing the highlight
        if it has no row here. Keeps the table selections linked."""
        index = list(self.log_table.value.index)
        self.log_table.selection = [index.index(source)] if source in index else []

    def __panel__(self):
        return self.card
