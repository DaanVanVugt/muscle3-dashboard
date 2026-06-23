"""m3dash command line interface.

  ``m3dash serve``    run the server on a unix socket (for an SSH forward).
  ``m3dash open``     serve on a loopback TCP port and open a browser.
  ``m3dash ls``       list discovered runs on the terminal.

Reach it from your machine with an SSH LocalForward to the unix socket, e.g.::

    LocalForward 127.0.0.1:4333 /home/ITER/%r/.m3dash.sock
"""

import logging
import os
from pathlib import Path

import click

from muscle3_dashboard.m3dash.discovery import discover_runs, runs_to_json

# In the home dir so that one ssh_config line works for every user:
#   LocalForward 127.0.0.1:4333 /home/ITER/%r/.m3dash.sock
# (%r expands to the remote username). Unix sockets are host-local even
# on a shared filesystem: pin one login node and run m3dash there.
DEFAULT_SOCKET = Path("~/.m3dash.sock").expanduser()


def default_tcp_port() -> int:
    """Deterministic per-user loopback port for ``m3dash open``.

    Outside the Linux ephemeral range (32768+) to avoid collisions with
    short-lived connections, and per-user so two people on the same node
    don't clash. NB unlike the 0600 socket, a loopback TCP port is
    connectable by other users on the same node.
    """
    return 20000 + os.getuid() % 10000


DEFAULT_LOCAL_PORT = 4333

#: Positional run roots, shared by every command. Empty means "scan the
#: current directory", so ``m3dash ls`` in a run tree just works.
roots_argument = click.argument(
    "roots",
    nargs=-1,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)


def _resolve_roots(roots: tuple[Path, ...]) -> list[Path]:
    return [r.expanduser() for r in roots] or [Path.cwd()]


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )


@click.group()
def main() -> None:
    """Find MUSCLE3 runs and serve their dashboards over one endpoint."""


@main.command()
@roots_argument
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
    "origin (localhost:<port>).",
)
def serve(roots: tuple[Path, ...], socket_path: Path, local_port: int) -> None:
    """For remote access: serve on a unix socket via your SSH forward (blocking).

    Reached through an SSH LocalForward to the socket (see the module
    docstring). ROOTS are the directories scanned for runs (default: the
    current directory); they are fixed for the server's life, so restart
    to change them.
    """
    _setup_logging()
    from muscle3_dashboard.m3dash import app

    app.serve(socket_path, _resolve_roots(roots), local_port=local_port)


@main.command("open")
@roots_argument
@click.option(
    "--port",
    "tcp_port",
    type=int,
    default=None,
    help="Loopback TCP port to serve on. Default: a per-user port, "
    "20000 + uid % 10000.",
)
@click.option(
    "--open-browser/--no-open-browser",
    default=True,
    show_default=True,
    help="Open a browser at the URL once serving.",
)
def open_(roots: tuple[Path, ...], tcp_port: int | None, open_browser: bool) -> None:
    """On this machine: serve on a local port and open a browser (blocking).

    For a desktop session running on the node itself (e.g. NoMachine),
    where no SSH socket forward is involved. A loopback TCP port is also
    the fallback where sshd forbids unix-socket forwarding: run
    ``m3dash open --no-open-browser`` and forward the port with a plain
    ``LocalForward 127.0.0.1:<port> 127.0.0.1:<port>``. ROOTS are the
    directories scanned for runs (default: the current directory).
    """
    _setup_logging()
    from muscle3_dashboard.m3dash import app

    app.serve(
        None,
        _resolve_roots(roots),
        tcp_port=tcp_port or default_tcp_port(),
        open_browser=open_browser,
    )


@main.command("ls")
@roots_argument
@click.option("--json", "as_json", is_flag=True, help="Output JSON.")
def ls(roots: tuple[Path, ...], as_json: bool) -> None:
    """List discovered MUSCLE3 runs.

    ROOTS are the directories scanned for runs (default: the current
    directory).
    """
    runs = discover_runs(_resolve_roots(roots))
    if as_json:
        click.echo(runs_to_json(runs))
        return
    for run in runs:
        ref = str(run.job_id or run.pid or "")
        updated = str(run.last_updated or "")[:16]
        click.echo(f"{run.status.value:9} {updated:16} {ref:>8}  {run.run_dir}")


if __name__ == "__main__":
    main()
