from pathlib import Path

import click


@click.command()
@click.argument(
    "run_folder", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
@click.version_option()
def main(run_folder: Path) -> None:
    """TODO"""
    # Local import to not import all of panel when doing `muscle_dashboard --help`
    import panel as pn

    from .dashboard import Dashboard

    app = Dashboard(run_folder)
    pn.serve(app, threaded=True)
