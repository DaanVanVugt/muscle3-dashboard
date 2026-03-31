import datetime

import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN


class OverviewViewer(pn.viewable.Viewer):
    """Panel component to get a basic overview of the simulation"""

    def __init__(self) -> None:
        super().__init__()
        self.components = []
        self.status = "Running"
        self.logs_last_updated = datetime.datetime.now()
        self.markdown = pn.pane.Markdown("""
            *PLACEHOLDER!*

            - **Simulation status**: Running (?)
            - **Last log update**: 2026-03-25 10:41:32 (1 second ago)
            - **Components**
              - Found 20 components in the simulation
              - Found log files for 20 components in the run folder
        """)
        self.card = pn.Card(
            self.markdown,
            title="Overview",
            sizing_mode="stretch_both",
            margin=CARD_MARGIN,
        )

    def update(self, logs_last_updated, status, components):
        """Method to update the overview viewer from outside"""
        self.logs_last_updated = logs_last_updated
        self.status = status
        self.components = components
        self.markdown.object = self.markdown_str()

    @property
    def last_updated_str(self):
        """Build string for last_updated based on inner state"""
        return self.logs_last_updated.strftime("%Y-%m-%d %H:%M:%S")

    def markdown_str(self):
        """Build string for markdown based on inner state"""
        return f"""
            - **Simulation status**: {self.status}
            - **Last log update**: {self.last_updated_str}
            - **Components**: Found {len(self.components)} components in simulation
        """

    def __panel__(self):
        return self.card
