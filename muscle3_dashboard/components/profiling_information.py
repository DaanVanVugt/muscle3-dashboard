import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN
from muscle3_dashboard.data_manager import DataManager


class ProfilingInformationViewer(pn.viewable.Viewer):
    def __init__(self, data_manager: DataManager) -> None:
        super().__init__()
        self.card = pn.Card(
            "<em>Placeholder</em> No crash detected",
            title="Profiling information",
            margin=CARD_MARGIN,
            sizing_mode="stretch_width",
        )
        self.data_manager = data_manager
        self.data_manager.param.watch(self.update, "event_called")

    def update(self, event):
        pass

    def __panel__(self):
        return self.card
