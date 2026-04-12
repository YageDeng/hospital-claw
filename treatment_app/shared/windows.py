"""Windows desktop automation helpers: window discovery, capture, and input.

Provides injectable callables for screenshotting, window enumeration, and
clicking so the module is fully testable without a live desktop.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

import numpy as np

from treatment_app.schemas import RegionLocator, WindowMatcher

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DesktopWindow:
    """Lightweight snapshot of a visible desktop window."""

    title: str
    executable_name: str
    class_name: str
    left: int
    top: int
    width: int
    height: int


WindowProvider = Callable[[], list[DesktopWindow]]
Screenshotter = Callable[[tuple[int, int, int, int]], np.ndarray]
Clicker = Callable[[int, int], None]


class WindowsDesktopAutomation:
    """Reusable primitives for window discovery, capture, and mouse input.

    All platform calls are injected so the class is testable with fakes.
    """

    def __init__(
        self,
        window_provider: Optional[WindowProvider] = None,
        screenshotter: Optional[Screenshotter] = None,
        clicker: Optional[Clicker] = None,
    ):
        self._window_provider = window_provider or _default_window_provider
        self._screenshotter = screenshotter or _default_screenshotter
        self._clicker = clicker or _default_clicker

    def find_window(
        self, matchers: Sequence[WindowMatcher]
    ) -> Optional[DesktopWindow]:
        """Return the first visible window matching any of *matchers*, or None."""
        windows = self._window_provider()
        for window in windows:
            for matcher in matchers:
                if _matches(window, matcher):
                    logger.info(
                        "Matched window '%s' (%s)", window.title, window.executable_name
                    )
                    return window
        return None

    def capture_window(
        self,
        window: DesktopWindow,
        excluded_regions: Optional[list[RegionLocator]] = None,
    ) -> np.ndarray:
        """Capture a screenshot of *window*, zeroing out any excluded regions."""
        region = (window.left, window.top, window.width, window.height)
        image = self._screenshotter(region)
        for ex in excluded_regions or []:
            image[ex.y : ex.y + ex.height, ex.x : ex.x + ex.width] = 0
        return image

    def click_relative(self, window: DesktopWindow, rx: int, ry: int) -> None:
        """Click at coordinates relative to the window's top-left corner."""
        abs_x = window.left + rx
        abs_y = window.top + ry
        logger.debug("click_relative (%d, %d) -> screen (%d, %d)", rx, ry, abs_x, abs_y)
        self._clicker(abs_x, abs_y)


def _matches(window: DesktopWindow, matcher: WindowMatcher) -> bool:
    if matcher.executable_names:
        if window.executable_name.lower() not in [
            n.lower() for n in matcher.executable_names
        ]:
            return False
    if matcher.title_patterns:
        if not any(
            re.search(pat, window.title, re.IGNORECASE)
            for pat in matcher.title_patterns
        ):
            return False
    if matcher.class_names:
        if window.class_name not in matcher.class_names:
            return False
    return True


def _default_window_provider() -> list[DesktopWindow]:
    """Enumerate visible windows via pygetwindow (Windows only)."""
    try:
        import pygetwindow as gw

        windows: list[DesktopWindow] = []
        for w in gw.getAllWindows():
            if not w.title or not w.visible:
                continue
            windows.append(
                DesktopWindow(
                    title=w.title,
                    executable_name="",
                    class_name="",
                    left=w.left,
                    top=w.top,
                    width=w.width,
                    height=w.height,
                )
            )
        return windows
    except ImportError:
        logger.warning("pygetwindow not available; returning empty window list")
        return []


def _default_screenshotter(region: tuple[int, int, int, int]) -> np.ndarray:
    """Capture a screen region via pyautogui."""
    import pyautogui

    screenshot = pyautogui.screenshot(region=region)
    return np.array(screenshot)


def _default_clicker(x: int, y: int) -> None:
    """Click at screen coordinates via pyautogui."""
    import pyautogui

    pyautogui.click(x, y)
