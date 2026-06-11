import html
from pathlib import Path

# Copies the path to the clipboard and briefly shows "✓ copied" in place,
# keeping the element at its original width so the layout doesn't jump.
# navigator.clipboard only exists in secure contexts (https / localhost);
# fall back to a hidden textarea + execCommand for plain-http access.
_COPY_JS = (
    "const el=this;"
    "const done=()=>{const t=el.textContent;const w=el.offsetWidth;"
    "el.style.display='inline-block';el.style.width=w+'px';"
    "el.style.textAlign='center';el.textContent='\\u2713 copied';"
    "setTimeout(()=>{el.textContent=t;el.style.display='';"
    "el.style.width='';el.style.textAlign='';},1200);};"
    "const p=el.dataset.path;"
    "if(navigator.clipboard){navigator.clipboard.writeText(p).then(done);}"
    "else{const a=document.createElement('textarea');a.value=p;"
    "a.style.position='fixed';a.style.opacity='0';"
    "document.body.appendChild(a);a.select();"
    "document.execCommand('copy');a.remove();done();}"
)


def path_html(path: Path, *, monospace: bool = False) -> str:
    """Render a path as HTML that copies itself to the clipboard on click,
    with a file:// link to open it when the browser runs on the machine
    that holds the files."""
    resolved = html.escape(str(path.resolve()))
    font = "font-family:monospace;" if monospace else ""
    return (
        f'<span title="click to copy" onclick="{_COPY_JS}" '
        f'data-path="{resolved}" '
        f'style="cursor:pointer;{font}opacity:0.85">{resolved}</span> '
        f'<a href="file://{resolved}" title="open in file manager" '
        f'target="_blank" style="text-decoration:none">&#x2197;</a>'
    )
