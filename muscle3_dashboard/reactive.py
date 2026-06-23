"""Small, generic ReactiveHTML widgets shared across dashboard components.

These are not tied to any one card; they exist because Panel HTML-sanitizes
every ``ReactiveHTML`` string param, which strips the ``<svg>``/``data-*``/
``<style>`` markup these widgets rely on. The shared trick is to percent-encode
the markup (see :func:`encode_markup`) so the sanitizer has nothing to strip,
and decode it back in the browser with the native ``decodeURIComponent``.
"""

import urllib.parse

import panel as pn
import param


def encode_markup(markup: str) -> str:
    """Percent-encode markup so Panel's String sanitizer passes it through.

    Panel HTML-sanitizes every ReactiveHTML string param, which would strip the
    <svg>/data-path/<style> markup these widgets rely on. Percent-encoded text
    has no HTML characters left, so it survives; the JS decodes it back with the
    native (UTF-8 safe) ``decodeURIComponent``.
    """
    return urllib.parse.quote(markup)


class ClickableHTML(pn.reactive.ReactiveHTML):
    """HTML that reports the data-path of a clicked element.

    The HTML is percent-encoded (see :func:`encode_markup`) so Panel's sanitizer
    leaves the data-path attributes intact; clicking an element with a data-path
    sets ``clicked`` to that path.
    """

    html_enc = param.String(default="")
    clicked = param.String(default="")

    _template = (
        '<div id="content" onclick="${script(\'click\')}" style="width:100%"></div>'
    )
    _draw = "content.innerHTML = data.html_enc ? decodeURIComponent(data.html_enc) : ''"
    _scripts = {
        "render": _draw,
        "html_enc": _draw,
        "click": (
            "const el = state.event.target.closest('[data-path]');"
            "if (el) { data.clicked = el.getAttribute('data-path'); }"
        ),
    }


class CopyButton(pn.reactive.ReactiveHTML):
    """A small button that copies arbitrary text to the clipboard, with a brief
    "copied" confirmation.

    The text is percent-encoded (see :func:`encode_markup`) to survive Panel's
    string sanitizer with newlines/quotes intact. navigator.clipboard needs a
    secure context, which localhost (the SSH-forward / NoMachine access path)
    always is.
    """

    payload_enc = param.String(default="")
    label = param.String(default="⧉ copy contents")

    _template = (
        '<button id="b" onclick="${script(\'copy\')}" '
        'style="cursor:pointer;font-size:0.85em;padding:2px 8px;'
        'border:1px solid #ccc;border-radius:4px;background:#fafafa">'
        "{{ label }}</button>"
    )
    _scripts = {
        "copy": (
            "const t = data.payload_enc ? decodeURIComponent(data.payload_enc) : '';"
            "navigator.clipboard.writeText(t).then(() => {"
            "  const o = data.label;"
            "  b.textContent = '\\u2713 copied';"
            "  setTimeout(() => { b.textContent = o; }, 1200);"
            "});"
        ),
    }
