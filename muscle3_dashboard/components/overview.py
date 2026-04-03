import datetime

import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN
from muscle3_dashboard.data_manager import DataManager


class OverviewViewer(pn.viewable.Viewer):
    """Panel component to get a basic overview of the simulation"""

    def __init__(self, data_manager: DataManager) -> None:
        super().__init__()
        self.components = []
        self.status = "Running"
        self.logs_last_updated = datetime.datetime.now()
        self.markdown = pn.pane.Markdown("")
        self.card = pn.Card(
            self.markdown,
            title="Overview",
            sizing_mode="stretch_both",
            margin=CARD_MARGIN,
        )
        self.data_manager = data_manager
        self.data_manager.param.watch(self.update, "data_updated")

    def update(self, event):
        """Method to update overview viewer from listener"""
        self.logs_last_updated = self.data_manager.logs_last_updated
        self.status = self.data_manager.manager_log_analyzer.status
        self.components = self.data_manager.manager_log_analyzer.components.keys()
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
