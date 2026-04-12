"""Tests for capture, perception, and schema-mapping services."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from treatment_app.schemas import (
    CaptureRegion,
    FieldDefinition,
    FieldKind,
    FieldReviewState,
    RegionLocator,
    ReviewControlType,
    ReviewFieldLayout,
    ReviewSectionLayout,
    TargetAppProfile,
    WindowMatcher,
)
from treatment_app.services.capture_service import CaptureService
from treatment_app.services.perception_service import (
    FieldExtraction,
    PerceptionService,
)
from treatment_app.services.schema_mapper import SchemaMapper, _coerce
from treatment_app.shared.windows import DesktopWindow, WindowsDesktopAutomation


def _white_image(h: int = 100, w: int = 200) -> np.ndarray:
    return np.full((h, w, 3), 255, dtype=np.uint8)


def _make_profile(**overrides) -> TargetAppProfile:
    defaults = dict(
        profile_id="test-profile",
        name="Test",
        window_matchers=[WindowMatcher(executable_names=["app.exe"])],
        field_definitions=[
            FieldDefinition(
                field_id="name",
                label="Name",
                section_id="info",
                field_type=FieldKind.TEXT,
                review_control=ReviewControlType.SINGLE_LINE,
            ),
            FieldDefinition(
                field_id="age",
                label="Age",
                section_id="info",
                field_type=FieldKind.INTEGER,
                review_control=ReviewControlType.SINGLE_LINE,
            ),
        ],
        review_sections=[
            ReviewSectionLayout(section_id="info", title="Info", order=1),
        ],
        review_fields=[
            ReviewFieldLayout(field_id="name", section_id="info", row=0, column=0),
            ReviewFieldLayout(field_id="age", section_id="info", row=1, column=0),
        ],
    )
    defaults.update(overrides)
    return TargetAppProfile(**defaults)


class _StubOCREngine:
    def __init__(self, text: str = "stub text", confidence: float = 0.85):
        self._text = text
        self._confidence = confidence

    def recognize(self, image):
        return self._text

    def confidence(self, image):
        return self._confidence

    def detect_regions(self, image):
        return [{"text": self._text, "confidence": self._confidence, "bbox": (0, 0, 10, 10)}]


class _StubVLM:
    def __init__(self, text: str = "vlm result", confidence: float = 0.92):
        self._text = text
        self._confidence = confidence
        self.calls = []

    def extract_field(self, image, field_id, prompt_hint=None):
        self.calls.append(field_id)
        return FieldExtraction(
            field_id=field_id,
            text=self._text,
            confidence=self._confidence,
            source="vlm",
        )


class TestCaptureService(unittest.TestCase):
    def test_capture_returns_none_when_no_window(self):
        automation = WindowsDesktopAutomation(window_provider=lambda: [])
        service = CaptureService(automation)
        profile = _make_profile()
        self.assertIsNone(service.capture(profile))

    def test_capture_returns_full_image_and_region_crops(self):
        window = DesktopWindow(
            title="App", executable_name="app.exe", class_name="Wnd",
            left=0, top=0, width=200, height=100,
        )
        automation = WindowsDesktopAutomation(
            window_provider=lambda: [window],
            screenshotter=lambda r: _white_image(),
        )
        profile = _make_profile(
            capture_regions=[
                CaptureRegion(region_id="name_region", label="Name", x=10, y=10, width=50, height=20, field_id="name"),
            ],
        )
        result = CaptureService(automation).capture(profile)

        self.assertIsNotNone(result)
        self.assertEqual(result.window.title, "App")
        self.assertEqual(result.full_image.shape, (100, 200, 3))
        self.assertIn("name", result.region_images)
        self.assertEqual(result.region_images["name"].shape, (20, 50, 3))

    def test_capture_masks_overlay_region(self):
        window = DesktopWindow(
            title="App", executable_name="app.exe", class_name="Wnd",
            left=0, top=0, width=200, height=100,
        )
        automation = WindowsDesktopAutomation(
            window_provider=lambda: [window],
            screenshotter=lambda r: _white_image(),
        )
        overlay = RegionLocator(x=0, y=0, width=50, height=30)
        result = CaptureService(automation, overlay_region=overlay).capture(_make_profile())

        self.assertTrue((result.full_image[0:30, 0:50] == 0).all())
        self.assertTrue((result.full_image[30:, :] == 255).all())


class TestPerceptionService(unittest.TestCase):
    def test_extract_collects_per_field_text_and_confidence(self):
        ocr = _StubOCREngine(text="Alice", confidence=0.90)
        service = PerceptionService(ocr)
        result = service.extract(
            _white_image(),
            region_images={"name": _white_image(20, 50)},
        )

        self.assertEqual(result.full_text, "Alice")
        self.assertIn("name", result.field_extractions)
        self.assertEqual(result.field_extractions["name"].text, "Alice")
        self.assertEqual(result.field_extractions["name"].confidence, 0.90)
        self.assertEqual(result.warnings, [])

    def test_low_confidence_triggers_warning(self):
        ocr = _StubOCREngine(text="?", confidence=0.40)
        service = PerceptionService(ocr, confidence_threshold=0.70)
        result = service.extract(
            _white_image(),
            region_images={"name": _white_image(20, 50)},
        )

        self.assertTrue(any("Low OCR" in w for w in result.warnings))

    def test_vlm_escalation_on_low_confidence(self):
        ocr = _StubOCREngine(text="?", confidence=0.40)
        vlm = _StubVLM(text="Alice Chen", confidence=0.95)
        service = PerceptionService(ocr, vlm_adapter=vlm, confidence_threshold=0.70)
        result = service.extract(
            _white_image(),
            region_images={"name": _white_image(20, 50)},
        )

        self.assertEqual(result.field_extractions["name"].text, "Alice Chen")
        self.assertEqual(result.field_extractions["name"].source, "vlm")
        self.assertIn("name", vlm.calls)

    def test_vlm_not_called_when_confidence_is_high(self):
        ocr = _StubOCREngine(text="Alice", confidence=0.90)
        vlm = _StubVLM()
        service = PerceptionService(ocr, vlm_adapter=vlm, confidence_threshold=0.70)
        service.extract(
            _white_image(),
            region_images={"name": _white_image(20, 50)},
        )

        self.assertEqual(vlm.calls, [])


class TestSchemaMapper(unittest.TestCase):
    def test_map_creates_case_with_extracted_fields(self):
        from treatment_app.services.perception_service import PerceptionResult

        perception = PerceptionResult(
            full_text="Alice 42",
            full_confidence=0.88,
            field_extractions={
                "name": FieldExtraction(field_id="name", text="Alice", confidence=0.95, source="ocr"),
                "age": FieldExtraction(field_id="age", text="42", confidence=0.90, source="ocr"),
            },
        )
        profile = _make_profile()
        mapper = SchemaMapper()
        case = mapper.map(perception, profile, case_id="c-001")

        self.assertEqual(case.case_id, "c-001")
        fields = case.field_map()
        self.assertEqual(fields["name"].value, "Alice")
        self.assertEqual(fields["age"].value, 42)

    def test_low_confidence_field_is_blocked(self):
        from treatment_app.services.perception_service import PerceptionResult

        perception = PerceptionResult(
            full_text="",
            full_confidence=0.50,
            field_extractions={
                "name": FieldExtraction(field_id="name", text="?", confidence=0.30, source="ocr"),
            },
        )
        mapper = SchemaMapper(low_confidence_threshold=0.70)
        case = mapper.map(perception, _make_profile())

        fields = case.field_map()
        self.assertEqual(fields["name"].review_state, FieldReviewState.BLOCKED)

    def test_missing_extraction_leaves_field_value_none(self):
        from treatment_app.services.perception_service import PerceptionResult

        perception = PerceptionResult(full_text="", full_confidence=0.0)
        case = SchemaMapper().map(perception, _make_profile())

        fields = case.field_map()
        self.assertIsNone(fields["name"].value)
        self.assertIsNone(fields["age"].value)


class TestCoerce(unittest.TestCase):
    def test_coerce_integer(self):
        self.assertEqual(_coerce("42", FieldKind.INTEGER), 42)

    def test_coerce_integer_fallback(self):
        self.assertEqual(_coerce("not-a-number", FieldKind.INTEGER), "not-a-number")

    def test_coerce_decimal(self):
        self.assertAlmostEqual(_coerce("3.14", FieldKind.DECIMAL), 3.14)

    def test_coerce_boolean_yes(self):
        self.assertTrue(_coerce("yes", FieldKind.BOOLEAN))

    def test_coerce_boolean_no(self):
        self.assertFalse(_coerce("no", FieldKind.BOOLEAN))

    def test_coerce_list(self):
        self.assertEqual(_coerce("a, b, c", FieldKind.LIST), ["a", "b", "c"])

    def test_coerce_empty(self):
        self.assertIsNone(_coerce("", FieldKind.TEXT))

    def test_coerce_text(self):
        self.assertEqual(_coerce("hello world", FieldKind.TEXT), "hello world")


if __name__ == "__main__":
    unittest.main()
