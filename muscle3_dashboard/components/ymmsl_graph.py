import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN
from muscle3_dashboard.data_manager import DataManager


class PlacholderGraph:
    def _repr_svg_(self):
        return """<svg xmlns="http://www.w3.org/2000/svg" width="436"
height="136"><defs><path stroke="black" stroke-width="2" id="port:f_init" d="M -1 0 L -4
-3 L -7 0 L -4 3 Z " fill="none"/><path stroke="black" stroke-width="2" id="port:o_f"
d="M 1 0 L 4 -3 L 7 0 L 4 3 Z " fill="black"/><circle stroke="black" stroke-width="2"
id="port:o_i" cy="3" r="2" fill="black"/><circle stroke="black" stroke-width="2"
id="port:s" cy="3" r="2" fill="none"/></defs><style> .component {
    fill: white; stroke: black; stroke-width: 2;
} .conduit {
    fill: none; stroke: black; stroke-width: 2;
} text {
    text-anchor: middle; dominant-baseline: middle;
} </style><g><g transform="translate(6 6)"><g transform="translate(5 56)"><g
transform="translate(36 24)"><use href="#port:f_init"
y="20.0"><title>input</title></use><use href="#port:f_init"
y="30.0"><title>input2</title></use><use href="#port:o_f" x="150"
y="25.0"><title>output</title></use><rect class="component" id="micro1" x="1" y="1"
width="148" height="48" rx="5"/><text x="75.0" y="25.0">micro1</text></g><g
transform="translate(238 24)"><use href="#port:f_init"
y="15.0"><title>input1</title></use><use href="#port:f_init"
y="25.0"><title>input2</title></use><use href="#port:f_init"
y="35.0"><title>input3</title></use><use href="#port:o_f" x="150"
y="25.0"><title>output</title></use><rect class="component" id="micro2" x="1" y="1"
width="148" height="48" rx="5"/><text x="75.0" y="25.0">micro2</text></g><g><path
class="conduit" d="M 5.0 0 V 6 H 217.0 V 49.0 H 232"/><path class="conduit" d="M 25.0 0
V 12 H 207.0 V 59.0 H 232"/><path class="conduit" d="M 5.0 0 V 44.0 H 30"/><path
class="conduit" d="M 15.0 0 V 54.0 H 30"/><path class="conduit" d="M 192 49.0 h 5.0 V
39.0 H 232"/><path class="conduit" d="M 192 49.0 h 5.0 V 18 H 409.0 V 0"/><path
class="conduit" d="M 394 49.0 h 5.0 V 0"/></g></g><use href="#port:o_i" x="10.0"
y="50"><title>output</title></use><use href="#port:o_i" x="20.0"
y="50"><title>output3</title></use><use href="#port:o_i" x="30.0"
y="50"><title>output2</title></use><use href="#port:s" x="414.0"
y="50"><title>input1</title></use><use href="#port:s" x="404.0"
y="50"><title>input2</title></use><rect class="component" id="macro" x="1" y="1"
width="422" height="48" rx="5"/><text x="212.0"
y="25.0">macro</text></g><g/></g></svg>"""


class YmmslGraphViewer(pn.viewable.Viewer):
    def __init__(self, data_manager: DataManager) -> None:
        super().__init__()
        self.svg = pn.pane.SVG(PlacholderGraph(), align="center")
        self.card = pn.Card(
            self.svg,
            title="Simulation graph (placeholder)",
            sizing_mode="stretch_width",
            margin=CARD_MARGIN,
        )
        self.data_manager = data_manager
        self.data_manager.param.watch(self.update, "data_updated")

        # TODO: create simulation graph from configuration.ymmsl
        ...

    def update(self, event):
        pass

    def __panel__(self):
        return self.card
