import pandas as pd
import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN


class StatusTableViewer(pn.viewable.Viewer):
    def __init__(self) -> None:
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

    def __panel__(self):
        return self.card
