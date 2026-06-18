import logging

import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN
from muscle3_dashboard.data_manager import DataManager

logger = logging.getLogger(__name__)

try:
    from ymmsl2svg import ymmsl2svg
except ImportError:  # optional "graph" extra not installed
    ymmsl2svg = None


class YmmslGraphViewer(pn.viewable.Viewer):
    """Render the run's coupling diagram from its ``configuration.ymmsl``.

    Visualization is provided by the optional ``ymmsl2svg`` dependency
    (``pip install muscle3-dashboard[graph]``). When it is unavailable, the
    configuration file is missing, or the model cannot be visualized, a short
    message is shown instead of the graph.
    """

    def __init__(self, data_manager: DataManager) -> None:
        super().__init__()
        self.data_manager = data_manager
        self._rendered = False
        self.svg = pn.pane.SVG(align="center", sizing_mode="stretch_width")
        self.message = pn.pane.Markdown(visible=False)
        self.card = pn.Card(
            self.svg,
            self.message,
            title="Simulation graph",
            sizing_mode="stretch_width",
            margin=CARD_MARGIN,
        )
        self.data_manager.param.watch(self.update, "data_updated")
        self.render()

    def render(self) -> None:
        """(Re)build the graph from configuration.ymmsl, with fallbacks."""
        if ymmsl2svg is None:
            self._show_message(
                "Install the optional `ymmsl2svg` dependency to see the "
                "simulation graph: `pip install muscle3-dashboard[graph]`."
            )
            return

        config = self.data_manager.run_folder / "configuration.ymmsl"
        if not config.is_file():
            self._show_message(f"No `configuration.ymmsl` in `{config.parent}`.")
            return

        try:
            svg = ymmsl2svg(config)
        except Exception as e:
            logger.warning("Could not visualize %s: %s", config, e)
            self._show_message(f"Could not visualize `{config.name}`: {e}")
            return

        self.svg.object = str(svg)
        self.svg.visible = True
        self.message.visible = False
        self._rendered = True

    def _show_message(self, text: str) -> None:
        self.svg.visible = False
        self.message.object = text
        self.message.visible = True

    def update(self, event) -> None:
        # The configuration is static for a run; render once successfully.
        if not self._rendered:
            self.render()

    def __panel__(self):
        return self.card
