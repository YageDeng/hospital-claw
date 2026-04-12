"""Top-level desktop shell that wires hover pill, review panel, and tray."""

from __future__ import annotations

import logging
import sys
from typing import Optional

from PySide6.QtWidgets import QApplication

from treatment_app.schemas import TargetAppProfile, TreatmentPlanCase

from .hover_widget import HoverPill
from .review_panel import ReviewPanel
from .tray import TrayManager

logger = logging.getLogger(__name__)


class DesktopShell:
    """Single entry-point that owns the QApplication and all shell widgets."""

    def __init__(self, hotkey: str = "Ctrl+Shift+T") -> None:
        self._app = QApplication.instance() or QApplication(sys.argv)

        self.pill = HoverPill()
        self.panel = ReviewPanel()
        self.tray = TrayManager(self._app, hotkey=hotkey)

        self.pill.expand_requested.connect(self._toggle_panel)
        self.tray.toggle_requested.connect(self._toggle_panel)
        self.tray.quit_requested.connect(self._quit)

        self._case: Optional[TreatmentPlanCase] = None
        self._profile: Optional[TargetAppProfile] = None

    def start(self) -> None:
        """Show the pill and tray, then enter the event loop."""
        self.pill.show()
        self.tray.show_tray()
        logger.info("Desktop shell started")
        self._app.exec()

    def load_case(self, case: TreatmentPlanCase, profile: TargetAppProfile) -> None:
        self._case = case
        self._profile = profile
        self.panel.load_case(case, profile)
        self.pill.set_status("ready", "Ready")

    def _toggle_panel(self) -> None:
        if self.panel.isVisible():
            self.panel.hide()
        else:
            pill_geo = self.pill.frameGeometry()
            self.panel.move(
                pill_geo.left() - self.panel.width() + self.pill.width(),
                pill_geo.bottom() + 4,
            )
            self.panel.resize(420, 500)
            self.panel.show()

    def _quit(self) -> None:
        logger.info("Quit requested")
        self.tray.hide_tray()
        self._app.quit()
