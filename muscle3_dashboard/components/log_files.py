import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN


class LogFilesViewer(pn.viewable.Viewer):
    def __init__(self) -> None:
        super().__init__()
        tabs = pn.Tabs(
            pn.pane.Markdown(
                """
                TODO: Show aggregated log files

                **N.B.** This will only show log messages appended since the dashboard
                started!
                """,
                name="Aggregated logs",
            ),
            pn.pane.Markdown(
                "TODO: Muscle manager log file", name="Muscle manager logs"
            ),
            pn.pane.Markdown(
                "TODO: `stdout.txt` and `stderr.txt` for each component",
                name="Component logs",
            ),
            sizing_mode="stretch_width",
            tabs_location="left",
            max_height=800,
            stylesheets=[".bk-tab {text-align: right;}"],
        )
        self.card = pn.Card(tabs, margin=CARD_MARGIN, title="Log files")

    def __panel__(self):
        return self.card
