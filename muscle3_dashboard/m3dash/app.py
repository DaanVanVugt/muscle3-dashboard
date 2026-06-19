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
"""

import html
import logging
import statistics
import threading
import time
import urllib.parse
from collections import deque
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
# Incremental discovery (cached dir listings + log status, parallel stat) makes
# rescans cheap after the first, so they can run often.
RESCAN_INTERVAL_SECONDS = 5
VIEW_REFRESH_MILLISECONDS = 5000


def load_roots() -> list[Path]:
    """Load run roots from the config file, defaulting to the home dir.

    The file is the single place roots are configured: one path per
    line; the scanner re-reads it on every rescan, so edits apply
    without a restart.
    """
    try:
        lines = ROOTS_FILE.read_text().splitlines()
        roots = [Path(li).expanduser() for li in lines if li.strip()]
    except OSError:
        roots = []
    return roots or [Path.home()]


class RunIndex:
    """Shared, periodically refreshed cache of discovered runs."""

    def __init__(self) -> None:
        self.roots: list[Path] = load_roots()
        self.runs: list[Run] = []
        self.last_scan: datetime | None = None
        self.scan_seconds: float | None = None
        self.scanning = False
        self._durations: deque[float] = deque(maxlen=20)
        self._lock = threading.Lock()
        self._wakeup = threading.Event()
        self._thread: threading.Thread | None = None

    def scan_lead(self) -> float:
        """Upper estimate of a scan's duration (mean + 2 stddev), in seconds,
        used to start a rescan so it finishes just before the next refresh."""
        d = list(self._durations)
        if not d:
            return 1.0
        if len(d) < 2:
            return d[0]
        return statistics.fmean(d) + 2 * statistics.pstdev(d)

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._scan_loop, name="m3dash-scanner", daemon=True
        )
        self._thread.start()

    def request_rescan(self) -> None:
        self._wakeup.set()

    def _scan_loop(self) -> None:
        while True:
            self.scanning = True
            started = time.monotonic()
            try:
                roots = load_roots()
                runs = discover_runs(roots)
                with self._lock:
                    self.roots = roots
                    self.runs = runs
            except Exception:
                logger.exception("Run discovery failed")
            finally:
                self.scanning = False
                self.scan_seconds = time.monotonic() - started
                self._durations.append(self.scan_seconds)
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


# Status dot colours: blue = running, green = finished OK, red = failed,
# grey = not started / unknown.
_DOT_COLORS = {
    RunStatus.NOT_STARTED: "#bdbdbd",
    RunStatus.RUNNING: "#1976d2",
    RunStatus.FINISHED: "#2e7d32",
    RunStatus.FAILED: "#d32f2f",
    RunStatus.UNKNOWN: "#9e9e9e",
}


def _job_ref(run: Run) -> str:
    if run.job_id:
        name = run.job_name
        return f"{name} (job {run.job_id})" if name else f"job {run.job_id}"
    if run.pid:
        return f"pid {run.pid}"
    return ""


def _common_prefix_len(a: str, b: str) -> int:
    """Length of the longest path prefix a and b share up to a '/' boundary."""
    cut = 0
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            break
        if a[i] == "/":
            cut = i + 1
    return cut


def _common_dir(paths: list[str]) -> str:
    """Directory prefix shared by every path (no trailing slash)."""
    if not paths:
        return ""
    prefix = paths[0]
    for path in paths[1:]:
        prefix = prefix[: _common_prefix_len(prefix, path)]
    common = prefix.rstrip("/")
    # If the common part is itself a whole run path (e.g. a single run), back
    # off to its parent so the run still shows a name.
    if common and any(path == common for path in paths):
        common = common.rsplit("/", 1)[0]
    return common


def _updated_html(timestamp: datetime | None) -> str:
    if timestamp is None:
        return "?"
    return (
        f'{timestamp.strftime("%Y-%m-%d %H:%M:%S")} '
        f'<span style="opacity:0.55">({_age(timestamp)})</span>'
    )


def _runs_table_html(runs: list[Run]) -> str:
    """Render the run list as an HTML table keyed on the run directory.

    Runs are sorted newest-first; the directory prefix common to all runs is
    dropped (shown once above the table) so each row's clickable path shows only
    its distinguishing tail and opens /run. A status dot precedes the path.
    Per-component web UIs live on the run page, not here.
    """
    if not runs:
        return (
            '<table style="border-spacing:12px 4px">'
            '<tr><td><i>No runs found yet.</i></td></tr></table>'
        )
    common = _common_dir([str(run.run_dir) for run in runs])
    epoch = datetime.fromtimestamp(0)
    rows = []
    previous = ""
    for run in sorted(runs, key=lambda r: r.last_updated or epoch, reverse=True):
        path = str(run.run_dir)
        rel = path[len(common) :].lstrip("/") if common else path
        # Blank out the path components shared with the row above (replacing
        # them with spaces) so only the distinguishing tail shows, aligned.
        cut = _common_prefix_len(previous, rel)
        previous = rel
        indent, unique = " " * cut, html.escape(rel[cut:])
        dot = _DOT_COLORS[run.status]
        # A not-yet-started (queued) run has no manager log to open yet, so show
        # its path as plain text rather than a /run link.
        if run.status is RunStatus.NOT_STARTED:
            label = unique
        else:
            query = urllib.parse.urlencode({"dir": path})
            label = f'<a href="run?{query}" target="_blank">{unique}</a>'
        rows.append(
            "<tr>"
            '<td style="font-family:monospace;white-space:pre">'
            f'<span style="color:{dot}" title="{html.escape(run.status.value)}">'
            "●</span> "
            f"{indent}{label}"
            "</td>"
            f'<td style="white-space:nowrap">{_updated_html(run.last_updated)}</td>'
            f"<td>{html.escape(_job_ref(run))}</td>"
            "</tr>"
        )
    caption = (
        f'<div style="opacity:0.7;margin-bottom:6px">in '
        f"<code>{html.escape(common)}/</code></div>"
        if common
        else ""
    )
    return (
        caption
        + '<table style="border-spacing:12px 4px">'
        "<tr><th>Run directory</th><th>Updated</th><th>Job/PID</th></tr>"
        + "".join(rows)
        + "</table>"
    )


def _scan_summary_html(index) -> str:
    if index.last_scan is not None:
        when = f"last scan {_age(index.last_scan)} ago ({index.scan_seconds:.2f}s)"
    else:
        when = "first scan pending"
    roots = ", ".join(f"<code>{html.escape(str(r))}</code>" for r in index.roots)
    tip = html.escape(f"edit {ROOTS_FILE} (one path per line) and it applies next scan")
    return (
        f'<span style="opacity:0.7" title="{tip}">{when} · roots: {roots}</span>'
    )


def index_app():
    """Landing page: run list, with the scan summary + roots at the bottom.

    A rescan is scheduled to start ``mean + 2*stddev`` of the recent scan
    durations before the next refresh, so it finishes just in time for the
    refresh to display fresh results.
    """
    assert _index is not None
    table = pn.pane.HTML(_runs_table_html(_index.runs), sizing_mode="stretch_width")
    summary = pn.pane.HTML(sizing_mode="stretch_width")

    def refresh(*_events) -> None:
        table.object = _runs_table_html(_index.runs)
        summary.object = _scan_summary_html(_index)
        doc = pn.state.curdoc
        if doc is not None:
            lead_ms = min(VIEW_REFRESH_MILLISECONDS, int(_index.scan_lead() * 1000))
            doc.add_timeout_callback(
                _index.request_rescan, VIEW_REFRESH_MILLISECONDS - lead_ms
            )

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
        main=[pn.Column(table, summary)],
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

    return Dashboard(run_dir.resolve())


def _claim_socket(socket_path: Path) -> None:
    """Remove a stale socket, or fail if a live server owns it."""
    from muscle3_dashboard.m3dash.cli import _socket_alive

    if _socket_alive(socket_path):
        raise RuntimeError(f"m3dash is already serving on {socket_path}")
    socket_path.unlink(missing_ok=True)


def serve(
    socket_path: Path | None,
    websocket_origins: list[str],
    tcp_port: int | None = None,
    address: str = "127.0.0.1",
    open_browser: bool = False,
) -> None:
    """Run the m3dash server (blocking).

    Run roots come from the config file (see :func:`load_roots`),
    re-read on every rescan.

    Args:
        socket_path: Unix socket to serve on (mode 0600), or None.
        websocket_origins: Allowed websocket origins, e.g. localhost:4333
            for the conventional SSH LocalForward.
        tcp_port: Optional TCP port to also serve on (mainly for
            debugging; its loopback origins are added automatically).
        address: Address to bind the TCP port to.
        open_browser: Open a browser at the TCP URL once serving (for a
            desktop session running on the node itself). Needs tcp_port.
    """
    global _index
    _index = RunIndex()
    _index.start()

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
    if socket_path is not None:
        from tornado.netutil import bind_unix_socket

        _claim_socket(socket_path)
        socket_path.parent.mkdir(parents=True, exist_ok=True)
        server._http.add_sockets([bind_unix_socket(str(socket_path), mode=0o600)])
        logger.info("Serving on unix socket %s", socket_path)
    if tcp_port:
        # Always print a clickable loopback URL (the usable browse URL),
        # even when bound on 0.0.0.0.
        logger.info("Serving at http://localhost:%d/  (bound on %s)", tcp_port, address)
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
