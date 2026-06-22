import base64
import contextlib
import html
import logging
from collections.abc import Callable

import panel as pn
import param

from muscle3_dashboard.constants import CARD_MARGIN
from muscle3_dashboard.data_manager import DataManager
from muscle3_dashboard.instances import base_name
from muscle3_dashboard.loganalyzer.manager import ComponentStatus

logger = logging.getLogger(__name__)

# Component box fill per status bucket (light tints; black labels stay readable).
# muscle3 has no distinct "running" status -- REGISTERED is the active state.
# "crashed" is the likely culprit (a real non-zero exit); "killed" is collateral
# (SIGKILL -9 / generic crash when another component failed first).
_STATUS_FILL = {
    "not_started": "#eeeeee",  # grey: not started / starting up
    "running": "#bbdefb",  # blue: registered / running
    "finished": "#c8e6c9",  # green: finished / deregistered
    "killed": "#ffcdd2",  # pale red: collateral crash
    "crashed": "#ef9a9a",  # strong red: responsible / likely culprit
}
# (stroke colour, width) overlaid on crash buckets so the culprit stands out most.
_CRASH_STROKE = {"crashed": ("#b71c1c", 5), "killed": ("#e57373", 2)}
_RUNNING_STATUSES = {
    ComponentStatus.PLANNED,
    ComponentStatus.INSTANTIATING,
    ComponentStatus.REGISTERED,
}
_FINISHED_STATUSES = {ComponentStatus.DEREGISTERED, ComponentStatus.FINISHED}
# When a multiplicity's instances differ, show the most attention-worthy state.
_BUCKET_PRIORITY = {
    "crashed": 4,
    "killed": 3,
    "running": 2,
    "not_started": 1,
    "finished": 0,
}

# Fill intensity is a *recent activity* proxy: log bytes written since the last
# refresh (Panel's poll interval) as a fraction of the file's total so far -- so
# a currently-busy component glows and an idle/finished one fades. Floored so the
# status hue stays faintly visible for quiet components.
_EFFORT_FLOOR = 0.2


def _blend_white(hex_color: str, t: float) -> str:
    """Blend ``hex_color`` toward white; t=1 keeps it, t=0 is white."""
    t = max(0.0, min(1.0, t))
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    r, g, b = (round(255 + (c - 255) * t) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"

try:
    from ymmsl2svg import ymmsl2svg
    from ymmsl2svg.settings import settings as ymmsl2svg_settings
except ImportError:  # optional "graph" extra not installed
    ymmsl2svg = None
    ymmsl2svg_settings = None


class _ClickableSVG(pn.reactive.ReactiveHTML):
    """Render an SVG string and report the clicked component.

    The SVG is passed **base64-encoded** (``svg_b64``): Panel runs every string
    param through an HTML sanitizer that strips ``<svg>``/``<path>``/``<style>``
    outright, so a raw SVG param renders as an empty box. base64 has no tags to
    strip, so it passes through; the script decodes it (UTF-8 safe, for the ``→``
    in conduit labels) and injects it as innerHTML.

    ymmsl2svg gives each component box ``id="component-<name>"``. A click on a
    box sets ``component`` to ``<name>`` (label text has ``pointer-events:none``
    so clicks fall through to the box); ``component`` is reset to "" after each
    click so the same box can be clicked again.
    """

    svg_b64 = param.String(default="")
    component = param.String(default="")

    _template = (
        '<div id="wrap" style="position:relative;width:100%">'
        '<div id="graph" onclick="${script(\'click\')}" '
        'onmousemove="${script(\'hover\')}" onmouseleave="${script(\'leave\')}" '
        'style="width:100%;overflow:auto"></div>'
        '<div id="tip" style="position:fixed;display:none;pointer-events:none;'
        "background:#222;color:#fff;padding:2px 6px;border-radius:3px;"
        'font:12px sans-serif;z-index:1000;white-space:nowrap"></div>'
        "</div>"
    )
    # Decode the base64 SVG into the div, then move every <title> into a
    # data-tip attribute and drop it: native SVG <title> tooltips have a fixed
    # ~1s browser delay, so we render our own instant tooltip from data-tip.
    _draw = (
        "graph.innerHTML = data.svg_b64 ? new TextDecoder().decode("
        "Uint8Array.from(atob(data.svg_b64), c => c.charCodeAt(0))) : '';"
        "graph.querySelectorAll('title').forEach(t => {"
        "  if (t.parentNode) { t.parentNode.setAttribute('data-tip', t.textContent); }"
        "  t.remove();"
        "});"
    )
    _scripts = {
        "render": _draw,
        "svg_b64": _draw,
        "click": (
            "const el = state.event.target.closest('[id^=\"component-\"]');"
            "if (el) { data.component = el.id.slice('component-'.length); }"
        ),
        "hover": (
            "const e = state.event;"
            "const el = e.target.closest('[data-tip]');"
            "if (el) {"
            "  tip.textContent = el.getAttribute('data-tip');"
            "  tip.style.left = (e.clientX + 12) + 'px';"
            "  tip.style.top = (e.clientY + 12) + 'px';"
            "  tip.style.display = 'block';"
            "} else { tip.style.display = 'none'; }"
        ),
        "leave": "tip.style.display = 'none'",
    }


class YmmslGraphViewer(pn.viewable.Viewer):
    """Render the run's coupling diagram from its ``configuration.ymmsl``.

    Visualization needs the optional ``ymmsl2svg`` dependency
    (``pip install muscle3-dashboard[graph]``); without it, a missing config,
    or an unvisualizable model, a short message is shown instead. Component
    boxes are coloured by status (crashed also outlined); clicking a component
    invokes ``on_select`` with its name (used to show that component's logs).
    """

    def __init__(
        self,
        data_manager: DataManager,
        on_select: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self.data_manager = data_manager
        self.on_select = on_select
        self._base_svg: str | None = None  # rendered graph, before styling
        self._rendered = False
        self._styled: dict[str, tuple[str, str]] = {}  # name -> (status, fill)
        # name -> total log bytes at the previous refresh, for the per-tick delta.
        self._prev_bytes: dict[str, int] = {}

        self.graph = _ClickableSVG()
        self.graph.param.watch(self._on_click, "component")
        # Small, click-to-expand "approximate layout" warning (<details>).
        self.note = pn.pane.HTML(visible=False, sizing_mode="stretch_width")
        self.message = pn.pane.Markdown(visible=False)  # error / no-graph text
        self.card = pn.Card(
            self.note,
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

        ymmsl2svg_settings.debug = False
        note_html = ""
        try:
            ymmsl2svg_settings.check_timelines = True
            svg = ymmsl2svg(config)
        except Exception as strict_error:
            # Best-effort: draw without timeline verification for models the
            # strict checker rejects (e.g. time-scale bridges / accumulators).
            try:
                ymmsl2svg_settings.check_timelines = False
                svg = ymmsl2svg(config)
                note_html = self._approximate_note(strict_error)
            except Exception:
                logger.warning("Could not visualize %s: %s", config, strict_error)
                self._show_message(
                    f"Could not visualize `{config.name}`: {strict_error}"
                )
                return
            finally:
                ymmsl2svg_settings.check_timelines = True

        self._base_svg = str(svg)
        self._rendered = True
        self.graph.visible = True
        self.message.visible = False
        self.note.object = note_html
        self.note.visible = bool(note_html)
        self._apply_styling()

    @staticmethod
    def _approximate_note(error: Exception) -> str:
        """Small, click-to-expand notice carrying the full strict error."""
        details = html.escape(str(error))
        return (
            '<details style="font-size:0.8em;opacity:0.8;margin:2px 4px">'
            '<summary style="cursor:pointer">&#9888; Timelines could not be '
            "verified — layout is approximate (click for details)</summary>"
            '<pre style="white-space:pre-wrap;font-size:0.95em;margin:4px 0">'
            f"{details}</pre></details>"
        )

    def _bucket(self, component) -> str:
        """Map a component's status / exit code to a colour bucket."""
        crash = component.crash_kind  # "culprit" | "killed" | None (structured)
        if crash == "culprit":
            return "crashed"  # likely root cause: ranked highest, strong red
        if crash == "killed":
            return "killed"  # collateral SIGKILL / generic crash: pale red
        if component.status in _RUNNING_STATUSES:
            return "running"
        if component.status in _FINISHED_STATUSES:
            return "finished"
        return "not_started"

    def _component_statuses(self) -> dict[str, str]:
        """Base component name -> status bucket for colouring.

        Strips a multiplicity suffix (``worker[0]`` -> ``worker``) so instances
        map to the single box ymmsl2svg draws, keeping the highest-priority
        bucket when a multiplicity's instances differ.
        """
        best: dict[str, str] = {}
        components = self.data_manager.manager_log_analyzer.components
        for name, component in components.items():
            base = base_name(name)
            bucket = self._bucket(component)
            current = best.get(base)
            if current is None or _BUCKET_PRIORITY[bucket] > _BUCKET_PRIORITY[current]:
                best[base] = bucket
        return best

    def _component_styles(self) -> dict[str, tuple[str, str]]:
        """Base component name -> (status bucket, fill colour).

        Fill is the status hue blended toward white by recent log activity:
        bytes written since the previous refresh as a fraction of the total so
        far. Advances the per-component byte baseline as a side effect.
        """
        statuses = self._component_statuses()
        sizes: dict[str, int] = {}
        for analyzers in (
            self.data_manager.stdout_log_analyzers,
            self.data_manager.stderr_log_analyzers,
        ):
            for instance, analyzer in analyzers.items():
                base = base_name(instance)
                with contextlib.suppress(OSError):
                    sizes[base] = sizes.get(base, 0) + analyzer.path.stat().st_size

        styles: dict[str, tuple[str, str]] = {}
        for name in set(statuses) | set(sizes):
            bucket = statuses.get(name, "not_started")
            total = sizes.get(name, 0)
            recent = max(0, total - self._prev_bytes.get(name, total))
            intensity = max(_EFFORT_FLOOR, recent / total if total else 0.0)
            styles[name] = (bucket, _blend_white(_STATUS_FILL[bucket], intensity))
        self._prev_bytes = sizes
        return styles

    def _apply_styling(self, styles: dict[str, tuple[str, str]] | None = None) -> None:
        """Inject styling (clickable boxes + status/activity colours) into the SVG.

        Crashed/killed components also get a red outline. Attribute selectors
        (not #id) so component names with '.'/'[' don't break the CSS.
        """
        if self._base_svg is None:
            return
        if styles is None:
            styles = self._component_styles()
        css = "text{pointer-events:none}[id^='component-']{cursor:pointer}"
        for name, (bucket, fill) in sorted(styles.items()):
            rule = f'[id="component-{name}"]{{fill:{fill}'
            stroke = _CRASH_STROKE.get(bucket)
            if stroke:
                rule += f";stroke:{stroke[0]};stroke-width:{stroke[1]}"
            css += rule + "}"
        styled = self._base_svg.replace(
            "</svg>", f"<style>{css}</style></svg>", 1
        )
        self.graph.svg_b64 = base64.b64encode(styled.encode()).decode()
        self._styled = styles

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
        self.note.visible = False
        self.message.object = text
        self.message.visible = True

    def update(self, event) -> None:
        if not self._rendered:
            self.render()
            return
        # The configuration is static, but statuses and recent activity evolve;
        # sample once per tick and restyle when the styling changes.
        styles = self._component_styles()
        if styles != self._styled:
            self._apply_styling(styles)

    def __panel__(self):
        return self.card
