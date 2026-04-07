"""Shared utility functions."""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def setup_logging(level: str = "INFO", log_file: Optional[str] = None) -> None:
    """Configure application-wide logging."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    import io
    stdout_wrapper = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    handlers: list[logging.Handler] = [logging.StreamHandler(stdout_wrapper)]

    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )


_FULLWIDTH_OFFSET = 0xFEE0  # ord('！') - ord('!')

def normalize_ocr_text(text: Optional[str]) -> str:
    """Normalize OCR text so slight recognition differences still match.

    Handles: extra whitespace, full-width/half-width, common substitutions,
    stray punctuation, and case differences.
    """
    if not text:
        return ""
    import re
    import unicodedata

    # Full-width ASCII (！-～) → half-width (! - ~), except space
    chars = []
    for ch in text:
        cp = ord(ch)
        if 0xFF01 <= cp <= 0xFF5E:
            chars.append(chr(cp - _FULLWIDTH_OFFSET))
        elif cp == 0x3000:  # ideographic space → ascii space
            chars.append(" ")
        else:
            chars.append(ch)
    s = "".join(chars)

    # Unicode normalize (e.g. composed vs decomposed)
    s = unicodedata.normalize("NFKC", s)
    # Lowercase
    s = s.lower()
    # Common OCR substitutions
    s = s.replace("\u2018", "'").replace("\u2019", "'")   # smart quotes
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2014", "-").replace("\u2013", "-")   # em/en dash
    s = s.replace("\u00b7", ".").replace("\u2022", ".")   # middle dot / bullet
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()

    return s


def compute_content_hash(contact_name: str, sender: Optional[str],
                         text_content: Optional[str], timestamp_ocr: Optional[str]) -> str:
    """Compute SHA-256 hash for message deduplication.

    Normalizes OCR-derived fields so slight recognition differences
    (spaces, full-width chars, case) still produce the same hash.
    """
    parts = [
        contact_name or "",
        normalize_ocr_text(sender),
        normalize_ocr_text(text_content),
        normalize_ocr_text(timestamp_ocr),
    ]
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def timestamp_filename(prefix: str = "screenshot", ext: str = "png") -> str:
    """Generate a timestamped filename."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"{prefix}_{ts}.{ext}"


def get_platform() -> str:
    """Return 'windows' or 'macos'."""
    if sys.platform == "win32":
        return "windows"
    elif sys.platform == "darwin":
        return "macos"
    raise RuntimeError(f"Unsupported platform: {sys.platform}")


def retry(func, max_attempts: int = 3, backoff_base: float = 1.0):
    """Retry a callable with exponential backoff. Returns the result or raises the last exception."""
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except Exception as e:
            last_exc = e
            wait = backoff_base * (2 ** (attempt - 1))
            logger.warning("Attempt %d/%d failed: %s — retrying in %.1fs",
                           attempt, max_attempts, e, wait)
            time.sleep(wait)
    raise last_exc


def ensure_file_dir(file_path: str) -> None:
    """Ensure the parent directory of a file path exists."""
    os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)


def clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def merge_ocr_regions(regions_a: list, regions_b: list) -> list:
    """Merge two OCR region lists, dropping near-duplicate bboxes.

    Keeps the higher-confidence detection when two regions overlap.
    Used to combine results from raw and preprocessed OCR passes.
    """
    merged = list(regions_a)
    for rb in regions_b:
        bx, by, bw, bh = rb["bbox"]
        bc_x, bc_y = bx + bw // 2, by + bh // 2
        is_dup = False
        for ra in merged:
            ax, ay, aw, ah = ra["bbox"]
            ac_x, ac_y = ax + aw // 2, ay + ah // 2
            if abs(bc_x - ac_x) < 20 and abs(bc_y - ac_y) < 20:
                if rb["confidence"] > ra["confidence"]:
                    ra.update(rb)
                is_dup = True
                break
        if not is_dup:
            merged.append(rb)
    return merged


def preprocess_for_ocr(image):
    """Convert an image to black-text-on-white for OCR.

    Works for both dark mode (light text on dark bg) and light mode
    (dark text on light bg) by detecting the background brightness
    and normalizing accordingly.
    """
    import cv2
    import numpy as np

    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    if float(np.mean(gray)) < 128:
        gray = cv2.bitwise_not(gray)

    _, result = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Safety check: ensure text is dark on light background
    if float(np.mean(result)) < 128:
        result = cv2.bitwise_not(result)

    if len(image.shape) == 3:
        return cv2.cvtColor(result, cv2.COLOR_GRAY2BGR)
    return result


class DebugSaver:
    """Saves debug images to a timestamped subfolder per scan run.

    Usage:
        saver = DebugSaver("data/debug")    # creates data/debug/20260331_215900/
        saver.save(image, "01_raw_window")
        saver.save(mask,  "02_red_mask")
    """

    def __init__(self, base_dir: str, enabled: bool = True):
        self.enabled = enabled
        self._counter = 0
        if not enabled:
            self.run_dir = ""
            return
        run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = os.path.join(base_dir, run_ts)
        os.makedirs(self.run_dir, exist_ok=True)
        logger.info("Debug images will be saved to %s", self.run_dir)

    def save(self, image, label: str, ext: str = "png") -> Optional[str]:
        """Save an image with an auto-incrementing counter prefix."""
        if not self.enabled or image is None:
            return None
        import cv2
        self._counter += 1
        filename = f"{self._counter:03d}_{label}.{ext}"
        path = os.path.join(self.run_dir, filename)
        cv2.imwrite(path, image)
        logger.debug("Debug saved: %s", path)
        return path
