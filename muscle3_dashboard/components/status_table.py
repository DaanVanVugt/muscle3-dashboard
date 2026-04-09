import pandas as pd
import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN
from muscle3_dashboard.data_manager import DataManager


class StatusTableViewer(pn.viewable.Viewer):
    """Panel component showing the status and exitcodes for every muscle3
    component in the simulation."""

    def __init__(self, data_manager: DataManager) -> None:
        super().__init__()
        self.component_status_table = pn.widgets.Tabulator(
            pd.DataFrame([], columns=["component", "status", "exitcode"]).set_index(
                "component"
            ),
            disabled=True,
            selectable=1,
            sizing_mode="stretch_both",
        )

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

    def update(self, event):
        df = self.data_manager.manager_log_analyzer.to_dataframe()
        if self.component_status_table.value.empty:
            self.component_status_table.value = df
        else:
            self.component_status_table.patch(df)

    def __panel__(self):
        return self.card
