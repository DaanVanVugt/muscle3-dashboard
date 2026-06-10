"""m3dash command line interface.

``m3dash serve``: run the server on a per-user unix socket.
``m3dash ensure``: start the server if it is not already running (cheap
and silent; suitable for ~/.bashrc).
``m3dash ls``: list discovered runs on the terminal.
"""

import getpass
import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import click

# In the home dir so that one ssh_config line works for every user:
#   LocalForward 127.0.0.1:4333 /home/ITER/%r/.m3dash.sock
# (%r expands to the remote username). Unix sockets are host-local even
# on a shared filesystem: pin one login node and run m3dash there.
DEFAULT_SOCKET = Path("~/.m3dash.sock").expanduser()


def default_tcp_port() -> int:
    """Deterministic per-user loopback port, for sites where sshd
    prohibits unix-socket forwarding (AllowStreamLocalForwarding no).

    Outside the Linux ephemeral range (32768+) to avoid collisions with
    short-lived connections. NB unlike the 0600 socket, a loopback TCP
    port is connectable by other users on the same node.
    """
    return 20000 + os.getuid() % 10000
DEFAULT_LOCAL_PORT = 4333
STATE_DIR = Path("~/.local/state/m3dash").expanduser()


def _socket_alive(socket_path: Path) -> bool:
    if not socket_path.exists():
        return False
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        probe.connect(str(socket_path))
        return True
    except OSError:
        return False
    finally:
        probe.close()


@click.group()
def main() -> None:
    """Find MUSCLE3 runs and serve their dashboards over one endpoint."""


@main.command()
@click.option(
    "--socket",
    "socket_path",
    type=click.Path(path_type=Path),
    default=DEFAULT_SOCKET,
    show_default=True,
    help="Unix socket to serve on.",
)
@click.option(
    "--local-port",
    default=DEFAULT_LOCAL_PORT,
    show_default=True,
    help="Local port the SSH forward uses; sets the allowed websocket "
    "origins (localhost:<port>).",
)
@click.option(
    "--tcp",
    "tcp_port",
    type=int,
    default=None,
    help="Also serve on this TCP port (see --address). By default a "
    "per-user port (20000 + uid % 10000) is used; --no-tcp disables.",
)
@click.option(
    "--no-tcp",
    is_flag=True,
    help="Serve on the unix socket only.",
)
@click.option(
    "--address",
    default="127.0.0.1",
    show_default=True,
    help="Address to bind the TCP port to. 0.0.0.0 makes the server "
    "reachable from other hosts AND other users on shared nodes; the "
    "websocket origin check only stops browsers, not curl.",
)
@click.option(
    "--no-socket",
    is_flag=True,
    help="Do not serve on the unix socket (TCP only; requires --tcp).",
)
@click.option(
    "--ws-origin",
    "ws_origins",
    multiple=True,
    help="Extra allowed websocket origin, e.g. mynode.iter.org:5006 "
    "(repeatable).",
)
@click.option(
    "--root",
    "roots",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    multiple=True,
    help="Add a run root for filesystem discovery (repeatable). "
    "Defaults to roots from ~/.config/m3dash/roots, or else $HOME.",
)
def serve(
    socket_path: Path,
    local_port: int,
    tcp_port: int | None,
    no_tcp: bool,
    address: str,
    no_socket: bool,
    ws_origins: tuple[str],
    roots: tuple[Path],
) -> None:
    """Run the m3dash server (blocking)."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if no_tcp and tcp_port is not None:
        raise click.UsageError("--no-tcp conflicts with --tcp")
    if not no_tcp and tcp_port is None:
        tcp_port = default_tcp_port()
    if no_socket and tcp_port is None:
        raise click.UsageError("--no-socket requires TCP (drop --no-tcp)")
    from muscle3_dashboard.m3dash import app

    all_roots = app.load_roots()
    for root in roots:
        root = root.expanduser().resolve()
        if root not in all_roots:
            all_roots.append(root)
    app.save_roots(all_roots)
    origins = [f"localhost:{local_port}", f"127.0.0.1:{local_port}"]
    origins += list(ws_origins)
    if tcp_port and address != "127.0.0.1":
        # Allow browsing this host directly by name
        host = socket.gethostname()
        origins += [f"{host}:{tcp_port}", f"{socket.getfqdn()}:{tcp_port}"]
    app.serve(
        None if no_socket else socket_path,
        all_roots,
        origins,
        tcp_port,
        address,
    )


@main.command()
@click.option(
    "--socket",
    "socket_path",
    type=click.Path(path_type=Path),
    default=DEFAULT_SOCKET,
    show_default=True,
)
@click.option("--timeout", default=15.0, show_default=True)
def ensure(socket_path: Path, timeout: float) -> None:
    """Start the server in the background unless it is already running.

    Idempotent and quiet, so it can be called from ~/.bashrc::

        command -v m3dash >/dev/null && m3dash ensure
    """
    if _socket_alive(socket_path):
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    logfile = (STATE_DIR / "serve.log").open("ab")
    subprocess.Popen(
        [sys.executable, "-m", "muscle3_dashboard.m3dash.cli",
         "serve", "--socket", str(socket_path)],
        stdout=logfile,
        stderr=logfile,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env=os.environ,
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _socket_alive(socket_path):
            click.echo(f"m3dash started on {socket_path}", err=True)
            return
        time.sleep(0.5)
    raise click.ClickException(
        f"m3dash did not come up within {timeout}s, "
        f"see {STATE_DIR / 'serve.log'}"
    )


@main.command()
@click.option("--host", default=None, help="HostName for the ssh config block.")
@click.option("--local-port", default=DEFAULT_LOCAL_PORT, show_default=True)
def sshline(host: str | None, local_port: int) -> None:
    """Print the ssh config block for reaching this m3dash instance.

    Run this on the login node where m3dash runs; paste the output into
    ~/.ssh/config on your own machine.
    """
    hostname = host or socket.getfqdn()
    click.echo(
        f"Host m3dash\n"
        f"    HostName {hostname}\n"
        f"    LocalForward 127.0.0.1:{local_port} "
        f"127.0.0.1:{default_tcp_port()}\n"
        f"    ExitOnForwardFailure no\n"
        f"# Where sshd allows unix-socket forwarding "
        f"(AllowStreamLocalForwarding), prefer:\n"
        f"#   LocalForward 127.0.0.1:{local_port} {DEFAULT_SOCKET}"
    )


@main.command("ls")
@click.option("--json", "as_json", is_flag=True, help="Output JSON.")
@click.option(
    "--root",
    "roots",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    multiple=True,
    help="Run root to scan (repeatable); defaults to configured roots.",
)
def ls(as_json: bool, roots: tuple[Path]) -> None:
    """List discovered MUSCLE3 runs."""
    from muscle3_dashboard.m3dash.app import load_roots
    from muscle3_dashboard.m3dash.discovery import discover_runs, runs_to_json

    runs = discover_runs([r.expanduser() for r in roots] or load_roots())
    if as_json:
        click.echo(runs_to_json(runs))
        return
    for run in runs:
        ref = str(run.job_id or run.pid or "")
        updated = str(run.last_updated or "")[:16]
        click.echo(
            f"{run.status.value:9} {updated:16} {ref:>8}  {run.run_dir}"
        )


if __name__ == "__main__":
    main()
