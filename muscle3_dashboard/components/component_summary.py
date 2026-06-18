import html
import logging
import re
from pathlib import Path

import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN
from muscle3_dashboard.data_manager import DataManager

logger = logging.getLogger(__name__)

try:
    import ymmsl
    from ymmsl.v0_2 import Configuration
except ImportError:  # optional "graph" extra not installed
    ymmsl = None

#: Largest file we'll load into the read-only viewer.
_MAX_FILE_BYTES = 512 * 1024

#: Editor language (Ace mode) by file extension.
_LANGUAGES = {
    ".py": "python", ".xml": "xml", ".sh": "sh", ".bash": "sh",
    ".yaml": "yaml", ".yml": "yaml", ".ymmsl": "yaml", ".json": "json",
    ".c": "c_cpp", ".h": "c_cpp", ".cpp": "c_cpp", ".hpp": "c_cpp",
    ".f": "fortran", ".f90": "fortran", ".md": "markdown",
    ".css": "css", ".js": "javascript", ".toml": "toml",
}
#: Absolute-path-looking tokens.
_PATH_RE = re.compile(r"/[^\s'\"<>():,]+")


class ComponentSummaryViewer(pn.viewable.Viewer):
    """Show a clicked component: a ymmsl2svg-style port block, its program /
    settings / description, and a read-only viewer for any files it references.
    """

    def __init__(self, data_manager: DataManager) -> None:
        super().__init__()
        self.data_manager = data_manager
        self._config = None
        self._loaded = False

        self.block = pn.pane.SVG(None, visible=False)
        self.details = pn.pane.HTML(
            "<i>Click a component in the graph for details.</i>",
            sizing_mode="stretch_width",
        )
        self.files = pn.widgets.Select(
            name="Open file (read-only)", options={}, visible=False, width=480
        )
        self.files.param.watch(self._load_file, "value")
        self.editor = pn.widgets.CodeEditor(
            value="", language="text", readonly=True, visible=False,
            sizing_mode="stretch_width", height=360,
        )
        self.card = pn.Card(
            pn.Column(self.block, self.details, self.files, self.editor),
            title="Component",
            margin=CARD_MARGIN,
            sizing_mode="stretch_width",
            collapsible=True,
        )

    # -- config -----------------------------------------------------------
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
        cfg = self._config_obj()
        comp = None
        if cfg is not None:
            comp = {
                str(c.name): c for c in cfg.root_model().components.values()
            }.get(component_name)
        if comp is None:
            self.block.visible = False
            self.files.visible = False
            self.editor.visible = False
            self.details.object = (
                f"<b>{html.escape(component_name)}</b><br>"
                "<i>Not in the configuration.</i>"
            )
            return

        program = cfg.programs.get(comp.implementation)
        self.block.object = _component_block_svg(comp, component_name)
        self.block.visible = True
        self.details.object = _details_html(comp, program, cfg, component_name)

        paths = _detect_files(comp, program, cfg, component_name)
        self.files.options = {Path(p).name: p for p in paths}
        self.files.value = None
        self.files.visible = bool(paths)
        self.editor.visible = False

    def _load_file(self, event) -> None:
        path = event.new
        if not path:
            self.editor.visible = False
            return
        try:
            data = Path(path).read_bytes()[:_MAX_FILE_BYTES]
            text = data.decode("utf-8", errors="replace")
        except OSError as e:
            text = f"# Could not read {path}: {e}"
        self.editor.language = _LANGUAGES.get(Path(path).suffix.lower(), "text")
        self.editor.value = text
        self.editor.visible = True

    def __panel__(self):
        return self.card


# -- rendering helpers ----------------------------------------------------
def _display_name(comp, name: str) -> str:
    mult = list(comp.multiplicity or [])
    return f"{name} [{','.join(map(str, mult))}]" if mult else name


def _component_block_svg(comp, name: str) -> str:
    """A ymmsl2svg-style component box: F_INIT open diamonds on the left, O_F
    closed diamonds on the right, O_I closed / S open circles on the bottom,
    each labelled with its port name."""
    ports = {"F_INIT": [], "O_F": [], "O_I": [], "S": []}
    for port in comp.ports.values():
        ports.setdefault(port.operator.name, []).append(str(port.name))
    left, right = ports["F_INIT"], ports["O_F"]
    bottom = [(n, "O_I") for n in ports["O_I"]] + [(n, "S") for n in ports["S"]]
    title = _display_name(comp, name)

    row, char = 20, 6.5
    lw = max((len(p) for p in left), default=0) * char
    rw = max((len(p) for p in right), default=0) * char
    box_w = max(170, len(title) * 8 + 24, lw + rw + 48, len(bottom) * 64 + 20)
    rows = max(len(left), len(right), 1)
    box_h = max(54, 30 + rows * row)
    pad = 10
    bottom_h = 22 if bottom else 0
    width, height = box_w + 2 * pad, box_h + 2 * pad + bottom_h
    x0, y0 = pad, pad

    el = [
        f'<rect x="{x0}" y="{y0}" width="{box_w}" height="{box_h}" rx="6" '
        'fill="#fff" stroke="#000" stroke-width="2"/>',
        f'<text x="{x0 + box_w / 2:.0f}" y="{y0 + 16}" text-anchor="middle" '
        f'font-family="sans-serif" font-size="12" font-weight="bold">'
        f"{html.escape(title)}</text>",
    ]

    def diamond(cx, cy, fill):
        return (
            f'<path d="M {cx - 5} {cy} L {cx} {cy - 5} L {cx + 5} {cy} '
            f'L {cx} {cy + 5} Z" fill="{fill}" stroke="#000" stroke-width="1.5"/>'
        )

    for i, p in enumerate(left):
        cy = y0 + 34 + i * row
        el.append(diamond(x0, cy, "#fff"))
        el.append(
            f'<text x="{x0 + 9}" y="{cy + 4}" font-family="sans-serif" '
            f'font-size="11">{html.escape(p)}</text>'
        )
    for i, p in enumerate(right):
        cy = y0 + 34 + i * row
        el.append(diamond(x0 + box_w, cy, "#000"))
        el.append(
            f'<text x="{x0 + box_w - 9}" y="{cy + 4}" text-anchor="end" '
            f'font-family="sans-serif" font-size="11">{html.escape(p)}</text>'
        )
    for j, (p, op) in enumerate(bottom):
        cx = x0 + 24 + j * 64
        cy = y0 + box_h
        fill = "#000" if op == "O_I" else "#fff"
        el.append(
            f'<circle cx="{cx}" cy="{cy}" r="4" fill="{fill}" '
            'stroke="#000" stroke-width="1.5"/>'
        )
        el.append(
            f'<text x="{cx}" y="{cy + 15}" text-anchor="middle" '
            f'font-family="sans-serif" font-size="10">{html.escape(p)}</text>'
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
        f'height="{height:.0f}">{"".join(el)}</svg>'
    )


def _details_html(comp, program, cfg, name: str) -> str:
    sections = []
    description = (comp.description or "").strip()
    if description:
        sections.append(f"<p>{html.escape(description)}</p>")
    if program is not None:
        sections.append(_program_html(program))
    prefix = name + "."
    settings = {
        str(key)[len(prefix) :]: value
        for key, value in cfg.settings.items()
        if str(key).startswith(prefix)
    }
    if settings:
        body = "\n".join(f"  {k}: {v!r}," for k, v in sorted(settings.items()))
        sections.append(
            "<b>Settings</b><pre style='margin:2px 0;white-space:pre-wrap'>"
            f"{{\n{html.escape(body)}\n}}</pre>"
        )
    return "".join(sections)


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
    script = getattr(program, "script", None)
    if script:
        rows.append(
            "<div><b>Script:</b><pre style='margin:2px 0;max-height:12em;"
            "overflow:auto;background:#f5f5f5;padding:4px'>"
            f"{html.escape(str(script))}</pre></div>"
        )
    return "".join(rows)


def _detect_files(comp, program, cfg, name: str) -> list[str]:
    """Existing files referenced by the component's program and settings."""
    blobs: list[str] = []
    if program is not None:
        blobs.append(str(getattr(program, "executable", "") or ""))
        blobs.extend(str(a) for a in getattr(program, "args", []) or [])
        blobs.append(str(getattr(program, "virtual_env", "") or ""))
        blobs.append(str(getattr(program, "script", "") or ""))
    prefix = name + "."
    for key, value in cfg.settings.items():
        if str(key).startswith(prefix):
            blobs.append(str(value))
    found: dict[str, None] = {}
    for blob in blobs:
        for match in _PATH_RE.findall(blob):
            if match not in found and Path(match).is_file():
                found[match] = None
    return list(found)
