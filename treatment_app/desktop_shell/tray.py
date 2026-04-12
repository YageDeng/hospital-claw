"""System tray icon with context menu and hotkey binding."""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

logger = logging.getLogger(__name__)


def _build_default_icon() -> QIcon:
    """Create a simple colored square icon (no external asset needed)."""
    pix = QPixmap(32, 32)
    pix.fill(QColor("#198754"))
    return QIcon(pix)


class TrayManager(QWidget):
    """System tray icon with toggle, quit, and global hotkey support.

    Signals
    -------
    toggle_requested : emitted when the user clicks the tray icon or presses the hotkey.
    quit_requested : emitted when the user selects Quit from the tray menu.
    """

    toggle_requested = Signal()
    quit_requested = Signal()

    def __init__(
        self,
        app: QApplication,
        hotkey: str = "Ctrl+Shift+T",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._app = app

        self._tray = QSystemTrayIcon(_build_default_icon(), self)
        self._tray.setToolTip("Treatment App")
        self._tray.activated.connect(self._on_tray_activated)

        menu = QMenu()
        toggle_action = QAction("Toggle Panel", menu)
        toggle_action.triggered.connect(self.toggle_requested.emit)
        menu.addAction(toggle_action)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)

        self._shortcut = QShortcut(QKeySequence(hotkey), self)
        self._shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._shortcut.activated.connect(self.toggle_requested.emit)

    def show_tray(self) -> None:
        self._tray.show()

    def hide_tray(self) -> None:
        self._tray.hide()

    def show_notification(self, title: str, message: str) -> None:
        self._tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_requested.emit()
