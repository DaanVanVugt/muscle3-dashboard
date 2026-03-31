import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN


class CrashAnalysisViewer(pn.viewable.Viewer):
    def __init__(self) -> None:
        super().__init__()
        self.components_exit_code_dict = {}
        self.markdown = pn.pane.Markdown(self.markdown_str)
        self.card = pn.Card(
            self.markdown,
            title="Crash analysis",
            margin=CARD_MARGIN,
            sizing_mode="stretch_width",
        )

    def update(self, components_exit_code_dict):
        self.components_exit_code_dict = components_exit_code_dict
        self.markdown.object = self.markdown_str

    @property
    def markdown_str(self):
        crashed_components = {
            name: exit_code_message
            for name, exit_code_message in self.components_exit_code_dict.items()
            if exit_code_message != "0"
        }
        if len(crashed_components):
            new_str = (
                "Crash detected. "
                "We expect one of the following components "
                "to be responsible.\n\n"
            )
            new_str += "\n".join(
                [
                    f"- {name} exited with {exit_code_message}"
                    for name, exit_code_message in crashed_components.items()
                    if "-9" not in exit_code_message
                ]
            )
        else:
            new_str = "No crash detected"
        return new_str

    def __panel__(self):
        return self.card
