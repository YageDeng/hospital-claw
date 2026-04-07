"""Platform abstraction for Windows and macOS WeChat window interaction."""

from __future__ import annotations

import json
import logging
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
import pyautogui
from PIL import Image

from .utils import get_platform

logger = logging.getLogger(__name__)

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


class PlatformAdapter(ABC):
    """Abstract interface for platform-specific WeChat window operations."""

    nav_bar_ratio: float = 0.035
    sidebar_ratio: float = 0.22
    avatar_ratio: float = 0.2

    @abstractmethod
    def find_wechat_window(self, title: str = "WeChat") -> bool:
        """Locate WeChat window and bring to foreground. Returns True if found."""

    @abstractmethod
    def capture_window(self) -> Optional[np.ndarray]:
        """Capture a screenshot of the WeChat window. Returns BGR numpy array."""

    @abstractmethod
    def get_window_rect(self) -> Optional[tuple[int, int, int, int]]:
        """Return (left, top, width, height) of the WeChat window."""

    def get_nav_bar_width(self, window_width: int) -> int:
        return int(window_width * self.nav_bar_ratio)

    def get_sidebar_width(self, window_width: int) -> int:
        return int(window_width * self.sidebar_ratio)

    def get_chat_list_region(self, calibration: Optional[dict] = None) -> Tuple[int, int, int, int]:
        """Region of the sidebar chat list (x, y, w, h) relative to window.

        Starts after the navigation icon bar, ends at the sidebar split.
        """
        rect = self.get_window_rect()
        if not rect:
            raise RuntimeError("WeChat window not found")
        _, _, ww, wh = rect
        nav_w = self.get_nav_bar_width(ww)
        sidebar_w = self.get_sidebar_width(ww)
        return (nav_w, 0, sidebar_w - nav_w, wh)

    def get_message_area_region(self, calibration: Optional[dict] = None) -> Tuple[int, int, int, int]:
        """Region of the main message display (x, y, w, h) relative to window."""
        rect = self.get_window_rect()
        if not rect:
            raise RuntimeError("WeChat window not found")
        _, _, ww, wh = rect
        sidebar_w = self.get_sidebar_width(ww)
        return (sidebar_w, 0, ww - sidebar_w, wh)

    def click(self, x: int, y: int) -> None:
        """Click at absolute screen coordinates."""
        pyautogui.click(x, y)

    def scroll(self, direction: str = "up", amount: int = 3) -> None:
        """Scroll within the current position. direction: 'up' or 'down'."""
        clicks = amount if direction == "up" else -amount
        pyautogui.scroll(clicks)

    def load_calibration(self, path: str) -> Optional[dict]:
        p = Path(path)
        if p.exists():
            with open(p, "r") as f:
                return json.load(f)
        return None

    def save_calibration(self, path: str, data: dict) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Calibration saved to %s", path)


class WindowsAdapter(PlatformAdapter):
    """Windows-specific WeChat window operations."""

    def __init__(self):
        import pygetwindow as gw
        self._gw = gw
        self._window = None

    def find_wechat_window(self, title: str = "WeChat") -> bool:
        windows = self._gw.getWindowsWithTitle(title)
        # Filter to windows whose title is exactly the target or starts with it
        # (WeChat window title is just "WeChat" or "微信")
        exact = [w for w in windows if w.title.strip() == title]
        if not exact:
            exact = [w for w in windows if w.title.strip().startswith(title)
                     and "Cursor" not in w.title and "Chrome" not in w.title
                     and "Code" not in w.title]
        if not exact:
            logger.warning("WeChat window '%s' not found", title)
            return False
        self._window = exact[0]
        try:
            if self._window.isMinimized:
                self._window.restore()
            self._window.activate()
        except Exception as e:
            logger.warning("Could not activate window (non-fatal): %s", e)
        time.sleep(0.3)
        return True

    def capture_window(self) -> Optional[np.ndarray]:
        rect = self.get_window_rect()
        if not rect:
            return None
        left, top, width, height = rect
        screenshot = pyautogui.screenshot(region=(left, top, width, height))
        return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

    def get_window_rect(self) -> Optional[tuple[int, int, int, int]]:
        if self._window is None:
            return None
        return (self._window.left, self._window.top,
                self._window.width, self._window.height)


class MacOSAdapter(PlatformAdapter):
    """macOS-specific WeChat window operations."""

    def __init__(self):
        self._window_rect: Optional[tuple[int, int, int, int]] = None

    def find_wechat_window(self, title: str = "WeChat") -> bool:
        import subprocess
        script = f'''
        tell application "System Events"
            set wechatProcs to (every process whose name is "{title}")
            if (count of wechatProcs) > 0 then
                set frontmost of (item 1 of wechatProcs) to true
                tell (item 1 of wechatProcs)
                    set winPos to position of window 1
                    set winSize to size of window 1
                end tell
                return (item 1 of winPos) & "," & (item 2 of winPos) & "," & (item 1 of winSize) & "," & (item 2 of winSize)
            else
                return "NOT_FOUND"
            end if
        end tell
        '''
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=5,
            )
            output = result.stdout.strip()
            if output == "NOT_FOUND" or not output:
                logger.warning("WeChat window not found on macOS")
                return False
            parts = [int(x.strip()) for x in output.split(",")]
            self._window_rect = tuple(parts)
            time.sleep(0.3)
            return True
        except Exception as e:
            logger.error("Failed to find WeChat on macOS: %s", e)
            return False

    def capture_window(self) -> Optional[np.ndarray]:
        rect = self.get_window_rect()
        if not rect:
            return None
        left, top, width, height = rect
        screenshot = pyautogui.screenshot(region=(left, top, width, height))
        return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

    def get_window_rect(self) -> Optional[tuple[int, int, int, int]]:
        return self._window_rect


def create_adapter() -> PlatformAdapter:
    """Factory: returns the correct adapter for the current OS."""
    platform = get_platform()
    if platform == "windows":
        return WindowsAdapter()
    elif platform == "macos":
        return MacOSAdapter()
    raise RuntimeError(f"Unsupported platform: {platform}")
