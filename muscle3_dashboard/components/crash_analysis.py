from collections import defaultdict

import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN
from muscle3_dashboard.data_manager import DataManager


class CrashAnalysisViewer(pn.viewable.Viewer):
    """Panel component showing the most likely components responsible for a
    simulation crash. Collapsed while there is nothing to report; pops
    open on the first detected crash."""

    def __init__(self, data_manager: DataManager) -> None:
        super().__init__()
        self.components_exit_code_dict = {}
        self.alert = pn.pane.Alert(self.markdown_str, alert_type="success")
        self.card = pn.Card(
            self.alert,
            title="Crash analysis",
            margin=CARD_MARGIN,
            sizing_mode="stretch_width",
            collapsed=True,
        )
        self._crash_reported = False
        self.data_manager = data_manager
        self.data_manager.param.watch(self.update, "data_updated")

    def update(self, event):
        """Method to update crash analysis viewer from listener"""
        self.components_exit_code_dict = {
            component.name: component.exit_code_message
            for component in self.data_manager.manager_log_analyzer.components.values()
        }
        crashed = any(
            message and message != "0"
            for message in self.components_exit_code_dict.values()
        )
        self.alert.object = self.markdown_str
        self.alert.alert_type = "danger" if crashed else "success"
        # Open the card once per crash; leave it alone afterwards so the
        # user can re-collapse it.
        if crashed and not self._crash_reported:
            self._crash_reported = True
            self.card.collapsed = False

    @property
    def markdown_str(self):
        """Build string for markdown based on inner state"""
        crashed_components = defaultdict(list)
        for name, exit_code_message in self.components_exit_code_dict.items():
            if exit_code_message and exit_code_message != "0":
                crashed_components[exit_code_message].append(name)
        if len(crashed_components):
            new_str = (
                "Crash detected. "
                "We expect one of the following components "
                "to be responsible.\n\n"
            )
            new_str += "\n".join(
                [
                    f"- {name} exited with {exit_code_message}"
                    for exit_code_message, names in crashed_components.items()
                    for name in names
                    if "-9" not in exit_code_message
                    and "crashed" not in exit_code_message
                ]
            )
            if "crashed" in crashed_components:
                new_str += "\n\nThe following components crashed, "
                new_str += "likely because an error occurred elsewhere:\n\n"
                new_str += "\n".join(
                    [f"- {name}" for name in crashed_components["crashed"]]
                )
        else:
            new_str = "No crash detected"
        return new_str

    def __panel__(self):
        return self.card
