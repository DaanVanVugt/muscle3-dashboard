"""Optional logdy-based log explorer, surfaced through the m3dash proxy.

`logdy <https://logdy.dev>`_ is a small web UI for browsing/searching/
tailing logs. When its binary is available, m3dash starts one
``logdy follow`` per run over that run's log files (on the m3dash host,
reading the shared filesystem) and the run page embeds its web UI in an
iframe, reached through the same per-target subdomain proxy as actor
UIs.

It is entirely optional: if no logdy binary is found, the run page keeps
the built-in xterm log terminals unchanged. Point at a binary with the
``M3DASH_LOGDY`` environment variable, or put ``logdy`` on PATH; extra
flags can be passed via ``M3DASH_LOGDY_ARGS``.
"""

import atexit
import logging
import os
import shlex
import shutil
import socket
import subprocess
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

#: run_dir -> (Popen, port), so we start at most one logdy per run.
_servers: dict[Path, tuple[subprocess.Popen, int]] = {}
_lock = threading.Lock()


@atexit.register
def _terminate_all() -> None:
    # logdy is detached (start_new_session), so without this every
    # m3dash restart would leave orphaned logdy servers on the node.
    with _lock:
        for proc, _port in _servers.values():
            if proc.poll() is None:
                proc.terminate()


def find_logdy() -> str | None:
    """Path to the logdy binary, or None if not available."""
    return os.environ.get("M3DASH_LOGDY") or shutil.which("logdy")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _log_files(run_dir: Path) -> list[str]:
    files = [run_dir / "muscle3_manager.log"]
    files += sorted(run_dir.glob("instances/*/stdout.txt"))
    files += sorted(run_dir.glob("instances/*/stderr.txt"))
    return [str(f) for f in files if f.exists()]


def launch(run_dir: Path) -> int | None:
    """Start (once) a logdy server over the run's logs; return its port.

    Returns None if logdy is unavailable, there are no logs, or it fails
    to start — callers then fall back to the built-in terminals.
    """
    binary = find_logdy()
    if not binary:
        return None
    key = run_dir.resolve()
    with _lock:
        existing = _servers.get(key)
        if existing and existing[0].poll() is None:
            return existing[1]
        files = _log_files(run_dir)
        if not files:
            return None
        port = _free_port()
        argv = [
            binary,
            "follow",
            *files,
            "--port",
            str(port),
            "--ui-ip",
            "127.0.0.1",
            "--no-updates",
            "--no-analytics",
            *shlex.split(os.environ.get("M3DASH_LOGDY_ARGS", "")),
        ]
        try:
            proc = subprocess.Popen(
                argv,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            logger.exception("Could not start logdy")
            return None
        _servers[key] = (proc, port)
        logger.info(
            "logdy serving %d log file(s) for %s on 127.0.0.1:%d",
            len(files),
            key.name,
            port,
        )
        return port
