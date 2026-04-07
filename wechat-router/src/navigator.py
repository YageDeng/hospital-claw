"""Chat navigation — atomic UI primitives and orchestration flows.

Layer 1 (primitives): click_sidebar, click_message_area, click_message_input,
    click_at, scroll_sidebar, scroll_messages, scroll_sidebar_to_top,
    scroll_messages_to_bottom, capture_chat_list, capture_message_area,
    type_and_send, press_escape, images_similar

Layer 2 (orchestration): find_chat_in_sidebar, find_and_open_chat,
    reset_chat_selection, send_message, capture_all_messages,
    scroll_up_to_keyword, capture_downward
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional, Tuple

import cv2
import numpy as np
import pyautogui
import pyperclip
from thefuzz import fuzz

from .ocr_engine import OCREngine
from .platform_adapter import PlatformAdapter
from .utils import DebugSaver, merge_ocr_regions, preprocess_for_ocr

logger = logging.getLogger(__name__)

SCROLL_PAUSE = 0.01
MAX_SCROLL_ATTEMPTS = 20
SIMILARITY_THRESHOLD = 0.98
SIDEBAR_SCROLL_PAUSE = 0.02
MAX_SIDEBAR_SCROLLS = 10
FUZZY_MATCH_THRESHOLD = 70
MSG_SCROLL_AMOUNT = 500
SIDEBAR_SCROLL_AMOUNT = 200

OCR_DOWNSCALE = 0.5


def _downscale(image: np.ndarray, scale: float = OCR_DOWNSCALE) -> np.ndarray:
    """Downscale an image for faster OCR."""
    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)


class ChatNavigator:
    """Two-layer navigator: atomic UI primitives + orchestration flows."""

    def __init__(self, adapter: PlatformAdapter, debug: Optional[DebugSaver] = None):
        self.adapter = adapter
        self.debug = debug

    # ------------------------------------------------------------------
    # Layer 1 — Atomic Primitives
    # ------------------------------------------------------------------

    # --- Focus / Click ---

    def click_at(self, x: int, y: int, pause: float = 0.3) -> None:
        """Click at absolute screen coordinates and wait."""
        logger.info("click_at (%d, %d)", x, y)
        self.adapter.click(x, y)
        time.sleep(pause)

    def move_to_sidebar(self) -> None:
        """Move the mouse to the center of the sidebar without clicking."""
        rect = self.adapter.get_window_rect()
        if not rect:
            return
        wl, wt, ww, wh = rect
        nav_w = self.adapter.get_nav_bar_width(ww)
        sidebar_w = self.adapter.get_sidebar_width(ww)
        x = wl + nav_w + (sidebar_w - nav_w) // 2
        y = wt + int(wh * 0.5)
        logger.info("move_to_sidebar at (%d, %d)", x, y)
        pyautogui.moveTo(x, y)
        time.sleep(0.05)

    def click_sidebar(self) -> None:
        """Click the center of the chat list sidebar to focus it."""
        rect = self.adapter.get_window_rect()
        if not rect:
            return
        wl, wt, ww, wh = rect
        nav_w = self.adapter.get_nav_bar_width(ww)
        sidebar_w = self.adapter.get_sidebar_width(ww)
        x = wl + nav_w + (sidebar_w - nav_w) // 2
        y = wt + int(wh * 0.5)
        logger.info("click_sidebar at (%d, %d)", x, y)
        self.adapter.click(x, y)
        time.sleep(0.1)

    def click_message_area(self) -> None:
        """Click the center of the message area to focus it for scrolling."""
        rect = self.adapter.get_window_rect()
        if not rect:
            return
        wl, wt, ww, wh = rect
        sidebar_w = self.adapter.get_sidebar_width(ww)
        x = wl + sidebar_w + (ww - sidebar_w) // 2
        y = wt + int(wh * 0.5)
        logger.info("click_message_area at (%d, %d)", x, y)
        self.adapter.click(x, y)
        time.sleep(0.1)

    def click_message_input(self, y_ratio: float = 0.90) -> None:
        """Click the message input box at the bottom of the message area.

        Args:
            y_ratio: vertical position as fraction of window height (default 0.88).
                     Adjust if the input box is at a different position.
        """
        rect = self.adapter.get_window_rect()
        if not rect:
            logger.warning("click_message_input: window rect unavailable")
            return
        wl, wt, ww, wh = rect
        sidebar_w = self.adapter.get_sidebar_width(ww)
        x = wl + sidebar_w + (ww - sidebar_w) // 2
        y = wt + int(wh * y_ratio)
        logger.info("click_message_input at (%d, %d) [y_ratio=%.2f]", x, y, y_ratio)
        self.adapter.click(x, y)
        time.sleep(0.2)

    # --- Scroll ---

    def scroll_sidebar(self, direction: str = "down",
                       amount: int = SIDEBAR_SCROLL_AMOUNT) -> None:
        """Single scroll on the sidebar. Caller must ensure sidebar is focused."""
        self.adapter.scroll(direction, amount=amount)
        time.sleep(SIDEBAR_SCROLL_PAUSE)

    def scroll_messages(self, direction: str = "up",
                        amount: int = MSG_SCROLL_AMOUNT) -> None:
        """Single scroll on the message area. Caller must ensure it is focused."""
        self.adapter.scroll(direction, amount=amount)
        time.sleep(SCROLL_PAUSE)

    def scroll_sidebar_to_top(self) -> None:
        """Scroll the sidebar up to reach the very top.

        Assumes mouse is already over the sidebar.
        """
        for _ in range(5):
            self.adapter.scroll("up", amount=500)
            time.sleep(0.1)
        time.sleep(0.2)
        logger.info("Scrolled chat list to top")

    def scroll_messages_to_bottom(self) -> None:
        """Scroll the message area down to reach the bottom."""
        self.click_message_area()
        for _ in range(5):
            self.adapter.scroll("down", amount=500)
            time.sleep(0.1)
        time.sleep(0.2)

    # --- Capture ---

    def capture_chat_list(self, calibration: Optional[dict] = None) -> Optional[np.ndarray]:
        """Screenshot the chat list sidebar region."""
        full = self.adapter.capture_window()
        if full is None:
            return None
        x, y, w, h = self.adapter.get_chat_list_region(calibration)
        return full[y:y + h, x:x + w].copy()

    def capture_message_area(self, calibration: Optional[dict] = None) -> Optional[np.ndarray]:
        """Screenshot the message display region."""
        full = self.adapter.capture_window()
        if full is None:
            return None
        x, y, w, h = self.adapter.get_message_area_region(calibration)
        return full[y:y + h, x:x + w].copy()

    # --- Input ---

    def type_and_send(self, text: str) -> None:
        """Paste text via clipboard and press Enter to send.

        Caller must ensure the input box is focused (call click_message_input first).
        """
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.1)
        pyautogui.press("enter")
        time.sleep(0.3)
        logger.info("Typed and sent: %s", text[:80])

    def press_escape(self) -> None:
        """Press the Escape key."""
        pyautogui.press("escape")
        time.sleep(0.1)

    # --- Utility ---

    def images_similar(self, img1: np.ndarray, img2: np.ndarray) -> bool:
        """Check if two images are nearly identical (scroll reached boundary)."""
        if img1.shape != img2.shape:
            return False
        gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
        score = cv2.matchTemplate(gray1, gray2, cv2.TM_CCOEFF_NORMED)[0][0]
        return score > SIMILARITY_THRESHOLD

    # ------------------------------------------------------------------
    # Layer 2 — Orchestration Flows (compose primitives)
    # ------------------------------------------------------------------

    def is_chat_selected(self, chat_list_img: np.ndarray,
                         ry: int, rh: int) -> bool:
        """Check if a chat row is currently selected (green/blue highlight).

        Samples the background color of the row in the chat list image.
        """
        row_y = max(0, ry)
        row_y_end = min(chat_list_img.shape[0], ry + rh)
        if row_y >= row_y_end:
            return False
        row_strip = chat_list_img[row_y:row_y_end, :20]
        hsv = cv2.cvtColor(row_strip, cv2.COLOR_BGR2HSV)
        mean_s = float(np.mean(hsv[:, :, 1]))
        mean_v = float(np.mean(hsv[:, :, 2]))
        # Selected rows have a colored (green/blue) background with noticeable saturation
        is_selected = mean_s > 30 and mean_v > 80
        logger.info("is_chat_selected: mean_s=%.0f mean_v=%.0f -> %s", mean_s, mean_v, is_selected)
        return is_selected

    def find_chat_in_sidebar(self, name: str, ocr_engine: OCREngine,
                             calibration: Optional[dict] = None
                             ) -> Optional[Tuple[int, int, bool]]:
        """OCR-search the sidebar for a chat name.

        Scrolls through the chat list if needed.
        Returns (click_x, click_y, already_selected) or None.
        Does NOT click the chat.
        """
        rect = self.adapter.get_window_rect()
        if not rect:
            logger.error("Cannot find chat: window rect unavailable")
            return None

        wl, wt, ww, wh = rect

        self.move_to_sidebar()
        self.scroll_sidebar_to_top()

        prev_capture = None

        for attempt in range(MAX_SIDEBAR_SCROLLS):
            chat_list_img = self.capture_chat_list(calibration)
            if chat_list_img is None:
                logger.warning("Failed to capture chat list on attempt %d", attempt)
                continue

            if self.debug:
                self.debug.save(chat_list_img, f"find_chat_{attempt:02d}_capture")

            if prev_capture is not None and self.images_similar(prev_capture, chat_list_img):
                logger.info("Reached bottom of chat list without finding '%s'", name)
                return None
            prev_capture = chat_list_img

            # Strip avatar column for cleaner OCR (same as detector)
            h_cl, w_cl = chat_list_img.shape[:2]
            avatar_x = int(w_cl * self.adapter.avatar_ratio)
            text_strip = chat_list_img[:, avatar_x:]

            small = _downscale(text_strip)
            ocr_preprocessed = preprocess_for_ocr(small)
            if self.debug:
                self.debug.save(ocr_preprocessed, f"find_chat_{attempt:02d}_ocr_preprocessed")

            regions_raw = ocr_engine.detect_regions(small)
            regions_preprocessed = ocr_engine.detect_regions(ocr_preprocessed)
            regions = merge_ocr_regions(regions_raw, regions_preprocessed)
            scale_inv = 1.0 / OCR_DOWNSCALE

            all_texts = [r["text"].strip() for r in regions if r["text"].strip()]
            logger.info("find_chat attempt %d: OCR found %d regions (%d with text), searching for '%s'. All texts: %s",
                         attempt, len(regions), len(all_texts), name, all_texts[:20])
            for region in regions:
                text = region["text"].strip()
                if not text:
                    continue

                score = fuzz.partial_ratio(text, name)
                if score >= 50:
                    logger.info("  OCR text='%s' score=%d (threshold=%d)",
                                 text, score, FUZZY_MATCH_THRESHOLD)
                if score >= FUZZY_MATCH_THRESHOLD:
                    rx, ry, rw, rh = region["bbox"]
                    rx = int(rx * scale_inv) + avatar_x
                    ry = int(ry * scale_inv)
                    rw = int(rw * scale_inv)
                    rh = int(rh * scale_inv)
                    nav_w = self.adapter.get_nav_bar_width(ww)
                    click_x = wl + nav_w + rx + rw // 2
                    click_y = wt + ry + rh // 2
                    selected = self.is_chat_selected(chat_list_img, ry, rh)
                    logger.info("Found '%s' in sidebar (OCR='%s', score=%d, selected=%s) at (%d, %d)",
                                name, text, score, selected, click_x, click_y)
                    return (click_x, click_y, selected)

            self.move_to_sidebar()
            self.scroll_sidebar("down")

        logger.warning("Could not find '%s' after scrolling through entire chat list", name)
        return None

    def find_and_open_chat(self, name: str, ocr_engine: OCREngine,
                           calibration: Optional[dict] = None) -> bool:
        """Find a chat by name in the sidebar and click to open it.

        Skips clicking if the chat is already selected (green highlight).
        """
        result = self.find_chat_in_sidebar(name, ocr_engine, calibration)
        if result is None:
            return False
        click_x, click_y, already_selected = result
        if already_selected:
            logger.info("Chat '%s' is already selected, skipping click", name)
        else:
            self.click_at(click_x, click_y)
            logger.info("Opened chat: %s", name)
        return True

    def open_chat(self, click_x: int, click_y: int) -> bool:
        """Click on a chat entry at known coordinates. Returns True on success."""
        logger.debug("Opening chat at (%d, %d)", click_x, click_y)
        self.click_at(click_x, click_y)

        image = self.adapter.capture_window()
        if image is None:
            return False
        rect = self.adapter.get_window_rect()
        if not rect:
            return False
        _, _, ww, _ = rect
        sidebar_w = self.adapter.get_sidebar_width(ww)
        message_area = image[:, sidebar_w:]
        return message_area.size > 0

    def reset_chat_selection(self, ocr_engine: OCREngine = None,
                             reset_chat_name: str = "文件传输助手",
                             calibration: Optional[dict] = None) -> None:
        """Scroll the chat list to the top so scanning starts from a clean state."""
        logger.info("Resetting chat list: moving to sidebar and scrolling to top")
        self.move_to_sidebar()
        self.scroll_sidebar_to_top()

    def return_to_chat_list(self) -> None:
        """Press Escape to return focus to the chat list."""
        self.press_escape()

    def send_message(self, text: str) -> bool:
        """Click the input box, type a message, and send it.

        Assumes the target chat is already open.
        """
        rect = self.adapter.get_window_rect()
        if not rect:
            logger.error("Cannot send message: window rect unavailable")
            return False
        self.click_message_input()
        self.type_and_send(text)
        return True

    def capture_all_messages(self, calibration: Optional[dict] = None,
                             max_scrolls: int = MAX_SCROLL_ATTEMPTS) -> List[np.ndarray]:
        """Scroll up capturing all visible messages. Returns screenshots in chronological order."""
        captures = []

        current = self.capture_message_area(calibration)
        if current is None:
            return captures
        captures.append(current)
        if self.debug:
            self.debug.save(current, "nav_scroll_up_000")

        for i in range(max_scrolls):
            self.scroll_messages("up")

            new_capture = self.capture_message_area(calibration)
            if new_capture is None:
                break

            if self.images_similar(current, new_capture):
                logger.debug("Reached top of conversation after %d scrolls", i + 1)
                break

            captures.append(new_capture)
            current = new_capture
            if self.debug:
                self.debug.save(new_capture, f"nav_scroll_up_{i + 1:03d}")

        captures.reverse()
        logger.info("Captured %d message area screenshot(s)", len(captures))
        return captures

    def scroll_up_to_keyword(self, ocr_engine: OCREngine, stop_keywords: List[str],
                              calibration: Optional[dict] = None,
                              max_scrolls: int = 80) -> bool:
        """Scroll UP checking for stop keywords via OCR.

        Returns True if a stop keyword was found, False if top was reached.
        """
        self.click_message_area()

        prev = self.capture_message_area(calibration)
        if prev is None:
            return False

        for i in range(max_scrolls):
            self.scroll_messages("up")

            current = self.capture_message_area(calibration)
            if current is None:
                break

            if self.images_similar(prev, current):
                logger.info("Reached top of conversation after %d scrolls (no stop keyword)", i + 1)
                return False

            small = _downscale(current)
            ocr_input = preprocess_for_ocr(small)
            text = ocr_engine.recognize(ocr_input)
            for kw in stop_keywords:
                if kw in text:
                    logger.info("Found stop keyword '%s' after %d scrolls up", kw, i + 1)
                    return True

            prev = current

        logger.info("Reached max scrolls (%d) without finding stop keyword", max_scrolls)
        return False

    def capture_downward(self, calibration: Optional[dict] = None,
                         max_scrolls: int = 80) -> List[np.ndarray]:
        """Scroll DOWN capturing screenshots until bottom. Returns list of screenshots."""
        captures = []

        current = self.capture_message_area(calibration)
        if current is None:
            return captures
        captures.append(current)
        if self.debug:
            self.debug.save(current, "nav_scroll_down_000")

        for i in range(max_scrolls):
            self.scroll_messages("down")

            new_capture = self.capture_message_area(calibration)
            if new_capture is None:
                break

            if self.images_similar(current, new_capture):
                logger.debug("Reached bottom of conversation after %d scrolls down", i + 1)
                break

            captures.append(new_capture)
            current = new_capture
            if self.debug:
                self.debug.save(new_capture, f"nav_scroll_down_{i + 1:03d}")

        logger.info("Captured %d screenshot(s) scrolling down", len(captures))
        return captures
