"""Tests for ChatNavigator and calibration-aware adapter regions."""

import unittest
from unittest.mock import patch

import numpy as np

from src.navigator import ChatNavigator
from src.platform_adapter import PlatformAdapter


def _make_region(text, bbox, confidence=0.9):
    return {"text": text, "confidence": confidence, "bbox": bbox}


def _make_window(marker_x):
    image = np.zeros((600, 800, 3), dtype=np.uint8)
    image[40:80, marker_x:marker_x + 20] = 255
    return image


class FakePlatformAdapter(PlatformAdapter):
    def __init__(self, captures=None):
        self._rect = (0, 0, 800, 600)
        self.nav_bar_ratio = 0.1
        self.sidebar_ratio = 0.3
        self.avatar_ratio = 0.0
        self.captures = list(captures or [])
        self.scroll_calls = []

    def find_wechat_window(self, title="WeChat"):
        return True

    def capture_window(self):
        if self.captures:
            return self.captures.pop(0).copy()
        return np.zeros((600, 800, 3), dtype=np.uint8)

    def get_window_rect(self):
        return self._rect

    def click(self, x, y):
        return None

    def scroll(self, direction="up", amount=3):
        self.scroll_calls.append((direction, amount))


class QuietNavigator(ChatNavigator):
    def move_to_sidebar(self):
        return None


class SequenceOCREngine:
    def __init__(self, responses):
        self._responses = list(responses)
        self.call_count = 0

    def detect_regions(self, image):
        self.call_count += 1
        if self._responses:
            return self._responses.pop(0)
        return []


class TestPlatformAdapterCalibration(unittest.TestCase):
    def test_chat_list_region_uses_calibration(self):
        adapter = FakePlatformAdapter()

        region = adapter.get_chat_list_region({"chat_list": [10, 20, 300, 400]})

        self.assertEqual(region, (10, 20, 300, 400))

    def test_message_area_region_uses_calibration(self):
        adapter = FakePlatformAdapter()

        region = adapter.get_message_area_region({"message_area": [200, 50, 500, 520]})

        self.assertEqual(region, (200, 50, 500, 520))


class TestChatNavigator(unittest.TestCase):
    @patch("src.navigator.time.sleep", return_value=None)
    def test_find_chat_picks_best_scoring_candidate(self, _sleep):
        adapter = FakePlatformAdapter([_make_window(100)])
        navigator = QuietNavigator(adapter)
        ocr = SequenceOCREngine([
            [
                _make_region("near miss", (10, 40, 60, 20), 0.95),
                _make_region("target chat", (15, 140, 70, 20), 0.60),
            ],
            [],
        ])

        def score_lookup(text, target):
            scores = {
                "near miss": 72,
                "target chat": 95,
            }
            return scores[text.lower()]

        with patch("src.navigator._downscale", side_effect=lambda image: image), \
             patch("src.navigator.OCR_DOWNSCALE", 1.0), \
             patch("src.navigator.preprocess_for_ocr", side_effect=lambda image: image), \
             patch("src.navigator.merge_ocr_regions", side_effect=lambda raw, pre: raw + pre), \
             patch("src.navigator.fuzz.partial_ratio", side_effect=score_lookup), \
             patch.object(QuietNavigator, "scroll_sidebar_to_top", return_value=None), \
             patch.object(QuietNavigator, "is_chat_selected", return_value=False):
            result = navigator.find_chat_in_sidebar("Target Chat", ocr)

        self.assertEqual(result, (130, 150, False))

    @patch("src.navigator.time.sleep", return_value=None)
    def test_find_chat_uses_full_resolution_fallback_when_fast_pass_misses(self, _sleep):
        adapter = FakePlatformAdapter([_make_window(120)])
        navigator = QuietNavigator(adapter)
        ocr = SequenceOCREngine([
            [],
            [],
            [_make_region("target chat", (20, 100, 80, 24), 0.92)],
            [],
        ])

        with patch("src.navigator._downscale", side_effect=lambda image: image), \
             patch("src.navigator.OCR_DOWNSCALE", 1.0), \
             patch("src.navigator.preprocess_for_ocr", side_effect=lambda image: image), \
             patch("src.navigator.merge_ocr_regions", side_effect=lambda raw, pre: raw + pre), \
             patch("src.navigator.fuzz.partial_ratio", return_value=96), \
             patch.object(QuietNavigator, "scroll_sidebar_to_top", return_value=None), \
             patch.object(QuietNavigator, "is_chat_selected", return_value=False):
            result = navigator.find_chat_in_sidebar("Target Chat", ocr)

        self.assertEqual(result, (140, 112, False))
        self.assertGreaterEqual(ocr.call_count, 4)

    @patch("src.navigator.time.sleep", return_value=None)
    def test_scroll_sidebar_to_top_stops_when_captures_stabilize(self, _sleep):
        adapter = FakePlatformAdapter([
            _make_window(100),
            _make_window(120),
            _make_window(140),
            _make_window(140),
        ])
        navigator = QuietNavigator(adapter)

        navigator.scroll_sidebar_to_top()

        self.assertEqual(adapter.scroll_calls, [
            ("up", 500),
            ("up", 500),
            ("up", 500),
        ])


if __name__ == "__main__":
    unittest.main()
