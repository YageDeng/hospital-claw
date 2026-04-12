"""Tests for reusable OCR and window automation helpers."""

import os
import sys
import types
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from treatment_app.schemas import RegionLocator, WindowMatcher
from treatment_app.shared.image_utils import merge_ocr_regions, normalize_ocr_text
from treatment_app.shared.ocr import EasyOCREngine, TesseractEngine, create_ocr_engine
from treatment_app.shared.windows import DesktopWindow, WindowsDesktopAutomation


class FakePytesseractModule:
    class Output:
        DICT = "DICT"

    def __init__(self):
        self.pytesseract = types.SimpleNamespace(tesseract_cmd=None)

    def image_to_string(self, image, lang, config):
        return " recognized text \n"

    def image_to_data(self, image, lang, config, output_type):
        return {
            "text": ["Diagnosis", ""],
            "conf": ["80", "-1"],
            "left": [4, 0],
            "top": [6, 0],
            "width": [40, 0],
            "height": [12, 0],
        }


class FakeEasyReader:
    def readtext(self, image, detail=1):
        if detail == 0:
            return ["chief complaint", "neck pain"]
        return [
            ([(0, 0), (20, 0), (20, 10), (0, 10)], "Diagnosis", 0.88),
            ([(30, 10), (50, 10), (50, 24), (30, 24)], "Pain", 0.77),
        ]


class TestTreatmentAppSharedAutomation(unittest.TestCase):
    def test_normalize_ocr_text_flattens_spacing_and_fullwidth_chars(self):
        self.assertEqual(normalize_ocr_text("ＡＢＣ　 Neck\nPain "), "abc neck pain")

    def test_merge_ocr_regions_prefers_higher_confidence_duplicate(self):
        merged = merge_ocr_regions(
            [
                {
                    "text": "old",
                    "confidence": 0.5,
                    "bbox": (10, 10, 30, 10),
                }
            ],
            [
                {
                    "text": "new",
                    "confidence": 0.9,
                    "bbox": (12, 12, 30, 10),
                }
            ],
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["text"], "new")
        self.assertEqual(merged[0]["confidence"], 0.9)

    def test_tesseract_engine_uses_injected_module(self):
        engine = TesseractEngine(
            languages="eng",
            pytesseract_module=FakePytesseractModule(),
        )

        self.assertEqual(engine.recognize(np.zeros((10, 10, 3), dtype=np.uint8)), "recognized text")
        self.assertEqual(
            engine.detect_regions(np.zeros((10, 10, 3), dtype=np.uint8)),
            [{"text": "Diagnosis", "confidence": 0.8, "bbox": (4, 6, 40, 12)}],
        )

    def test_easyocr_engine_detect_regions_with_injected_reader(self):
        engine = EasyOCREngine(languages="eng", reader=FakeEasyReader())

        self.assertEqual(engine.recognize(np.zeros((10, 10, 3), dtype=np.uint8)), "chief complaint neck pain")
        self.assertEqual(
            engine.detect_regions(np.zeros((10, 10, 3), dtype=np.uint8)),
            [
                {"text": "Diagnosis", "confidence": 0.88, "bbox": (0, 0, 20, 10)},
                {"text": "Pain", "confidence": 0.77, "bbox": (30, 10, 20, 14)},
            ],
        )

    def test_create_ocr_engine_rejects_unknown_engine(self):
        with self.assertRaisesRegex(ValueError, "Unknown OCR engine"):
            create_ocr_engine("missing")

    def test_find_window_matches_title_executable_and_class(self):
        automation = WindowsDesktopAutomation(
            window_provider=lambda: [
                DesktopWindow(
                    title="Treatment Form - Alice",
                    executable_name="his.exe",
                    class_name="MainWnd",
                    left=100,
                    top=200,
                    width=640,
                    height=480,
                ),
                DesktopWindow(
                    title="Other App",
                    executable_name="other.exe",
                    class_name="OtherWnd",
                    left=0,
                    top=0,
                    width=100,
                    height=100,
                ),
            ]
        )

        match = automation.find_window(
            [
                WindowMatcher(
                    executable_names=["his.exe"],
                    title_patterns=["Treatment Form"],
                    class_names=["MainWnd"],
                )
            ]
        )

        self.assertIsNotNone(match)
        self.assertEqual(match.title, "Treatment Form - Alice")

    def test_capture_window_masks_excluded_regions(self):
        captured_regions = []

        def fake_capture(region):
            captured_regions.append(region)
            return np.full((8, 8, 3), 255, dtype=np.uint8)

        automation = WindowsDesktopAutomation(
            screenshotter=fake_capture,
        )
        window = DesktopWindow(
            title="Treatment Form",
            executable_name="his.exe",
            class_name="MainWnd",
            left=50,
            top=80,
            width=8,
            height=8,
        )

        image = automation.capture_window(
            window,
            excluded_regions=[RegionLocator(x=2, y=3, width=2, height=3)],
        )

        self.assertEqual(captured_regions, [(50, 80, 8, 8)])
        self.assertTrue((image[3:6, 2:4] == 0).all())

    def test_click_relative_translates_to_screen_coordinates(self):
        clicked = []
        automation = WindowsDesktopAutomation(clicker=lambda x, y: clicked.append((x, y)))
        window = DesktopWindow(
            title="Treatment Form",
            executable_name="his.exe",
            class_name="MainWnd",
            left=25,
            top=40,
            width=300,
            height=200,
        )

        automation.click_relative(window, 10, 20)

        self.assertEqual(clicked, [(35, 60)])


if __name__ == "__main__":
    unittest.main()
