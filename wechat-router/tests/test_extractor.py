"""Tests for ContentExtractor."""

import os
import tempfile
import unittest

import numpy as np

from src.extractor import ContentExtractor, ExtractedMessage


class MockOCREngine:
    def __init__(self, text="你好世界", conf=0.85):
        self._text = text
        self._conf = conf

    def recognize(self, image):
        return self._text

    def confidence(self, image):
        return self._conf

    def detect_regions(self, image):
        if self._text:
            return [{"text": self._text, "confidence": self._conf, "bbox": (0, 0, 100, 20)}]
        return []


class TestContentExtractor(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ocr = MockOCREngine("你好世界", 0.85)
        self.extractor = ContentExtractor(
            self.ocr, self.tmpdir, confidence_threshold=0.6,
        )

    def test_classify_text(self):
        bubble = np.ones((40, 200, 3), dtype=np.uint8) * 200
        ct = self.extractor._classify_from_cache(
            bubble, "你好世界", 0.85, [{"text": "你好世界", "confidence": 0.85, "bbox": (0, 0, 100, 20)}]
        )
        self.assertEqual(ct, "text")

    def test_classify_low_confidence(self):
        bubble = np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8)
        ct = self.extractor._classify_from_cache(bubble, "", 0.1, [])
        self.assertIn(ct, ("image", "sticker", "other"))

    def test_classify_link(self):
        bubble = np.ones((40, 300, 3), dtype=np.uint8) * 200
        ct = self.extractor._classify_from_cache(
            bubble, "Check https://example.com for details", 0.85,
            [{"text": "Check https://example.com for details", "confidence": 0.85, "bbox": (0, 0, 200, 20)}]
        )
        self.assertEqual(ct, "link")

    def test_build_text_message(self):
        bubble = np.ones((40, 200, 3), dtype=np.uint8) * 200
        msg = self.extractor._build_message(bubble, "text", "你好世界")
        self.assertEqual(msg.content_type, "text")
        self.assertEqual(msg.text_content, "你好世界")

    def test_build_image_saves_file(self):
        bubble = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        msg = self.extractor._build_message(bubble, "image", "")
        self.assertEqual(msg.content_type, "image")
        self.assertIsNotNone(msg.attachment_path)
        self.assertTrue(os.path.exists(msg.attachment_path))

    def test_extract_messages_single_pass(self):
        image = np.ones((200, 400, 3), dtype=np.uint8) * 220
        msgs = self.extractor.extract_messages(image, is_group=False)
        self.assertIsInstance(msgs, list)

    def test_extracted_message_fields(self):
        msg = ExtractedMessage(
            sender="Alice", content_type="text",
            text_content="hello", timestamp_ocr="14:00",
        )
        self.assertEqual(msg.sender, "Alice")
        self.assertEqual(msg.content_type, "text")
        self.assertEqual(msg.text_content, "hello")
        self.assertEqual(msg.timestamp_ocr, "14:00")


if __name__ == "__main__":
    unittest.main()
