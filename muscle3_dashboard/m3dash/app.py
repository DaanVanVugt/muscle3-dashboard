"""m3dash Panel application.

Serves two Panel apps:

* ``/``: a landing page listing the user's MUSCLE3 runs, discovered via
  SLURM, local muscle_manager processes and a filesystem scan of
  configurable run roots (see :mod:`muscle3_dashboard.m3dash.discovery`).
* ``/run?dir=<path>``: the muscle3-dashboard for one run directory.

The server listens on a per-user unix socket (``~/.m3dash.sock``, mode
0600, which on a shared login node restricts access to the owning user)
and is reached through an SSH forward, e.g. in ``~/.ssh/config``::

    LocalForward 127.0.0.1:4333 /home/ITER/%r/.m3dash.sock

(``%r`` expands to the remote username, so one line serves every user.)

It additionally reverse-proxies each running run's harvested actor UIs
under per-target subdomains (``<token>.localhost``); see
:mod:`muscle3_dashboard.m3dash.proxy`.
"""

import html
import logging
import socket
import threading
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

import panel as pn

from muscle3_dashboard.m3dash.discovery import (
    MANAGER_LOG,
    Run,
    RunStatus,
    discover_runs,
)

logger = logging.getLogger(__name__)

ROOTS_FILE = Path("~/.config/m3dash/roots").expanduser()
RESCAN_INTERVAL_SECONDS = 60
VIEW_REFRESH_MILLISECONDS = 5000
#: Local port the browser reaches m3dash on; used to build proxy links.
LOCAL_PORT = 4333

_STATUS_COLORS = {
    RunStatus.RUNNING: "#1976d2",
    RunStatus.FINISHED: "#388e3c",
    RunStatus.FAILED: "#d32f2f",
    RunStatus.UNKNOWN: "#757575",
}


def load_roots() -> list[Path]:
    """Load run roots from the config file, defaulting to the home dir."""
    try:
        lines = ROOTS_FILE.read_text().splitlines()
        roots = [Path(li).expanduser() for li in lines if li.strip()]
    except OSError:
        roots = []
    return roots or [Path.home()]


def save_roots(roots: list[Path]) -> None:
    ROOTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ROOTS_FILE.write_text("".join(f"{root}\n" for root in roots))


class RunIndex:
    """Shared, periodically refreshed cache of discovered runs."""

    def __init__(self, roots: list[Path]) -> None:
        self.roots = roots
        self.runs: list[Run] = []
        self.last_scan: datetime | None = None
        self.scan_seconds: float | None = None
        self.scanning = False
        self._lock = threading.Lock()
        self._wakeup = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._scan_loop, name="m3dash-scanner", daemon=True
        )
        self._thread.start()

    def request_rescan(self) -> None:
        self._wakeup.set()

    def add_root(self, root: Path) -> None:
        with self._lock:
            if root not in self.roots:
                self.roots.append(root)
                save_roots(self.roots)
        self.request_rescan()

    def _scan_loop(self) -> None:
        while True:
            self.scanning = True
            started = time.monotonic()
            try:
                runs = discover_runs(list(self.roots))
                with self._lock:
                    self.runs = runs
            except Exception:
                logger.exception("Run discovery failed")
            finally:
                self.scanning = False
                self.scan_seconds = time.monotonic() - started
                self.last_scan = datetime.now()
            self._wakeup.wait(timeout=RESCAN_INTERVAL_SECONDS)
            self._wakeup.clear()


_index: RunIndex | None = None


def _age(timestamp: datetime | None) -> str:
    if timestamp is None:
        return "?"
    seconds = (datetime.now() - timestamp).total_seconds()
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds / 60)}m"
    if seconds < 86400:
        return f"{int(seconds / 3600)}h"
    return f"{int(seconds / 86400)}d"


def _runs_table_html(runs: list[Run]) -> str:
    """Render the run list as an HTML table with links to /run."""
    rows = []
    for run in runs:
        query = urllib.parse.urlencode({"dir": str(run.run_dir)})
        color = _STATUS_COLORS[run.status]
        via = ", ".join(run.sources)
        if run.job_id:
            ref = f"job {run.job_id}"
        elif run.pid:
            ref = f"pid {run.pid}"
        else:
            ref = ""
        uis = []
        for u in run.web_urls:
            if u["resolved"]:
                uis.append(
                    f'<a href="{html.escape(u["reachable_url"])}" '
                    f'target="_blank">{html.escape(u["instance"])}</a>'
                )
            else:
                uis.append(
                    f'<span title="node unresolved: {html.escape(u["original"])}">'
                    f'{html.escape(u["instance"])} (?)</span>'
                )
        rows.append(
            f"<tr>"
            f'<td><a href="run?{query}" target="_blank">'
            f"<b>{html.escape(run.name)}</b></a></td>"
            f'<td><span style="color:{color}">{run.status.value}</span></td>'
            f"<td>{_age(run.last_updated)}</td>"
            f"<td>{html.escape(via)}</td>"
            f"<td>{html.escape(ref)}</td>"
            f"<td>{', '.join(uis)}</td>"
            f'<td style="color:#888;font-size:0.85em">'
            f"{html.escape(str(run.run_dir))}</td>"
            f"</tr>"
        )
    if not rows:
        rows = ['<tr><td colspan="7"><i>No runs found yet.</i></td></tr>']
    return (
        '<table style="border-spacing:12px 4px">'
        "<tr><th>Run</th><th>Status</th><th>Updated</th>"
        "<th>Found via</th><th>Job/PID</th><th>Web UIs</th>"
        "<th>Run directory</th></tr>"
        + "".join(rows)
        + "</table>"
    )


def index_app():
    """Landing page: run list, scan status, and run-root management."""
    assert _index is not None
    table = pn.pane.HTML(_runs_table_html(_index.runs), sizing_mode="stretch_width")
    status = pn.pane.Markdown()
    roots_md = pn.pane.Markdown()
    root_input = pn.widgets.TextInput(
        placeholder="Add run root, e.g. /work/imas/shared", width=400
    )
    add_button = pn.widgets.Button(name="Add root", button_type="primary")
    rescan_button = pn.widgets.Button(name="Rescan now")

    def refresh(*_events) -> None:
        table.object = _runs_table_html(_index.runs)
        roots_md.object = "Scanned roots: " + ", ".join(
            f"`{root}`" for root in _index.roots
        )
        if _index.scanning:
            status.object = "*Scanning…*"
        elif _index.last_scan is not None:
            status.object = (
                f"{len(_index.runs)} runs; last scan {_age(_index.last_scan)} "
                f"ago took {_index.scan_seconds:.1f}s"
            )
        else:
            status.object = "*First scan pending…*"

    def add_root(_event) -> None:
        if root_input.value:
            _index.add_root(Path(root_input.value).expanduser())
            root_input.value = ""
        refresh()

    add_button.on_click(add_root)
    rescan_button.on_click(lambda _event: _index.request_rescan())
    # Defer the periodic callback to session load: adding it during the
    # app-factory call makes Bokeh replay a SessionCallbackAdded event on
    # the first document unhold, raising "a callback ... has already been
    # added with this ID" in a real browser session.
    if pn.state.curdoc:
        pn.state.onload(
            lambda: pn.state.add_periodic_callback(
                refresh, period=VIEW_REFRESH_MILLISECONDS
            )
        )
    else:
        pn.state.add_periodic_callback(refresh, period=VIEW_REFRESH_MILLISECONDS)
    refresh()

    return pn.template.VanillaTemplate(
        title="m3dash | MUSCLE3 runs",
        main=[
            pn.Column(
                pn.Row(status, rescan_button),
                table,
                pn.Row(roots_md, root_input, add_button),
            )
        ],
    )


def run_app():
    """Dashboard page for a single run, selected with ?dir=<path>."""
    raw = pn.state.session_args.get("dir", [b""])[0].decode()
    run_dir = Path(raw).expanduser()
    if not raw or not (run_dir / MANAGER_LOG).is_file():
        # NB: a bare pane returned from an app function may render an
        # empty document; wrap in a template like the other pages.
        return pn.template.VanillaTemplate(
            title="m3dash | error",
            main=[
                pn.pane.Markdown(
                    f"Not a MUSCLE3 run directory (no `{MANAGER_LOG}`): "
                    f"`{raw or '(missing ?dir= parameter)'}`"
                )
            ],
        )
    # Local import: pulls in the full dashboard and its dependencies
    from muscle3_dashboard.dashboard import Dashboard

    dash = Dashboard(run_dir.resolve())
    card = _web_uis_card(run_dir.resolve())
    if card is not None:
        dash.template.main.insert(0, card)
    return dash


def _web_uis_card(run_dir: Path):
    """A card listing each instance's harvested UIs as proxy links."""
    from muscle3_dashboard.m3dash.harvest import harvest_run
    from muscle3_dashboard.m3dash.proxy import subdomain_host

    found = harvest_run(run_dir, fallback_node=socket.gethostname())
    if not found:
        return None
    by_instance: dict[str, list[str]] = {}
    for u in found:
        if u.resolved and u.node and u.port:
            sub = subdomain_host(u.node, u.port, f"localhost:{LOCAL_PORT}")
            link = f"http://{sub}{u.path or '/'}"
            label = f'<a href="{html.escape(link)}" target="_blank">{html.escape(u.original)}</a>'
        else:
            label = (
                f'{html.escape(u.original)} '
                f'<span style="color:#999">(node unresolved)</span>'
            )
        by_instance.setdefault(u.instance, []).append(label)
    items = "".join(
        f"<li><b>{html.escape(inst)}</b>: {' , '.join(links)}</li>"
        for inst, links in sorted(by_instance.items())
    )
    return pn.Card(
        pn.pane.HTML(f"<ul style='margin:0'>{items}</ul>"),
        title="Web UIs (proxied)",
        collapsed=False,
        sizing_mode="stretch_width",
    )


def _claim_socket(socket_path: Path) -> None:
    """Remove a stale socket, or fail if a live server owns it."""
    if not socket_path.exists():
        return
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        probe.connect(str(socket_path))
    except OSError:
        socket_path.unlink()  # stale
    else:
        raise RuntimeError(f"m3dash is already serving on {socket_path}")
    finally:
        probe.close()


def serve(
    socket_path: Path | None,
    roots: list[Path],
    websocket_origins: list[str],
    tcp_port: int | None = None,
    address: str = "127.0.0.1",
    local_port: int = 4333,
    open_browser: bool = False,
) -> None:
    """Run the m3dash server (blocking).

    Args:
        socket_path: Unix socket to serve on (mode 0600), or None.
        roots: Initial run roots for filesystem discovery.
        websocket_origins: Allowed websocket origins, e.g. localhost:4333
            for the conventional SSH LocalForward.
        tcp_port: Optional TCP port to also serve on (mainly for
            debugging; its loopback origins are added automatically).
        address: Address to bind the TCP port to.
        local_port: Port the browser reaches m3dash on; used to build
            ``<token>.localhost:<local_port>`` proxy links.
        open_browser: Open a browser at the TCP URL once serving (for a
            desktop session running on the node itself). Needs tcp_port.
    """
    global _index, LOCAL_PORT
    _index = RunIndex(roots)
    _index.start()
    LOCAL_PORT = local_port

    origins = list(websocket_origins)
    if tcp_port:
        origins += [f"localhost:{tcp_port}", f"127.0.0.1:{tcp_port}"]
    server = pn.serve(
        {"/": index_app, "/run": run_app},
        address=address,
        port=tcp_port or 0,
        websocket_origin=origins,
        show=False,
        start=False,
        threaded=False,
    )
    # Mount the per-target subdomain reverse-proxy on the same tornado
    # app; host-routing means these only catch <token>.localhost traffic
    # and leave the dashboard's own routes untouched.
    from muscle3_dashboard.m3dash.proxy import PROXY_HOST_PATTERN, proxy_handlers

    server._tornado.add_handlers(PROXY_HOST_PATTERN, proxy_handlers())
    if socket_path is not None:
        from tornado.netutil import bind_unix_socket

        _claim_socket(socket_path)
        socket_path.parent.mkdir(parents=True, exist_ok=True)
        server._http.add_sockets([bind_unix_socket(str(socket_path), mode=0o600)])
        logger.info("Serving on unix socket %s", socket_path)
    if tcp_port:
        # Always print a clickable loopback URL (the usable browse URL),
        # even when bound on 0.0.0.0.
        logger.info("Serving at http://localhost:%d/  (bound on %s)",
                    tcp_port, address)
    if open_browser and tcp_port:
        import webbrowser

        url = f"http://localhost:{tcp_port}/"
        server.io_loop.add_callback(lambda: webbrowser.open(url))
    try:
        server.start()
        server.io_loop.start()
    finally:
        if socket_path is not None:
            socket_path.unlink(missing_ok=True)
