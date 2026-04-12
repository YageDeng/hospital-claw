"""Always-on-top hover pill that expands into the review panel.

The pill floats near the top-right of the screen, can be dragged to any edge,
and expands into the full review surface on click or hotkey.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QPoint, QPropertyAnimation, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

logger = logging.getLogger(__name__)

PILL_WIDTH = 120
PILL_HEIGHT = 36
PILL_RADIUS = 18
PILL_MARGIN = 12

STATUS_COLORS = {
    "idle": QColor("#6C757D"),
    "capturing": QColor("#0D6EFD"),
    "processing": QColor("#FFC107"),
    "ready": QColor("#198754"),
    "error": QColor("#DC3545"),
}


class HoverPill(QWidget):
    """Small draggable pill that stays always-on-top.

    Signals
    -------
    expand_requested : emitted when the user clicks the pill or presses the hotkey.
    """

    expand_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._status = "idle"
        self._label = "Treatment"
        self._drag_pos: Optional[QPoint] = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(PILL_WIDTH, PILL_HEIGHT)
        self._place_default()

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)

    def set_status(self, status: str, label: Optional[str] = None) -> None:
        self._status = status
        if label is not None:
            self._label = label
        self.update()

    def _place_default(self) -> None:
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.right() - PILL_WIDTH - PILL_MARGIN
            y = geo.top() + PILL_MARGIN
            self.move(x, y)

    # --- painting ---

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), PILL_RADIUS, PILL_RADIUS)

        color = STATUS_COLORS.get(self._status, STATUS_COLORS["idle"])
        painter.fillPath(path, color)

        painter.setPen(Qt.GlobalColor.white)
        font = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._label)
        painter.end()

    # --- drag support ---

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if self._drag_pos is not None:
                delta = event.globalPosition().toPoint() - (self.frameGeometry().topLeft() + self._drag_pos)
                if abs(delta.x()) < 4 and abs(delta.y()) < 4:
                    self.expand_requested.emit()
            self._drag_pos = None
            event.accept()
