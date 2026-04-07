"""Screenshot capture for the WeChat window."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .platform_adapter import PlatformAdapter
from .utils import DebugSaver, timestamp_filename

logger = logging.getLogger(__name__)


class ScreenCapture:
    """Captures screenshots of the WeChat window and specific regions."""

    def __init__(self, adapter: PlatformAdapter, screenshots_dir: str,
                 debug: Optional[DebugSaver] = None):
        self.adapter = adapter
        self.screenshots_dir = screenshots_dir
        self.debug = debug
        Path(screenshots_dir).mkdir(parents=True, exist_ok=True)

    def capture_full_window(self, save: bool = True) -> Optional[np.ndarray]:
        """Capture the entire WeChat window."""
        image = self.adapter.capture_window()
        if image is None:
            logger.warning("Failed to capture WeChat window")
            return None
        if save:
            self._save(image, "window")
        if self.debug:
            self.debug.save(image, "raw_full_window")
        return image

    def capture_chat_list(self, calibration: Optional[dict] = None,
                          save: bool = True) -> Optional[np.ndarray]:
        """Capture just the chat list sidebar."""
        full = self.adapter.capture_window()
        if full is None:
            return None
        if self.debug:
            self.debug.save(full, "raw_full_for_chatlist")
        x, y, w, h = self.adapter.get_chat_list_region(calibration)
        cropped = full[y:y + h, x:x + w]
        if save:
            self._save(cropped, "chatlist")
        if self.debug:
            self.debug.save(cropped, "crop_chatlist")
        return cropped

    def capture_message_area(self, calibration: Optional[dict] = None,
                             save: bool = True) -> Optional[np.ndarray]:
        """Capture just the message display area."""
        full = self.adapter.capture_window()
        if full is None:
            return None
        if self.debug:
            self.debug.save(full, "raw_full_for_messages")
        x, y, w, h = self.adapter.get_message_area_region(calibration)
        cropped = full[y:y + h, x:x + w]
        if save:
            self._save(cropped, "messages")
        if self.debug:
            self.debug.save(cropped, "crop_message_area")
        return cropped

    def capture_region(self, image: np.ndarray, x: int, y: int,
                       w: int, h: int) -> np.ndarray:
        """Crop a sub-region from an existing image."""
        return image[y:y + h, x:x + w].copy()

    def _save(self, image: np.ndarray, prefix: str) -> str:
        filename = timestamp_filename(prefix)
        path = os.path.join(self.screenshots_dir, filename)
        cv2.imwrite(path, image)
        logger.debug("Saved screenshot: %s", path)
        return path
