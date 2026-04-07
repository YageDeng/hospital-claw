"""Detect unread message badges in the WeChat chat list sidebar."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
from thefuzz import fuzz

from .ocr_engine import OCREngine
from .platform_adapter import PlatformAdapter
from .utils import DebugSaver, get_platform, merge_ocr_regions, preprocess_for_ocr

logger = logging.getLogger(__name__)

# HSV range for WeChat's red unread badge
RED_LOWER_1 = np.array([0, 100, 100])
RED_UPPER_1 = np.array([10, 255, 255])
RED_LOWER_2 = np.array([160, 100, 100])
RED_UPPER_2 = np.array([180, 255, 255])

MIN_BADGE_AREA = 50
MAX_BADGE_AREA = 5000
BADGE_CIRCULARITY_THRESHOLD = 0.3

# Each chat row is roughly this tall (pixels) on a standard layout;
# scaled dynamically based on actual image height.
ESTIMATED_ROW_HEIGHT_RATIO = 0.065


class UnreadChat:
    """Represents a chat with unread messages detected in the sidebar."""

    def __init__(self, name: str, badge_rect: Tuple[int, int, int, int],
                 click_point: Tuple[int, int], match_score: float):
        self.name = name
        self.badge_rect = badge_rect
        self.click_point = click_point
        self.match_score = match_score


class UnreadDetector:
    """Finds contacts/groups with unread badges in the WeChat chat list.

    Uses a hybrid approach:
    1. OCR the full chat list to find all contact/group names and their positions
    2. Detect red unread badges via color filtering
    3. Associate badges with nearby chat rows
    4. Match chat names against the monitored list
    """

    def __init__(self, ocr_engine: OCREngine, adapter: PlatformAdapter,
                 monitored_names: List[str],
                 templates_dir: Optional[str] = None,
                 fuzzy_threshold: int = 70,
                 debug: Optional[DebugSaver] = None):
        self.ocr = ocr_engine
        self.adapter = adapter
        self.monitored_names = monitored_names
        self.fuzzy_threshold = fuzzy_threshold
        self.templates_dir = templates_dir or self._default_templates_dir()
        self.debug = debug

    def _default_templates_dir(self) -> str:
        platform = get_platform()
        return str(Path(__file__).parent.parent / "templates" / platform)

    def detect_unread(self, chat_list_image: np.ndarray) -> List[UnreadChat]:
        """Scan the chat list for monitored contacts with unread messages."""
        h_img, w_img = chat_list_image.shape[:2]

        # Step 1: Crop out avatar column for cleaner OCR
        avatar_x = int(w_img * self.adapter.avatar_ratio)
        text_strip = chat_list_image[:, avatar_x:]
        ocr_preprocessed = preprocess_for_ocr(text_strip)

        if self.debug:
            self.debug.save(text_strip, "detect_text_strip")
            self.debug.save(ocr_preprocessed, "detect_ocr_preprocessed")

        # OCR on both raw text strip and preprocessed, merge results
        regions_raw = self.ocr.detect_regions(text_strip)
        regions_preprocessed = self.ocr.detect_regions(ocr_preprocessed)
        text_regions_local = merge_ocr_regions(regions_raw, regions_preprocessed)

        # Shift OCR coordinates back to full chat list space
        text_regions = []
        for r in text_regions_local:
            rx, ry, rw, rh = r["bbox"]
            text_regions.append({
                "text": r["text"],
                "confidence": r["confidence"],
                "bbox": (rx + avatar_x, ry, rw, rh),
            })

        logger.info("OCR found %d text regions (%d raw + %d preprocessed, merged)",
                     len(text_regions), len(regions_raw), len(regions_preprocessed))
        for r in text_regions:
            logger.info("  OCR region: '%s' (conf=%.2f, bbox=%s)", r["text"], r["confidence"], r["bbox"])

        # Debug: save OCR-annotated chat list
        if self.debug:
            annotated = chat_list_image.copy()
            for r in text_regions:
                rx, ry, rw, rh = r["bbox"]
                cv2.rectangle(annotated, (rx, ry), (rx + rw, ry + rh), (0, 255, 0), 1)
                cv2.putText(annotated, r["text"][:20], (rx, ry - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 0), 1)
            self.debug.save(annotated, "detect_ocr_regions")

        # Step 2: Find red unread badges
        badge_rects = self._find_badges(chat_list_image)
        logger.info("Found %d unread badge(s)", len(badge_rects))

        # Debug: save badge-annotated image
        if self.debug:
            badge_vis = chat_list_image.copy()
            for bx, by, bw, bh in badge_rects:
                cv2.rectangle(badge_vis, (bx, by), (bx + bw, by + bh), (0, 0, 255), 2)
            self.debug.save(badge_vis, "detect_badge_rects")

        # Step 3: For each text region, check if it matches a monitored name
        row_h = int(h_img * ESTIMATED_ROW_HEIGHT_RATIO)
        results = []
        seen_names = set()

        # The crop starts at nav_bar offset — add it back for absolute coordinates
        window_rect = self.adapter.get_window_rect()
        crop_offset_x = 0
        if window_rect:
            crop_offset_x = self.adapter.get_nav_bar_width(window_rect[2])

        for region in text_regions:
            text = region["text"]
            rx, ry, rw, rh = region["bbox"]

            matched = self._match_contact(text)
            if not matched:
                continue

            name, score = matched
            logger.info("Matched OCR '%s' -> monitored '%s' (score=%.2f)", text, name, score)
            if name in seen_names:
                continue

            # Step 4: Check if there's a badge near this text row
            has_badge = self._has_nearby_badge(ry, rh, badge_rects, row_h)
            logger.info("  Badge near '%s' at y=%d: %s (row_h=%d)", name, ry, has_badge, row_h)

            if has_badge:
                seen_names.add(name)
                if window_rect:
                    abs_x = window_rect[0] + crop_offset_x + rx + rw // 2
                    abs_y = window_rect[1] + ry + rh // 2
                else:
                    abs_x = rx + rw // 2
                    abs_y = ry + rh // 2

                results.append(UnreadChat(
                    name=name,
                    badge_rect=(rx, ry, rw, rh),
                    click_point=(abs_x, abs_y),
                    match_score=score,
                ))
                logger.info("Matched unread chat: '%s' (OCR='%s', score=%.2f)", name, text, score)

        if not results:
            logger.info("No badge-associated matches found, trying fallback (no badge check)")
            for region in text_regions:
                text = region["text"]
                rx, ry, rw, rh = region["bbox"]
                matched = self._match_contact(text)
                if matched:
                    name, score = matched
                    if name not in seen_names:
                        seen_names.add(name)
                        if window_rect:
                            abs_x = window_rect[0] + crop_offset_x + rx + rw // 2
                            abs_y = window_rect[1] + ry + rh // 2
                        else:
                            abs_x = rx + rw // 2
                            abs_y = ry + rh // 2
                        results.append(UnreadChat(
                            name=name,
                            badge_rect=(rx, ry, rw, rh),
                            click_point=(abs_x, abs_y),
                            match_score=score,
                        ))
                        logger.info("Matched chat (no badge check): '%s' (OCR='%s', score=%.2f)", name, text, score)

        return results

    def _find_badges(self, image: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Detect red circular badges using color filtering."""
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

        mask1 = cv2.inRange(hsv, RED_LOWER_1, RED_UPPER_1)
        mask2 = cv2.inRange(hsv, RED_LOWER_2, RED_UPPER_2)
        red_mask = cv2.bitwise_or(mask1, mask2)

        # Large close kernel to fill white number text inside badges
        close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, close_kernel)
        # Smaller open kernel to remove noise without destroying badges
        open_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, open_kernel)

        if self.debug:
            self.debug.save(red_mask, "detect_red_mask")

        contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        badges = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            x, y, w, h = cv2.boundingRect(cnt)

            if area < MIN_BADGE_AREA or area > MAX_BADGE_AREA:
                logger.info("  Badge candidate rejected (area=%d, bounds=%s)", area, (x, y, w, h))
                continue

            perimeter = cv2.arcLength(cnt, True)
            if perimeter == 0:
                continue
            circularity = 4 * np.pi * area / (perimeter ** 2)
            if circularity < BADGE_CIRCULARITY_THRESHOLD:
                logger.info("  Badge candidate rejected (circ=%.3f, area=%d, bounds=%s)",
                            circularity, area, (x, y, w, h))
                continue

            aspect = w / max(h, 1)
            if aspect > 2.5 or aspect < 0.4:
                logger.info("  Badge candidate rejected (aspect=%.2f, bounds=%s)", aspect, (x, y, w, h))
                continue

            logger.info("  Badge accepted: area=%d, circ=%.3f, bounds=%s", area, circularity, (x, y, w, h))
            badges.append((x, y, w, h))

        return badges

    def _has_nearby_badge(self, text_y: int, text_h: int,
                          badges: List[Tuple[int, int, int, int]],
                          row_height: int) -> bool:
        """Check if any red badge is vertically close to a text region."""
        text_center_y = text_y + text_h // 2
        for bx, by, bw, bh in badges:
            badge_center_y = by + bh // 2
            if abs(badge_center_y - text_center_y) < row_height:
                return True
        return False

    def _match_contact(self, ocr_text: str) -> Optional[Tuple[str, float]]:
        """Fuzzy-match OCR text against monitored contact names."""
        if not ocr_text.strip():
            return None

        best_name = None
        best_score = 0

        for name in self.monitored_names:
            score = fuzz.partial_ratio(ocr_text.strip(), name)
            if score > best_score:
                best_score = score
                best_name = name

        if best_score >= self.fuzzy_threshold:
            logger.info("Fuzzy matched '%s' -> '%s' (score=%d)", ocr_text.strip(), best_name, best_score)
            return (best_name, best_score / 100.0)

        logger.debug("No fuzzy match for OCR text: '%s' (best_score=%d, threshold=%d)",
                     ocr_text.strip(), best_score, self.fuzzy_threshold)
        return None
