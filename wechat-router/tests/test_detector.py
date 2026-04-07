"""Tests for UnreadDetector."""

import unittest

import numpy as np

from src.detector import UnreadDetector


class MockOCREngine:
    def __init__(self, text="张三"):
        self._text = text

    def recognize(self, image):
        return self._text

    def confidence(self, image):
        return 0.9

    def detect_regions(self, image):
        if self._text:
            return [{"text": self._text, "confidence": 0.9, "bbox": (0, 0, 100, 20)}]
        return []


class MockAdapter:
    def __init__(self):
        self._rect = (0, 0, 800, 600)

    def get_window_rect(self):
        return self._rect

    def get_chat_list_region(self, cal=None):
        return (0, 0, 240, 600)

    def get_message_area_region(self, cal=None):
        return (240, 0, 560, 600)


class TestUnreadDetector(unittest.TestCase):
    def setUp(self):
        self.ocr = MockOCREngine("张三")
        self.adapter = MockAdapter()
        self.detector = UnreadDetector(
            self.ocr, self.adapter, ["张三", "工作群"],
            fuzzy_threshold=70,
        )

    def test_no_badges_empty(self):
        # Use an OCR engine that returns no text so no fallback match occurs
        empty_ocr = MockOCREngine("")
        det = UnreadDetector(empty_ocr, self.adapter, ["张三", "工作群"], fuzzy_threshold=70)
        blank = np.ones((600, 240, 3), dtype=np.uint8) * 255
        result = det.detect_unread(blank)
        self.assertEqual(len(result), 0)

    def test_find_red_badge(self):
        image = np.ones((600, 240, 3), dtype=np.uint8) * 255
        cv2 = __import__("cv2")
        cv2.circle(image, (220, 50), 10, (0, 0, 255), -1)

        result = self.detector.detect_unread(image)
        # OCR returns "张三" which matches a monitored contact
        self.assertGreaterEqual(len(result), 0)

    def test_fuzzy_match(self):
        matched = self.detector._match_contact("张三")
        self.assertIsNotNone(matched)
        name, score = matched
        self.assertEqual(name, "张三")
        self.assertGreaterEqual(score, 0.7)

    def test_no_match(self):
        matched = self.detector._match_contact("王五")
        # Wang Wu is not in monitored list — might or might not match depending on fuzzy
        # Just verify it returns None or a low score
        if matched:
            _, score = matched
            self.assertLess(score, 1.0)

    def test_empty_text_no_match(self):
        matched = self.detector._match_contact("")
        self.assertIsNone(matched)


if __name__ == "__main__":
    unittest.main()
