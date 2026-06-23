"""Small Panel helpers shared across the m3dash server and the dashboard."""

import contextlib

import panel as pn


def add_session_periodic_callback(callback, period: int) -> None:
    """Register a Panel periodic callback once per session, for servers + scripts.

    In a live server session the registration is deferred to ``pn.state.onload``,
    since adding it during app construction makes Bokeh replay a
    SessionCallbackAdded event on the first document unhold. Bokeh dedups periodic
    callbacks by id and raises ValueError on a duplicate (a replayed event, or a
    session reload) -- the callback is already polling then, so the duplicate is
    ignored. Outside a session (scripts, tests) there may be no running event
    loop, so the add is attempted directly and a RuntimeError suppressed.
    """

    def _add() -> None:
        with contextlib.suppress(ValueError):
            pn.state.add_periodic_callback(callback, period=period)

    if pn.state.curdoc:
        pn.state.onload(_add)
    else:
        with contextlib.suppress(RuntimeError):
            _add()
