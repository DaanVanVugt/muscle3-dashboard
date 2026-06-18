import html
import logging

import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN
from muscle3_dashboard.data_manager import DataManager

logger = logging.getLogger(__name__)

try:
    import ymmsl
    from ymmsl.v0_2 import Configuration
except ImportError:  # optional "graph" extra not installed
    ymmsl = None

#: Port operators grouped as inputs (receive) and outputs (send).
_INPUT_OPS = ("F_INIT", "S")
_OUTPUT_OPS = ("O_I", "O_F")


class ComponentSummaryViewer(pn.viewable.Viewer):
    """Show a clicked component's configuration.

    Ports (in/out), the program's command / env / modules / script, the
    component's settings (as a dict), and its description -- read from the run's
    ``configuration.ymmsl``.
    """

    def __init__(self, data_manager: DataManager) -> None:
        super().__init__()
        self.data_manager = data_manager
        self._config = None
        self._loaded = False
        self.body = pn.pane.HTML(
            "<i>Click a component in the graph for details.</i>",
            sizing_mode="stretch_width",
        )
        self.card = pn.Card(
            self.body,
            title="Component",
            margin=CARD_MARGIN,
            sizing_mode="stretch_width",
            collapsible=True,
        )

    def _config_obj(self):
        if not self._loaded:
            self._loaded = True
            config = self.data_manager.run_folder / "configuration.ymmsl"
            if ymmsl is not None and config.is_file():
                try:
                    self._config = ymmsl.load_as(Configuration, config)
                except Exception as e:
                    logger.warning("Could not load %s: %s", config, e)
        return self._config

    def show(self, component_name: str) -> None:
        """Render the summary for the given (base) component name."""
        self.body.object = self._summary_html(component_name)

    def _summary_html(self, name: str) -> str:
        cfg = self._config_obj()
        if cfg is None:
            return (
                f"<b>{html.escape(name)}</b><br>"
                "<i>No configuration.ymmsl available.</i>"
            )
        components = {str(c.name): c for c in cfg.root_model().components.values()}
        comp = components.get(name)
        if comp is None:
            return f"<b>{html.escape(name)}</b><br><i>Not in the configuration.</i>"

        title = html.escape(name)
        mult = list(comp.multiplicity or [])
        if mult:
            title += " [" + ",".join(str(d) for d in mult) + "]"
        sections = [f'<div style="font-size:1.1em"><b>{title}</b></div>']

        description = (comp.description or "").strip()
        if description:
            sections.append(f"<p>{html.escape(description)}</p>")

        inputs, outputs = [], []
        for port in comp.ports.values():
            (inputs if port.operator.name in _INPUT_OPS else outputs).append(
                f"{html.escape(str(port.name))} "
                f'<span style="opacity:0.6">({port.operator.name})</span>'
            )
        sections.append(self._ports_html("Inputs", inputs))
        sections.append(self._ports_html("Outputs", outputs))

        program = cfg.programs.get(comp.implementation)
        if program is not None:
            sections.append(self._program_html(program))

        prefix = name + "."
        settings = {
            str(key)[len(prefix) :]: value
            for key, value in cfg.settings.items()
            if str(key).startswith(prefix)
        }
        if settings:
            body = "\n".join(
                f"  {k}: {v!r}," for k, v in sorted(settings.items())
            )
            sections.append(
                "<b>Settings</b>"
                f'<pre style="margin:2px 0;white-space:pre-wrap">{{\n'
                f"{html.escape(body)}\n}}</pre>"
            )
        return "".join(sections)

    @staticmethod
    def _ports_html(label: str, ports: list[str]) -> str:
        items = ", ".join(ports) if ports else "<i>none</i>"
        return f"<div><b>{label}:</b> {items}</div>"

    @staticmethod
    def _program_html(program) -> str:
        rows = []
        executable = getattr(program, "executable", None)
        args = list(getattr(program, "args", []) or [])
        if executable is not None:
            command = html.escape(" ".join([str(executable), *args]))
            rows.append(f"<div><b>Command:</b> <code>{command}</code></div>")
        venv = getattr(program, "virtual_env", None)
        if venv:
            rows.append(
                f"<div><b>venv:</b> <code>{html.escape(str(venv))}</code></div>"
            )
        modules = list(getattr(program, "modules", []) or [])
        if modules:
            rows.append(
                "<div><b>Modules:</b> "
                f"<code>{html.escape(', '.join(map(str, modules)))}</code></div>"
            )
        env = dict(getattr(program, "env", {}) or {})
        if env:
            envtext = html.escape("\n".join(f"  {k}={v}" for k, v in env.items()))
            rows.append(
                f"<div><b>Env:</b><pre style='margin:2px 0'>{envtext}</pre></div>"
            )
        script = getattr(program, "script", None)
        if script:
            rows.append(
                "<div><b>Script:</b>"
                "<pre style='margin:2px 0;max-height:12em;overflow:auto;"
                "background:#f5f5f5;padding:4px'>"
                f"{html.escape(str(script))}</pre></div>"
            )
        return "".join(rows)

    def __panel__(self):
        return self.card
