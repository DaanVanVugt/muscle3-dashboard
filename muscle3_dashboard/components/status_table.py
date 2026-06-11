from typing import Callable, Dict, Optional

import pandas as pd
import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN
from muscle3_dashboard.data_manager import DataManager


class StatusTableViewer(pn.viewable.Viewer):
    """Panel component showing the status and exitcodes for every muscle3
    component in the simulation.

    ``web_urls`` optionally maps a component name to an HTML snippet (e.g.
    a link to a served UI); when given, a "web UI" column is shown. Pass
    ``on_select`` to be notified (with the component name) when a row is
    clicked, e.g. to show that component's logs.
    """

    def __init__(
        self,
        data_manager: DataManager,
        web_urls: Optional[Dict[str, str]] = None,
        on_select: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__()
        self.web_urls = web_urls or {}
        self.on_select = on_select
        columns = ["component", "status", "exit_code"]
        formatters = {}
        if self.web_urls:
            columns.append("web UI")
            formatters["web UI"] = {"type": "html"}
        self.component_status_table = pn.widgets.Tabulator(
            pd.DataFrame([], columns=columns).set_index("component"),
            disabled=True,
            selectable=1,
            formatters=formatters,
            sizing_mode="stretch_both",
        )
        if self.on_select is not None:
            self.component_status_table.param.watch(self._handle_select, "selection")

        self.card = pn.Card(
            self.component_status_table,
            title="Component status",
            margin=CARD_MARGIN,
            sizing_mode="stretch_both",
            collapsible=False,
            width_policy="min",
        )
        self.data_manager = data_manager
        self.data_manager.param.watch(self.update, "data_updated")

    def _with_web_ui(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.web_urls:
            df = df.copy()
            df["web UI"] = [self.web_urls.get(name, "") for name in df.index]
        return df

    def update(self, event):
        df = self._with_web_ui(self.data_manager.manager_log_analyzer.to_dataframe())
        if self.component_status_table.value.empty:
            self.component_status_table.value = df
        else:
            self.component_status_table.patch(df)

    def _handle_select(self, event) -> None:
        rows = event.new
        if not rows:
            return
        df = self.component_status_table.value
        component = str(df.index[rows[0]])
        if self.on_select is not None:
            self.on_select(component)

    def __panel__(self):
        return self.card
