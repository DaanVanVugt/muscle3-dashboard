import base64
import html
import logging
import re
from pathlib import Path

import panel as pn
import param

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


class _ClickableHTML(pn.reactive.ReactiveHTML):
    """HTML that reports the data-path of a clicked element.

    The HTML is passed base64-encoded so Panel's sanitizer (which strips the
    data-path attributes we need) leaves it intact; clicking an element with a
    data-path sets ``clicked`` to that path.
    """

    html_b64 = param.String(default="")
    clicked = param.String(default="")

    _template = (
        '<div id="content" onclick="${script(\'click\')}" '
        'style="width:100%"></div>'
    )
    _draw = (
        "content.innerHTML = data.html_b64 ? new TextDecoder().decode("
        "Uint8Array.from(atob(data.html_b64), c => c.charCodeAt(0))) : ''"
    )
    _scripts = {
        "render": _draw,
        "html_b64": _draw,
        "click": (
            "const el = state.event.target.closest('[data-path]');"
            "if (el) { data.clicked = el.getAttribute('data-path'); }"
        ),
    }


class ComponentSummaryViewer(pn.viewable.Viewer):
    """Show a clicked component: a ymmsl2svg-style port block, its program /
    settings / description (with referenced text files as inline links), and a
    read-only viewer that opens a file when its link is clicked.
    """

    def __init__(self, data_manager: DataManager) -> None:
        super().__init__()
        self.data_manager = data_manager
        self._config = None
        self._loaded = False
        self._text_files: set[str] = set()

        self.block = pn.pane.SVG(None, visible=False)
        self.details = _ClickableHTML(
            html_b64=_b64("<i>Click a component in the graph for details.</i>"),
            sizing_mode="stretch_width",
        )
        self.details.param.watch(self._on_path_click, "clicked")
        self.editor = pn.widgets.CodeEditor(
            value="", language="text", readonly=True, visible=False,
            sizing_mode="stretch_width", height=360,
        )
        self.card = pn.Card(
            pn.Column(self.block, self.details, self.editor),
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
        cfg = self._config_obj()
        comp = None
        if cfg is not None:
            comp = {
                str(c.name): c for c in cfg.root_model().components.values()
            }.get(component_name)
        self.editor.visible = False
        if comp is None:
            self.block.visible = False
            self.details.html_b64 = _b64(
                f"<b>{html.escape(component_name)}</b><br>"
                "<i>Not in the configuration.</i>"
            )
            return

        program = cfg.programs.get(comp.implementation)
        svg, width, height = _component_block_svg(comp, component_name)
        self.block.object = svg
        self.block.width = max(1, round(width / 2))  # render 2x smaller in page
        self.block.height = max(1, round(height / 2))
        self.block.visible = True

        self._text_files = set(_detect_files(comp, program, cfg, component_name))
        self.details.html_b64 = _b64(
            _details_html(comp, program, cfg, component_name, self._text_files)
        )

    def _on_path_click(self, event) -> None:
        path = event.new
        self.details.clicked = ""  # reset so the same link can be clicked again
        if path and path in self._text_files:
            self._open(path)

    def _open(self, path: str) -> None:
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


def _b64(markup: str) -> str:
    return base64.b64encode(markup.encode()).decode()


# -- block rendering ------------------------------------------------------
_FONT, _TITLE_FONT = 6.0, 7.0  # px
_CHAR = _FONT * 0.6  # rough glyph width
_ROW = 9.0  # vertical spacing of left/right ports
_DH, _CR = 3.0, 2.5  # diamond half-width, circle radius


def _display_name(comp, name: str) -> str:
    mult = list(comp.multiplicity or [])
    return f"{name} [{','.join(map(str, mult))}]" if mult else name


def _component_block_svg(comp, name: str) -> tuple[str, float, float]:
    """A compact ymmsl2svg-style component box, returned with its (w, h).

    F_INIT open diamonds on the left, O_F closed diamonds on the right, O_I
    closed / S open circles on the bottom. Bottom labels stay horizontal but
    alternate between two layers so adjacent ones don't overlap; the box is
    sized from label widths so nothing collides.
    """
    ports = {"F_INIT": [], "O_F": [], "O_I": [], "S": []}
    for port in comp.ports.values():
        ports.setdefault(port.operator.name, []).append(str(port.name))
    left, right = ports["F_INIT"], ports["O_F"]
    bottom = [(n, "O_I") for n in ports["O_I"]] + [(n, "S") for n in ports["S"]]
    title = _display_name(comp, name)

    lw = max((len(p) for p in left), default=0) * _CHAR
    rw = max((len(p) for p in right), default=0) * _CHAR
    # Bottom: horizontal labels in 2 layers, so same-layer (2 apart) must clear
    # one label width -> column spacing >= half a label.
    half = max((len(n) for n, _ in bottom), default=0) * _CHAR / 2
    col = max(14.0, half + 4)
    box_w = max(
        70, len(title) * _TITLE_FONT * 0.6 + 12, lw + rw + 24, len(bottom) * col
    )
    rows = max(len(left), len(right), 1)
    box_h = max(26, 15 + rows * _ROW)
    pad = 5
    side = half if bottom else 0  # room for end labels to overhang
    bottom_h = _CR + 4 + 2 * (_FONT + 1) if bottom else 0
    width = box_w + 2 * pad + 2 * side
    height = box_h + 2 * pad + bottom_h
    x0, y0 = pad + side, pad

    el = [
        f'<rect x="{x0:.0f}" y="{y0}" width="{box_w:.0f}" height="{box_h:.0f}" '
        'rx="4" fill="#fff" stroke="#000" stroke-width="1.5"/>',
        f'<text x="{x0 + box_w / 2:.0f}" y="{y0 + 10:.0f}" text-anchor="middle" '
        f'font-family="sans-serif" font-size="{_TITLE_FONT}" font-weight="bold">'
        f"{html.escape(title)}</text>",
    ]

    def diamond(cx, cy, fill):
        return (
            f'<path d="M {cx - _DH:.0f} {cy} L {cx:.0f} {cy - _DH} '
            f'L {cx + _DH:.0f} {cy} L {cx:.0f} {cy + _DH} Z" '
            f'fill="{fill}" stroke="#000" stroke-width="1"/>'
        )

    for i, p in enumerate(left):
        cy = y0 + 20 + i * _ROW
        el.append(diamond(x0, cy, "#fff"))
        el.append(
            f'<text x="{x0 + _DH + 3:.0f}" y="{cy + 2:.0f}" '
            f'font-family="sans-serif" font-size="{_FONT}">{html.escape(p)}</text>'
        )
    for i, p in enumerate(right):
        cy = y0 + 20 + i * _ROW
        el.append(diamond(x0 + box_w, cy, "#000"))
        el.append(
            f'<text x="{x0 + box_w - _DH - 3:.0f}" y="{cy + 2:.0f}" '
            f'text-anchor="end" font-family="sans-serif" font-size="{_FONT}">'
            f"{html.escape(p)}</text>"
        )
    for j, (p, op) in enumerate(bottom):
        cx = x0 + col * (j + 0.5)
        cy = y0 + box_h
        fill = "#000" if op == "O_I" else "#fff"
        el.append(
            f'<circle cx="{cx:.0f}" cy="{cy}" r="{_CR}" fill="{fill}" '
            'stroke="#000" stroke-width="1"/>'
        )
        ty = cy + _CR + 6 + (j % 2) * (_FONT + 1)  # two staggered layers
        el.append(
            f'<text x="{cx:.0f}" y="{ty:.0f}" text-anchor="middle" '
            f'font-family="sans-serif" font-size="{_FONT}">{html.escape(p)}</text>'
        )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
        f'height="{height:.0f}">{"".join(el)}</svg>'
    )
    return svg, width, height


# -- details rendering ----------------------------------------------------
def _linkify(escaped_text: str, paths: set[str]) -> str:
    """Turn detected text-file paths in already-escaped text into links."""
    for path in sorted(paths, key=len, reverse=True):
        esc = html.escape(path)
        if esc in escaped_text:
            escaped_text = escaped_text.replace(
                esc,
                f'<a data-path="{esc}" style="color:#1976d2;cursor:pointer;'
                f'text-decoration:underline">{esc}</a>',
            )
    return escaped_text


def _details_html(comp, program, cfg, name: str, text_files: set[str]) -> str:
    def link(raw: str) -> str:
        return _linkify(html.escape(raw), text_files)

    sections = []
    description = (comp.description or "").strip()
    if description:
        sections.append(f"<p>{html.escape(description)}</p>")
    if program is not None:
        rows = []
        executable = getattr(program, "executable", None)
        args = list(getattr(program, "args", []) or [])
        if executable is not None:
            command = " ".join([str(executable), *args])
            rows.append(f"<div><b>Command:</b> <code>{link(command)}</code></div>")
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
                f"{link(str(script))}</pre></div>"
            )
        sections.append("".join(rows))
    prefix = name + "."
    settings = {
        str(key)[len(prefix) :]: value
        for key, value in cfg.settings.items()
        if str(key).startswith(prefix)
    }
    if settings:
        lines = "\n".join(
            f"  {html.escape(k)}: {link(repr(v))}," for k, v in sorted(settings.items())
        )
        sections.append(
            "<b>Settings</b><pre style='margin:2px 0;white-space:pre-wrap'>"
            f"{{\n{lines}\n}}</pre>"
        )
    return "".join(sections)


# -- file detection -------------------------------------------------------
def _is_text_file(path: Path) -> bool:
    """Heuristic: a readable file with no NUL byte in its first 4 KiB."""
    try:
        with path.open("rb") as f:
            return b"\x00" not in f.read(4096)
    except OSError:
        return False


def _detect_files(comp, program, cfg, name: str) -> list[str]:
    """Existing *text* files referenced by the program and settings."""
    blobs: list[str] = []
    if program is not None:
        blobs.append(str(getattr(program, "executable", "") or ""))
        blobs.extend(str(a) for a in getattr(program, "args", []) or [])
        blobs.append(str(getattr(program, "script", "") or ""))
    prefix = name + "."
    for key, value in cfg.settings.items():
        if str(key).startswith(prefix):
            blobs.append(str(value))
    found: dict[str, None] = {}
    for blob in blobs:
        for match in _PATH_RE.findall(blob):
            if match not in found:
                p = Path(match)
                if p.is_file() and _is_text_file(p):
                    found[match] = None
    return list(found)
