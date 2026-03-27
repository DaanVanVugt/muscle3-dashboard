import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN


class ProfilingInformationViewer(pn.viewable.Viewer):
    def __init__(self) -> None:
        super().__init__()
        self.card = pn.Card(
            "<em>Placeholder</em> No crash detected",
            title="Crash analysis",
            margin=CARD_MARGIN,
            sizing_mode="stretch_width",
        )

    def __panel__(self):
        return self.card
