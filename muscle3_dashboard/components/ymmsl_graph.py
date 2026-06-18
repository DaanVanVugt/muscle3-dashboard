import logging
import re
from collections.abc import Callable

import panel as pn
import param

from muscle3_dashboard.constants import CARD_MARGIN
from muscle3_dashboard.data_manager import DataManager

logger = logging.getLogger(__name__)

try:
    from ymmsl2svg import ymmsl2svg
    from ymmsl2svg.settings import settings as ymmsl2svg_settings
except ImportError:  # optional "graph" extra not installed
    ymmsl2svg = None
    ymmsl2svg_settings = None


class _ClickableSVG(pn.reactive.ReactiveHTML):
    """Render an SVG string and report the clicked component.

    ymmsl2svg gives each component box ``id="component-<name>"``. A click
    anywhere on a box sets ``component`` to ``<name>`` (label text has
    ``pointer-events: none`` so clicks fall through to the box). ``component``
    is reset to "" after each click so the same box can be clicked again.
    """

    svg = param.String(default="")
    component = param.String(default="")

    _template = (
        '<div id="graph" onclick="${script(\'click\')}" '
        'style="width:100%;overflow:auto"></div>'
    )
    _scripts = {
        "render": "graph.innerHTML = data.svg",
        "svg": "graph.innerHTML = data.svg",
        "click": (
            "const el = event.target.closest('[id^=\"component-\"]');"
            "if (el) { data.component = el.id.slice('component-'.length); }"
        ),
    }


class YmmslGraphViewer(pn.viewable.Viewer):
    """Render the run's coupling diagram from its ``configuration.ymmsl``.

    Visualization needs the optional ``ymmsl2svg`` dependency
    (``pip install muscle3-dashboard[graph]``); without it, a missing config,
    or an unvisualizable model, a short message is shown instead. Crashed
    components are outlined; clicking a component invokes ``on_select`` with
    its name (used to show that component's logs).
    """

    def __init__(
        self,
        data_manager: DataManager,
        on_select: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self.data_manager = data_manager
        self.on_select = on_select
        self._base_svg: str | None = None  # rendered graph, before highlight
        self._rendered = False
        self._highlighted: frozenset[str] = frozenset()

        self.graph = _ClickableSVG()
        self.graph.param.watch(self._on_click, "component")
        self.message = pn.pane.Markdown(visible=False)
        self.card = pn.Card(
            self.graph,
            self.message,
            title="Simulation graph",
            sizing_mode="stretch_width",
            margin=CARD_MARGIN,
        )
        self.data_manager.param.watch(self.update, "data_updated")
        self.render()

    def render(self) -> None:
        """Render configuration.ymmsl into the graph, with fallbacks."""
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
            ymmsl2svg_settings.debug = False
            svg = ymmsl2svg(config)
        except Exception as e:
            logger.warning("Could not visualize %s: %s", config, e)
            self._show_message(f"Could not visualize `{config.name}`: {e}")
            return

        self._base_svg = str(svg)
        self._rendered = True
        self.graph.visible = True
        self.message.visible = False
        self._apply_highlight()

    def _crashed_components(self) -> frozenset[str]:
        """Component names with a non-zero exit / crash, for highlighting.

        Strips a multiplicity suffix (``worker[0]`` -> ``worker``) so it matches
        the component box ymmsl2svg draws for the whole multiplicity.
        """
        names = set()
        components = self.data_manager.manager_log_analyzer.components
        for name, component in components.items():
            message = component.exit_code_message
            if message and message != "0":
                names.add(re.sub(r"\[.*\]$", "", name))
        return frozenset(names)

    def _apply_highlight(self) -> None:
        """Inject styling (clickable boxes + crash outline) into the SVG."""
        if self._base_svg is None:
            return
        crashed = self._crashed_components()
        # Travels with the SVG: clicks hit the box not the label, boxes show a
        # pointer cursor, and crashed boxes get a red outline. Attribute
        # selectors (not #id) so component names with '.'/'[' don't break CSS.
        css = "text{pointer-events:none}[id^='component-']{cursor:pointer}"
        for name in sorted(crashed):
            css += f'[id="component-{name}"]{{stroke:#c62828;stroke-width:4}}'
        self.graph.svg = self._base_svg.replace(
            "</svg>", f"<style>{css}</style></svg>", 1
        )
        self._highlighted = crashed

    def _on_click(self, event) -> None:
        component = event.new
        if not component:
            return
        # Allow re-clicking the same component (reset before dispatch).
        self.graph.component = ""
        if self.on_select is not None:
            self.on_select(component)

    def _show_message(self, text: str) -> None:
        self.graph.visible = False
        self.message.object = text
        self.message.visible = True

    def update(self, event) -> None:
        if not self._rendered:
            self.render()
            return
        # The configuration is static, but crash state evolves; restyle when it
        # changes.
        if self._crashed_components() != self._highlighted:
            self._apply_highlight()

    def __panel__(self):
        return self.card
