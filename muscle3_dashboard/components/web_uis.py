import html

import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN


class WebUIsViewer(pn.viewable.Viewer):
    """Card listing served-UI links per component (harvested + proxied).

    ``web_urls`` maps a component name to a ready HTML snippet (one or more
    links). The card is hidden when there are none, e.g. for finished runs or
    runs whose actors expose no UI. Previously these links were a column in the
    component status table, which has been replaced by the clickable graph.
    """

    def __init__(self, web_urls: dict[str, str] | None = None) -> None:
        super().__init__()
        web_urls = web_urls or {}
        # web_urls values are already HTML links; only the component name is
        # untrusted text and gets escaped.
        rows = "".join(
            f'<div style="margin:2px 0"><b>{html.escape(name)}</b>: {link}</div>'
            for name, link in sorted(web_urls.items())
        )
        self.card = pn.Card(
            pn.pane.HTML(rows, sizing_mode="stretch_width"),
            title="Web UIs",
            margin=CARD_MARGIN,
            sizing_mode="stretch_width",
            collapsible=False,
            visible=bool(web_urls),
        )

    def __panel__(self):
        return self.card
