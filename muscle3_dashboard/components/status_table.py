import html
from collections.abc import Callable

import pandas as pd
import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN
from muscle3_dashboard.data_manager import DataManager
from muscle3_dashboard.loganalyzer.manager import ComponentStatus

#: Status-dot colours per component status, dark shades for the light card.
_STATUS_COLORS = {
    ComponentStatus.NOT_STARTED: "#ef6c00",
    ComponentStatus.PLANNED: "#2e7d32",
    ComponentStatus.INSTANTIATING: "#2e7d32",
    ComponentStatus.REGISTERED: "#2e7d32",
    ComponentStatus.DEREGISTERED: "#616161",
    ComponentStatus.FINISHED: "#616161",
}
_FAILED_COLOR = "#c62828"


def _status_html(status: ComponentStatus, failed: bool) -> str:
    color = _FAILED_COLOR if failed else _STATUS_COLORS[status]
    return f'<span style="color:{color}">&#x25cf;</span> {status.value}'


def _exit_code_html(exit_code: str) -> str:
    if exit_code in ("", "0"):
        return exit_code
    return f'<b style="color:{_FAILED_COLOR}">{html.escape(exit_code)}</b>'


class StatusTableViewer(pn.viewable.Viewer):
    """Panel component showing the status and exitcodes for every muscle3
    component in the simulation.

    ``web_urls`` optionally maps a component name to an HTML snippet (e.g.
    a link to a served UI); when given, a "web UI" column is shown. Pass
    ``on_select`` to be notified (with the component name) when a row is
    clicked, e.g. to show that component's logs; clicks in the web UI
    column are left to the link.
    """

    def __init__(
        self,
        data_manager: DataManager,
        web_urls: dict[str, str] | None = None,
        on_select: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self.web_urls = web_urls or {}
        self.on_select = on_select
        columns = ["component", "status", "exit_code"]
        formatters = {
            "status": {"type": "html"},
            "exit_code": {"type": "html"},
        }
        if self.web_urls:
            columns.append("web UI")
            formatters["web UI"] = {"type": "html"}
        self.component_status_table = pn.widgets.Tabulator(
            pd.DataFrame([], columns=columns).set_index("component"),
            disabled=True,
            selectable=1,
            formatters=formatters,
            sizing_mode="stretch_width",
        )
        self.component_status_table.on_click(self._handle_click)

        self.card = pn.Card(
            self.component_status_table,
            title="Component status",
            margin=CARD_MARGIN,
            sizing_mode="stretch_width",
            collapsible=False,
        )
        self.data_manager = data_manager
        self.data_manager.param.watch(self.update, "data_updated")

    def _to_display(self, df: pd.DataFrame) -> pd.DataFrame:
        """Decorate the raw status dataframe with colours and links"""
        df = df.copy()
        failed = [code not in ("", "0") for code in df["exit_code"]]
        df["status"] = [
            _status_html(status, fail)
            for status, fail in zip(df["status"], failed, strict=True)
        ]
        df["exit_code"] = df["exit_code"].map(_exit_code_html)
        if self.web_urls:
            df["web UI"] = [self.web_urls.get(name, "") for name in df.index]
        return df

    def update(self, event):
        df = self._to_display(self.data_manager.manager_log_analyzer.to_dataframe())
        if self.component_status_table.value.empty:
            self.component_status_table.value = df
        else:
            self.component_status_table.patch(df)

    def _handle_click(self, event) -> None:
        if self.on_select is None or event.column == "web UI":
            return
        component = str(self.component_status_table.value.index[event.row])
        self.on_select(component)

    def __panel__(self):
        return self.card
