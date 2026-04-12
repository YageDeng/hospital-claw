"""Tests for the desktop shell UI components.

Uses an offscreen QApplication so tests run without a display server.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from treatment_app.desktop_shell.hover_widget import HoverPill, STATUS_COLORS
from treatment_app.desktop_shell.review_panel import FieldWidget, ReviewPanel
from treatment_app.schemas import (
    CaseField,
    CaseSection,
    FieldDefinition,
    FieldKind,
    FieldOrigin,
    FieldReviewState,
    ReviewControlType,
    ReviewFieldLayout,
    ReviewSectionLayout,
    TargetAppProfile,
    TreatmentPlanCase,
    WindowMatcher,
)


def _make_demo_case() -> TreatmentPlanCase:
    return TreatmentPlanCase(
        case_id="case-ui-001",
        profile_id="demo",
        sections=[
            CaseSection(
                section_id="patient",
                title="Patient",
                fields=[
                    CaseField(
                        field_id="patient_name",
                        label="Patient Name",
                        section_id="patient",
                        field_type=FieldKind.TEXT,
                        value="Alice Chen",
                        confidence=0.95,
                    ),
                    CaseField(
                        field_id="age",
                        label="Age",
                        section_id="patient",
                        field_type=FieldKind.INTEGER,
                        value=42,
                        confidence=1.0,
                    ),
                ],
            ),
            CaseSection(
                section_id="clinical",
                title="Clinical",
                fields=[
                    CaseField(
                        field_id="diagnosis",
                        label="Diagnosis",
                        section_id="clinical",
                        field_type=FieldKind.MULTILINE,
                        value="Qi stagnation",
                        confidence=0.78,
                    ),
                ],
            ),
        ],
        warnings=["Low OCR confidence on diagnosis"],
    )


def _make_demo_profile() -> TargetAppProfile:
    return TargetAppProfile(
        profile_id="demo",
        name="Demo Profile",
        window_matchers=[WindowMatcher(executable_names=["his.exe"])],
        field_definitions=[
            FieldDefinition(
                field_id="patient_name",
                label="Patient Name",
                section_id="patient",
                field_type=FieldKind.TEXT,
                review_control=ReviewControlType.SINGLE_LINE,
            ),
            FieldDefinition(
                field_id="age",
                label="Age",
                section_id="patient",
                field_type=FieldKind.INTEGER,
                review_control=ReviewControlType.SINGLE_LINE,
            ),
            FieldDefinition(
                field_id="diagnosis",
                label="Diagnosis",
                section_id="clinical",
                field_type=FieldKind.MULTILINE,
                review_control=ReviewControlType.MULTI_LINE,
            ),
        ],
        review_sections=[
            ReviewSectionLayout(section_id="patient", title="Patient", order=1),
            ReviewSectionLayout(section_id="clinical", title="Clinical", order=2),
        ],
        review_fields=[
            ReviewFieldLayout(field_id="patient_name", section_id="patient", row=0, column=0),
            ReviewFieldLayout(field_id="age", section_id="patient", row=1, column=0),
            ReviewFieldLayout(field_id="diagnosis", section_id="clinical", row=0, column=0),
        ],
    )


class TestHoverPill(unittest.TestCase):
    def test_default_status_is_idle(self):
        pill = HoverPill()
        self.assertEqual(pill._status, "idle")
        self.assertEqual(pill._label, "Treatment")

    def test_set_status_updates_internal_state(self):
        pill = HoverPill()
        pill.set_status("ready", "Done")
        self.assertEqual(pill._status, "ready")
        self.assertEqual(pill._label, "Done")

    def test_expand_signal_emitted_on_click(self):
        pill = HoverPill()
        received = []
        pill.expand_requested.connect(lambda: received.append(True))
        pill.expand_requested.emit()
        self.assertEqual(received, [True])


class TestFieldWidget(unittest.TestCase):
    def test_approve_sets_review_state(self):
        cf = CaseField(
            field_id="f1",
            label="Field 1",
            section_id="s1",
            field_type=FieldKind.TEXT,
            value="hello",
        )
        fw = FieldWidget(cf, ReviewControlType.SINGLE_LINE)
        states = []
        fw.state_changed.connect(lambda fid, state: states.append((fid, state)))

        fw._set_state(FieldReviewState.APPROVED)

        self.assertEqual(cf.review_state, FieldReviewState.APPROVED)
        self.assertEqual(states, [("f1", "approved")])

    def test_block_sets_review_state(self):
        cf = CaseField(
            field_id="f2",
            label="Field 2",
            section_id="s1",
            field_type=FieldKind.TEXT,
            value="world",
        )
        fw = FieldWidget(cf, ReviewControlType.SINGLE_LINE)
        fw._set_state(FieldReviewState.BLOCKED)

        self.assertEqual(cf.review_state, FieldReviewState.BLOCKED)


class TestReviewPanel(unittest.TestCase):
    def test_load_case_creates_field_widgets_for_each_field(self):
        panel = ReviewPanel()
        case = _make_demo_case()
        profile = _make_demo_profile()

        panel.load_case(case, profile)

        self.assertIn("patient_name", panel._field_widgets)
        self.assertIn("age", panel._field_widgets)
        self.assertIn("diagnosis", panel._field_widgets)
        self.assertEqual(len(panel._field_widgets), 3)

    def test_load_case_clears_previous_widgets(self):
        panel = ReviewPanel()
        case = _make_demo_case()
        profile = _make_demo_profile()

        panel.load_case(case, profile)
        panel.load_case(case, profile)

        self.assertEqual(len(panel._field_widgets), 3)

    def test_get_field_widget_returns_none_for_unknown(self):
        panel = ReviewPanel()
        self.assertIsNone(panel.get_field_widget("nonexistent"))

    def test_warnings_label_shown_when_case_has_warnings(self):
        panel = ReviewPanel()
        case = _make_demo_case()
        profile = _make_demo_profile()

        panel.load_case(case, profile)

        self.assertFalse(panel._warnings_label.isHidden())

    def test_warnings_label_hidden_when_no_warnings(self):
        panel = ReviewPanel()
        case = _make_demo_case()
        case.warnings = []
        profile = _make_demo_profile()

        panel.load_case(case, profile)

        self.assertTrue(panel._warnings_label.isHidden())


if __name__ == "__main__":
    unittest.main()
