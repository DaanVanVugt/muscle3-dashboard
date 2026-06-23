import panel as pn

from muscle3_dashboard.constants import CARD_MARGIN
from muscle3_dashboard.data_manager import DataManager


class CrashAnalysisViewer(pn.viewable.Viewer):
    """A compact crash banner naming the components likely responsible.

    The graph colours crash suspects too, but that is easy to miss; this is the
    one always-visible-on-failure summary. It uses the same structured
    classifier as the graph (``Component.crash_kind``), so the named culprit and
    the graph's red outline always agree:

    * **likely cause** -- components with a real non-zero exit code; shown with
      their exit-code message.
    * **also stopped** -- collateral SIGKILL (-9) / generic crashes after
      another component failed first; named only, to keep the banner short.

    Hidden entirely when no crash is detected, so a healthy run shows nothing.
    """

    def __init__(self, data_manager: DataManager) -> None:
        super().__init__()
        self.data_manager = data_manager
        self.alert = pn.pane.Alert(
            "", alert_type="danger", margin=CARD_MARGIN, sizing_mode="stretch_width"
        )
        self.alert.visible = False
        self.data_manager.param.watch(self.update, "data_updated")
        self.update(None)

    def update(self, event) -> None:
        text = self._summary()
        self.alert.visible = bool(text)
        if text:
            self.alert.object = text

    def _summary(self) -> str:
        """One-line-per-culprit Markdown, or "" when nothing crashed."""
        culprits: list[str] = []
        collateral: list[str] = []
        components = self.data_manager.manager_log_analyzer.components
        for name, component in components.items():
            kind = component.crash_kind
            if kind == "culprit":
                culprits.append(f"`{name}` exited with {component.exit_code_message}")
            elif kind == "killed":
                collateral.append(f"`{name}`")
        if not culprits and not collateral:
            return ""
        lines = ["**Crash detected.**"]
        if culprits:
            lines.append("Likely cause: " + "; ".join(culprits) + ".")
        if collateral:
            lines.append("Also stopped (collateral): " + ", ".join(collateral) + ".")
        return "  \n".join(lines)

    def __panel__(self):
        return self.alert
