"""Content extraction pipeline — single-pass OCR, content classification."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .ocr_engine import OCREngine
from .utils import DebugSaver, normalize_ocr_text, preprocess_for_ocr, timestamp_filename

logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(r'https?://\S+|www\.\S+')

CONTENT_TYPES = ("text", "image", "file", "link", "voice", "video", "sticker", "other")

OCR_DOWNSCALE = 0.5


class ExtractedMessage:
    """A single extracted message from a chat screenshot."""

    def __init__(self, sender: Optional[str], content_type: str,
                 text_content: Optional[str] = None,
                 timestamp_ocr: Optional[str] = None,
                 attachment_path: Optional[str] = None,
                 raw_region: Optional[np.ndarray] = None):
        self.sender = sender
        self.content_type = content_type
        self.text_content = text_content
        self.timestamp_ocr = timestamp_ocr
        self.attachment_path = attachment_path
        self.raw_region = raw_region


class ContentExtractor:
    """Extracts and classifies messages from chat area screenshots.

    Uses a single-pass OCR strategy: run detect_regions() once on the
    full (downscaled) screenshot, then reuse those text regions for
    classification, sender detection, and timestamp extraction without
    additional OCR calls.
    """

    def __init__(self, ocr_engine: OCREngine, attachments_dir: str,
                 confidence_threshold: float = 0.6,
                 templates_dir: Optional[str] = None,
                 debug: Optional[DebugSaver] = None,
                 msg_avatar_ratio: float = 0.04):
        self.ocr = ocr_engine
        self.attachments_dir = attachments_dir
        self.confidence_threshold = confidence_threshold
        self.templates_dir = templates_dir
        self.debug = debug
        self.msg_avatar_ratio = msg_avatar_ratio
        Path(attachments_dir).mkdir(parents=True, exist_ok=True)

    def extract_messages(self, message_area: np.ndarray,
                         is_group: bool = False) -> List[ExtractedMessage]:
        """Extract all messages from a message area screenshot."""
        if self.debug:
            self.debug.save(message_area, "extract_raw_input")

        # Crop avatar columns from both sides
        h_full, w_full = message_area.shape[:2]
        margin = int(w_full * self.msg_avatar_ratio)
        message_area = message_area[:, margin:w_full - margin]
        h_img, w_img = message_area.shape[:2]

        if self.debug:
            self.debug.save(message_area, "extract_avatar_cropped")

        # Single-pass OCR on downscaled + preprocessed image
        small = cv2.resize(message_area, None, fx=OCR_DOWNSCALE, fy=OCR_DOWNSCALE,
                           interpolation=cv2.INTER_AREA)
        ocr_input = preprocess_for_ocr(small)
        if self.debug:
            self.debug.save(small, "extract_ocr_downscaled")
            self.debug.save(ocr_input, "extract_ocr_preprocessed")

        raw_regions = self.ocr.detect_regions(ocr_input)

        # Scale coordinates back to original resolution
        scale_inv = 1.0 / OCR_DOWNSCALE
        ocr_regions = []
        for r in raw_regions:
            rx, ry, rw, rh = r["bbox"]
            ocr_regions.append({
                "text": r["text"],
                "confidence": r["confidence"],
                "bbox": (int(rx * scale_inv), int(ry * scale_inv),
                         int(rw * scale_inv), int(rh * scale_inv)),
            })

        # Debug: save OCR regions overlaid on original
        if self.debug:
            ocr_vis = message_area.copy()
            for r in ocr_regions:
                rx, ry, rw, rh = r["bbox"]
                cv2.rectangle(ocr_vis, (rx, ry), (rx + rw, ry + rh), (0, 255, 0), 1)
                cv2.putText(ocr_vis, r["text"][:20], (rx, ry - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 0), 1)
            self.debug.save(ocr_vis, "extract_ocr_regions")

        # Detect message bubbles
        bubbles = self._detect_bubbles(message_area)
        messages = []
        current_timestamp = None

        for bx, by, bw, bh in bubbles:
            region = message_area[by:by + bh, bx:bx + bw]

            # Find OCR regions that overlap with this bubble
            bubble_texts = self._regions_in_rect(ocr_regions, bx, by, bw, bh)
            bubble_text = " ".join(r["text"] for r in bubble_texts)
            avg_conf = (sum(r["confidence"] for r in bubble_texts) / len(bubble_texts)
                        if bubble_texts else 0.0)

            # Timestamp: look for short centered text above the bubble
            ts = self._detect_timestamp_from_regions(ocr_regions, by, w_img)
            if ts:
                current_timestamp = ts

            # Classify using cached OCR data
            content_type = self._classify_from_cache(
                region, bubble_text, avg_conf, bubble_texts
            )

            # Sender detection for group chats
            sender = None
            if is_group:
                sender = self._detect_sender_from_regions(
                    ocr_regions, bx, by, bw, w_img
                )

            # Build the message
            msg = self._build_message(region, content_type, bubble_text)
            msg.sender = sender
            msg.timestamp_ocr = current_timestamp
            msg.raw_region = region
            messages.append(msg)

            if self.debug:
                label = f"extract_bubble_{len(messages):02d}_{content_type}"
                self.debug.save(region, label)

        logger.info("Extracted %d message(s) from screenshot", len(messages))
        return messages

    def _regions_in_rect(self, regions: List[dict], x: int, y: int,
                         w: int, h: int, margin: int = 10) -> List[dict]:
        """Return OCR regions whose center falls inside the given rectangle."""
        result = []
        for r in regions:
            rx, ry, rw, rh = r["bbox"]
            cx = rx + rw // 2
            cy = ry + rh // 2
            if (x - margin <= cx <= x + w + margin and
                    y - margin <= cy <= y + h + margin):
                result.append(r)
        return result

    def _detect_bubbles(self, image: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Detect message bubble regions using contour analysis.

        Uses both grayscale adaptive threshold and green channel isolation
        to catch white and green bubbles in light/dark mode.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        thresh_gray = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 11, 2,
        )

        # Also detect green bubbles (WeChat's sender bubbles) via HSV
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        green_mask = cv2.inRange(hsv, np.array([35, 40, 40]), np.array([85, 255, 255]))

        # Combine both masks
        thresh = cv2.bitwise_or(thresh_gray, green_mask)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 5))
        dilated = cv2.dilate(thresh, kernel, iterations=3)

        if self.debug:
            self.debug.save(thresh, "extract_threshold")
            self.debug.save(dilated, "extract_dilated")

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        h_img, w_img = image.shape[:2]
        min_area = h_img * w_img * 0.001
        max_area = h_img * w_img * 0.8

        bubbles = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if min_area < area < max_area:
                x, y, w, h = cv2.boundingRect(cnt)
                if w > 20 and h > 10:
                    bubbles.append((x, y, w, h))

        bubbles.sort(key=lambda b: b[1])

        if self.debug:
            contour_vis = image.copy()
            for bx, by, bw, bh in bubbles:
                cv2.rectangle(contour_vis, (bx, by), (bx + bw, by + bh), (255, 0, 0), 2)
            self.debug.save(contour_vis, "extract_bubble_contours")

        return bubbles

    def _classify_from_cache(self, bubble: np.ndarray, text: str,
                             avg_confidence: float,
                             text_regions: List[dict]) -> str:
        """Classify content type using cached OCR results (no extra OCR calls)."""
        h, w = bubble.shape[:2]
        aspect = w / max(h, 1)

        if self._match_template("voice", bubble):
            return "voice"
        if self._match_template("video", bubble):
            return "video"
        if self._match_template("file", bubble):
            return "file"
        if self._match_template("link", bubble):
            return "link"

        if avg_confidence >= self.confidence_threshold and text.strip():
            if URL_PATTERN.search(text):
                return "link"
            return "text"

        if 0.8 < aspect < 1.2 and h < 120 and w < 120:
            return "sticker"

        hsv = cv2.cvtColor(bubble, cv2.COLOR_BGR2HSV)
        color_variance = np.std(hsv[:, :, 0])
        if h > 80 and w > 80 and color_variance > 20:
            return "image"

        return "other"

    def _match_template(self, template_name: str, image: np.ndarray) -> bool:
        """Try to match a template image (e.g. file icon, play button)."""
        if not self.templates_dir:
            return False

        template_path = os.path.join(self.templates_dir, f"{template_name}.png")
        if not os.path.exists(template_path):
            return False

        template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
        if template is None:
            return False

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        th, tw = template.shape[:2]
        if th > gray.shape[0] or tw > gray.shape[1]:
            scale = min(gray.shape[0] / th, gray.shape[1] / tw) * 0.8
            template = cv2.resize(template, None, fx=scale, fy=scale)

        result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)
        return max_val > 0.7

    def _build_message(self, bubble: np.ndarray, content_type: str,
                       cached_text: str) -> ExtractedMessage:
        """Build an ExtractedMessage using cached OCR text where possible."""
        cleaned = normalize_ocr_text(cached_text)
        if content_type == "text":
            return ExtractedMessage(sender=None, content_type="text",
                                    text_content=cleaned)

        if content_type in ("image", "sticker", "video"):
            path = self._save_attachment(bubble, content_type)
            return ExtractedMessage(sender=None, content_type=content_type,
                                    attachment_path=path)

        if content_type == "link":
            return ExtractedMessage(sender=None, content_type="link",
                                    text_content=cleaned)

        if content_type == "file":
            return ExtractedMessage(sender=None, content_type="file",
                                    text_content=cleaned)

        if content_type == "voice":
            return ExtractedMessage(sender=None, content_type="voice",
                                    text_content=cleaned)

        return ExtractedMessage(sender=None, content_type="other")

    def _detect_sender_from_regions(self, regions: List[dict], bx: int, by: int,
                                    bw: int, img_width: int) -> Optional[str]:
        """Detect sender from cached OCR regions above a left-side bubble."""
        mid_x = img_width // 2

        if bx + bw // 2 > mid_x:
            return "self"

        # Look for text regions just above the bubble (within 40px)
        for r in regions:
            rx, ry, rw, rh = r["bbox"]
            region_bottom = ry + rh
            if (by - 40 <= region_bottom <= by + 5 and
                    rx < mid_x and r["text"].strip()):
                return r["text"].strip()

        return None

    def _detect_timestamp_from_regions(self, regions: List[dict], bubble_y: int,
                                       img_width: int) -> Optional[str]:
        """Detect WeChat timestamp from cached OCR regions above a bubble."""
        center_x = img_width // 4
        center_end = center_x + img_width // 2

        for r in regions:
            rx, ry, rw, rh = r["bbox"]
            region_center_x = rx + rw // 2
            region_bottom = ry + rh
            text = r["text"].strip()

            if (bubble_y - 50 <= region_bottom <= bubble_y + 5 and
                    center_x <= region_center_x <= center_end and
                    text and len(text) < 30):
                return text

        return None

    def _save_attachment(self, image: np.ndarray, content_type: str) -> str:
        filename = timestamp_filename(content_type)
        path = os.path.join(self.attachments_dir, filename)
        cv2.imwrite(path, image)
        logger.debug("Saved attachment: %s", path)
        return path
