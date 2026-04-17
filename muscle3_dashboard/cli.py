from pathlib import Path
from threading import Lock

import click
from bokeh.application.application import SessionContext

from muscle3_dashboard.constants import (
    CHECK_UNUSED_SESSIONS_MILLISECONDS,
    UNUSED_SESSION_LIFETIME_MILLISECONDS,
)

_active_sessions = 0
_lock = Lock()


@click.command()
@click.argument(
    "run_folder", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
@click.version_option()
def main(run_folder: Path) -> None:
    """TODO"""
    # Local import to not import all of panel when doing
    # `muscle_dashboard --help`
    import panel as pn

    from .dashboard import Dashboard

    def app():
        gui = Dashboard(run_folder)
        return gui

    def session_created(context: SessionContext) -> None:
        """Open session"""
        global _active_sessions
        with _lock:
            _active_sessions += 1
            print(f"Session created, {_active_sessions} sessions active")

    def session_destroyed(context: SessionContext) -> None:
        """Close session"""
        global _active_sessions
        with _lock:
            _active_sessions -= 1
            if _active_sessions == 0:
                print("Session destroyed, shutting down")
                raise SystemExit(0)
            else:
                print(f"Session destroyed, {_active_sessions} sessions active")

    pn.state.on_session_created(session_created)
    pn.state.on_session_destroyed(session_destroyed)
    pn.serve(
        app,
        threaded=True,
        unused_session_lifetime_milliseconds=UNUSED_SESSION_LIFETIME_MILLISECONDS,
        check_unused_sessions_milliseconds=CHECK_UNUSED_SESSIONS_MILLISECONDS,
    )
