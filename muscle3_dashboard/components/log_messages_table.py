import pandas as pd
import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN


class LogMessagesTableViewer(pn.viewable.Viewer):
    """Panel component showing the number of log messages per log level for
    different muscle3 components and the muscle_manager"""

    def __init__(self) -> None:
        super().__init__()
        logmessages = pd.DataFrame(
            {
                "component": ["muscle_manager"],
                "DEBUG": [0],
                "INFO": [0],
                "WARNING": [0],
                "ERROR": [0],
                "CRITICAL": [0],
                "unknown": [0],
            }
        ).set_index("component")

        self.log_table = pn.widgets.Tabulator(
            pd.concat([logmessages, logmessages.sum().to_frame("Total").T]),
            frozen_rows=[-1],
            disabled=True,
            selectable=1,
            sizing_mode="stretch_both",
            sorters=[
                {"field": name, "dir": "desc"}
                for name in ("critical", "error", "warning", "info", "debug")
            ],
        )

        self.card = pn.Card(
            self.log_table,
            title="All log messages",
            sizing_mode="stretch_both",
            collapsible=False,
            margin=CARD_MARGIN,
        )

    def __panel__(self):
        return self.card
