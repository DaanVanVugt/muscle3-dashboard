"""m3dash command line interface.

Server side (login node):
  ``m3dash serve``    run the server on a unix socket (+ a per-user TCP port).
  ``m3dash ensure``   start serve if not already running (for ~/.bashrc).
  ``m3dash ls``       list discovered runs on the terminal.
  ``m3dash urls``     show served-UI URLs harvested from a run's logs.
  ``m3dash sshline``  print the ssh config block to reach this instance.

Client side (your machine):
  ``m3dash connect``  listen on a local port and tunnel to a login node over
                      an ssh *exec* channel -- works even when ssh port and
                      unix-socket forwarding are both prohibited. The remote
                      end of the bridge is a python3 one-liner, so nothing
                      of m3dash is needed on the remote PATH.
"""

import logging
import os
import shlex
import socket
import subprocess
import sys
import threading
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
    help="Extra allowed websocket origin, e.g. mynode.iter.org:5006 (repeatable).",
)
@click.option(
    "--open-browser",
    is_flag=True,
    help="Open a browser at the TCP URL once serving (for a NoMachine / "
    "Open OnDemand desktop session on the node itself; needs TCP).",
)
def serve(
    socket_path: Path,
    local_port: int,
    tcp_port: int | None,
    no_tcp: bool,
    address: str,
    no_socket: bool,
    ws_origins: tuple[str, ...],
    open_browser: bool,
) -> None:
    """Run the m3dash server (blocking).

    Run roots for filesystem discovery are read from
    ~/.config/m3dash/roots (one path per line, default $HOME); edits are
    picked up at the next rescan, no restart needed.
    """
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if no_tcp and tcp_port is not None:
        raise click.UsageError("--no-tcp conflicts with --tcp")
    if not no_tcp and tcp_port is None:
        tcp_port = default_tcp_port()
    if no_socket and tcp_port is None:
        raise click.UsageError("--no-socket requires TCP (drop --no-tcp)")
    if open_browser and not tcp_port:
        raise click.UsageError("--open-browser needs a TCP port (drop --no-tcp)")
    from muscle3_dashboard.m3dash import app

    origins = [f"localhost:{local_port}", f"127.0.0.1:{local_port}"]
    origins += list(ws_origins)
    if tcp_port and address != "127.0.0.1":
        # Allow browsing this host directly by name
        host = socket.gethostname()
        origins += [f"{host}:{tcp_port}", f"{socket.getfqdn()}:{tcp_port}"]
    app.serve(
        None if no_socket else socket_path,
        origins,
        tcp_port=tcp_port,
        address=address,
        local_port=local_port,
        open_browser=open_browser,
    )


def _ensure_running(socket_path: Path, timeout: float = 15.0) -> bool:
    """Start a socket-only server in the background unless already up.

    Returns True once the socket is connectable, False on timeout.
    Writes only to the serve log, never stdout/stderr.
    """
    if _socket_alive(socket_path):
        return True
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    logfile = (STATE_DIR / "serve.log").open("ab")
    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "muscle3_dashboard.m3dash.cli",
            "serve",
            "--socket",
            str(socket_path),
            "--no-tcp",
        ],
        stdout=logfile,
        stderr=logfile,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env=os.environ,
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _socket_alive(socket_path):
            return True
        time.sleep(0.5)
    return False


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
    if _ensure_running(socket_path, timeout):
        return
    raise click.ClickException(
        f"m3dash did not come up within {timeout}s, see {STATE_DIR / 'serve.log'}"
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
        f"# Forwarding allowed -> add to ~/.ssh/config:\n"
        f"Host m3dash\n"
        f"    HostName {hostname}\n"
        f"    LocalForward 127.0.0.1:{local_port} "
        f"127.0.0.1:{default_tcp_port()}\n"
        f"    ExitOnForwardFailure no\n"
        f"#   ...where unix-socket forwarding is allowed, prefer:\n"
        f"#   LocalForward 127.0.0.1:{local_port} {DEFAULT_SOCKET}\n"
        f"#\n"
        f"# Forwarding prohibited (administratively prohibited: open\n"
        f"# failed) -> no ssh config needed, run on your machine:\n"
        f"#   m3dash connect {hostname} --local-port {local_port}"
    )


#: stdin/stdout <-> unix-socket bridge, run on the login node over an ssh
#: exec channel (``python3 -c <this> <socket>``). A python3 is always on
#: a cluster's default PATH, whereas ncat/socat are often absent or
#: restricted (mode 750 on ITER SDCC). The socket path is an argv and
#: expanded by python, so no remote shell quoting/expansion is involved.
_BRIDGE_PY = """\
import os,socket,sys,threading
s=socket.socket(socket.AF_UNIX)
s.connect(os.path.expanduser(sys.argv[1]))
def up():
    while d:=os.read(0,65536): s.sendall(d)
    try: s.shutdown(socket.SHUT_WR)
    except OSError: pass
threading.Thread(target=up,daemon=True).start()
while d:=s.recv(65536): os.write(1,d)
"""


def _shovel(src: socket.socket | int, dst: socket.socket | int) -> None:
    """Copy bytes from src to dst until EOF; src/dst are fds or sockets."""
    src_fd = src if isinstance(src, int) else src.fileno()
    dst_fd = dst if isinstance(dst, int) else dst.fileno()
    try:
        while True:
            chunk = os.read(src_fd, 65536)
            if not chunk:
                break
            os.write(dst_fd, chunk)
    except OSError:
        pass


@main.command()
@click.argument("ssh_host")
@click.option(
    "--local-port",
    default=DEFAULT_LOCAL_PORT,
    show_default=True,
    help="Local port to listen on.",
)
@click.option(
    "--remote-socket",
    default=str(DEFAULT_SOCKET).replace(str(Path.home()), "~", 1),
    show_default=True,
    help="Path of the m3dash socket on the login node.",
)
@click.option(
    "--ssh",
    "ssh_cmd",
    default="ssh",
    show_default=True,
    help="ssh command (add options here, e.g. 'ssh -J bastion').",
)
@click.option(
    "--remote-cmd",
    default=None,
    help="Remote command that connects to the socket and bridges "
    "stdin/stdout. Defaults to a python3 one-liner, which needs nothing "
    "but python3 on the remote PATH; where ncat is allowed, "
    "'ncat -U ~/.m3dash.sock' works too.",
)
def connect(
    ssh_host: str,
    local_port: int,
    remote_socket: str,
    ssh_cmd: str,
    remote_cmd: str | None,
) -> None:
    """Tunnel a local port to a login node's m3dash over ssh exec.

    Use this when ``ssh -L`` fails with "administratively prohibited"
    (both TCP and unix-socket forwarding disabled): exec channels are not
    forwarding, so they stay allowed. The remote end is a python3
    one-liner bridging stdin/stdout to the socket, so the server must
    already be running there -- start it from ``~/.bashrc``
    (``m3dash ensure``) or cron. Each browser
    connection spawns one ssh command; set up an ssh ControlMaster so
    those reuse a single authenticated connection instead of
    re-handshaking:

    \b
        Host <host>
            ControlMaster auto
            ControlPath ~/.ssh/cm-%r@%h:%p
            ControlPersist 10m

    Then browse http://localhost:<local-port>.
    """
    bridge = remote_cmd or (
        f"python3 -c {shlex.quote(_BRIDGE_PY)} {shlex.quote(remote_socket)}"
    )
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", local_port))
    listener.listen(16)
    click.echo(
        f"m3dash: http://localhost:{local_port}  ->  "
        f"{ssh_host}:{remote_socket}  (Ctrl-C to stop)",
        err=True,
    )

    def handle(conn: socket.socket) -> None:
        argv = [*shlex.split(ssh_cmd), ssh_host, bridge]
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        assert proc.stdin and proc.stdout
        t = threading.Thread(
            target=_shovel, args=(conn, proc.stdin.fileno()), daemon=True
        )
        t.start()
        _shovel(proc.stdout.fileno(), conn)
        conn.close()
        proc.terminate()

    try:
        while True:
            conn, _ = listener.accept()
            threading.Thread(target=handle, args=(conn,), daemon=True).start()
    except KeyboardInterrupt:
        pass
    finally:
        listener.close()


@main.command("ls")
@click.option("--json", "as_json", is_flag=True, help="Output JSON.")
@click.option(
    "--root",
    "roots",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    multiple=True,
    help="Run root to scan (repeatable); defaults to configured roots.",
)
def ls(as_json: bool, roots: tuple[Path, ...]) -> None:
    """List discovered MUSCLE3 runs."""
    from muscle3_dashboard.m3dash.app import load_roots
    from muscle3_dashboard.m3dash.discovery import discover_runs, runs_to_json

    runs = discover_runs(
        [r.expanduser() for r in roots] or load_roots(), harvest=as_json
    )
    if as_json:
        click.echo(runs_to_json(runs))
        return
    for run in runs:
        ref = str(run.job_id or run.pid or "")
        updated = str(run.last_updated or "")[:16]
        click.echo(f"{run.status.value:9} {updated:16} {ref:>8}  {run.run_dir}")


@main.command()
@click.argument(
    "run_dir", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
@click.option("--node", default=None, help="Fallback node for loopback URLs.")
@click.option("--json", "as_json", is_flag=True, help="Output JSON.")
def urls(run_dir: Path, node: str | None, as_json: bool) -> None:
    """Show served-UI URLs harvested from a run's instance logs."""
    import json as _json

    from muscle3_dashboard.m3dash.harvest import harvest_run

    found = harvest_run(run_dir, fallback_node=node)
    if as_json:
        click.echo(_json.dumps([u.to_dict() for u in found], indent=2))
        return
    for u in found:
        mark = "" if u.resolved else "  (node unresolved)"
        click.echo(f"{u.instance:24} {u.reachable_url}{mark}")


if __name__ == "__main__":
    main()
