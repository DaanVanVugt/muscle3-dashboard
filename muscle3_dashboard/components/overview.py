import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN
from muscle3_dashboard.data_manager import DataManager


class OverviewViewer(pn.viewable.Viewer):
    def __init__(self, data_manager: DataManager) -> None:
        super().__init__()
        self.card = pn.Card(
            pn.pane.Markdown(
                """
            *PLACEHOLDER!*

            - **Simulation status**: Running (?)
            - **Last log update**: 2026-03-25 10:41:32 (1 second ago)
            - **Components**
              - Found 20 components in the simulation
              - Found log files for 20 components in the run folder
            """,
            ),
            title="Overview",
            sizing_mode="stretch_both",
            margin=CARD_MARGIN,
        )
        self.data_manager = data_manager
        self.data_manager.param.watch(self.update, "event_called")

    def update(self, event):
        pass

    def __panel__(self):
        return self.card
