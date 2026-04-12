"""Tests for the Windows treatment app schema contracts."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from treatment_app.schemas import (
    AnchorLocator,
    CaseField,
    CaseSection,
    ControlLocator,
    FieldDefinition,
    FieldKind,
    FieldOrigin,
    FieldReviewState,
    FieldLocator,
    LocatorStrategy,
    RegionLocator,
    ReviewControlType,
    ReviewFieldLayout,
    ReviewSectionLayout,
    TargetAppProfile,
    TreatmentPlanCase,
    WindowMatcher,
)


class TestTreatmentAppSchemas(unittest.TestCase):
    def test_to_llm_payload_groups_values_by_section(self):
        case = TreatmentPlanCase(
            case_id="case-001",
            profile_id="demo-profile",
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
                            origin=FieldOrigin.EXTRACTED,
                            review_state=FieldReviewState.PENDING,
                            confidence=0.91,
                        ),
                        CaseField(
                            field_id="age",
                            label="Age",
                            section_id="patient",
                            field_type=FieldKind.INTEGER,
                            value=42,
                            origin=FieldOrigin.BACKEND,
                            review_state=FieldReviewState.PENDING,
                            confidence=1.0,
                        ),
                    ],
                ),
                CaseSection(
                    section_id="clinical",
                    title="Clinical Input",
                    fields=[
                        CaseField(
                            field_id="symptoms",
                            label="Symptoms",
                            section_id="clinical",
                            field_type=FieldKind.LIST,
                            value=["neck pain", "poor sleep"],
                            origin=FieldOrigin.EXTRACTED,
                            review_state=FieldReviewState.PENDING,
                            confidence=0.74,
                        )
                    ],
                ),
            ],
        )

        payload = case.to_llm_payload()

        self.assertEqual(payload["caseId"], "case-001")
        self.assertEqual(payload["profileId"], "demo-profile")
        self.assertEqual(
            payload["sections"],
            {
                "patient": {
                    "patient_name": "Alice Chen",
                    "age": 42,
                },
                "clinical": {
                    "symptoms": ["neck pain", "poor sleep"],
                },
            },
        )

    def test_approved_fill_values_skip_unapproved_and_blank_fields(self):
        case = TreatmentPlanCase(
            case_id="case-002",
            profile_id="demo-profile",
            sections=[
                CaseSection(
                    section_id="plan",
                    title="Plan",
                    fields=[
                        CaseField(
                            field_id="diagnosis",
                            label="Diagnosis",
                            section_id="plan",
                            field_type=FieldKind.TEXT,
                            value="Qi stagnation",
                            origin=FieldOrigin.LLM_GENERATED,
                            review_state=FieldReviewState.APPROVED,
                        ),
                        CaseField(
                            field_id="notes",
                            label="Notes",
                            section_id="plan",
                            field_type=FieldKind.MULTILINE,
                            value="",
                            origin=FieldOrigin.USER_EDITED,
                            review_state=FieldReviewState.APPROVED,
                        ),
                        CaseField(
                            field_id="warning",
                            label="Warning",
                            section_id="plan",
                            field_type=FieldKind.TEXT,
                            value="Needs review",
                            origin=FieldOrigin.INFERRED,
                            review_state=FieldReviewState.BLOCKED,
                        ),
                    ],
                )
            ],
        )

        self.assertEqual(case.approved_fill_values(), {"diagnosis": "Qi stagnation"})

    def test_apply_llm_response_updates_known_fields_and_resets_review_state(self):
        case = TreatmentPlanCase(
            case_id="case-003",
            profile_id="demo-profile",
            sections=[
                CaseSection(
                    section_id="plan",
                    title="Plan",
                    fields=[
                        CaseField(
                            field_id="diagnosis",
                            label="Diagnosis",
                            section_id="plan",
                            field_type=FieldKind.TEXT,
                            value="Initial value",
                            origin=FieldOrigin.EXTRACTED,
                            review_state=FieldReviewState.APPROVED,
                        ),
                        CaseField(
                            field_id="notes",
                            label="Notes",
                            section_id="plan",
                            field_type=FieldKind.MULTILINE,
                            value="Original note",
                            origin=FieldOrigin.USER_EDITED,
                            review_state=FieldReviewState.APPROVED,
                        ),
                    ],
                )
            ],
        )

        updated = case.apply_llm_response(
            {
                "caseId": "case-003",
                "profileId": "demo-profile",
                "optimizedFields": {
                    "diagnosis": "Qi stagnation",
                    "notes": "Focus on reducing pain and improving sleep.",
                },
                "warnings": ["Needs human verification"],
            }
        )

        fields = updated.field_map()
        self.assertEqual(fields["diagnosis"].value, "Qi stagnation")
        self.assertEqual(fields["diagnosis"].origin, FieldOrigin.LLM_GENERATED)
        self.assertEqual(fields["diagnosis"].review_state, FieldReviewState.PENDING)
        self.assertEqual(
            fields["notes"].value,
            "Focus on reducing pain and improving sleep.",
        )
        self.assertEqual(updated.warnings, ["Needs human verification"])

    def test_apply_llm_response_rejects_unknown_field(self):
        case = TreatmentPlanCase(
            case_id="case-004",
            profile_id="demo-profile",
            sections=[
                CaseSection(
                    section_id="plan",
                    title="Plan",
                    fields=[
                        CaseField(
                            field_id="diagnosis",
                            label="Diagnosis",
                            section_id="plan",
                            field_type=FieldKind.TEXT,
                        )
                    ],
                )
            ],
        )

        with self.assertRaisesRegex(ValueError, "unknown field_id 'missing'"):
            case.apply_llm_response(
                {
                    "caseId": "case-004",
                    "profileId": "demo-profile",
                    "optimizedFields": {"missing": "bad"},
                }
            )

    def test_apply_llm_response_rejects_null_warnings(self):
        case = TreatmentPlanCase(
            case_id="case-005",
            profile_id="demo-profile",
            sections=[
                CaseSection(
                    section_id="plan",
                    title="Plan",
                    fields=[
                        CaseField(
                            field_id="diagnosis",
                            label="Diagnosis",
                            section_id="plan",
                            field_type=FieldKind.TEXT,
                        )
                    ],
                )
            ],
        )

        with self.assertRaisesRegex(ValueError, "warnings must be a list"):
            case.apply_llm_response(
                {
                    "caseId": "case-005",
                    "profileId": "demo-profile",
                    "optimizedFields": {"diagnosis": "ok"},
                    "warnings": None,
                }
            )

        fields = case.field_map()
        self.assertIsNone(fields["diagnosis"].value)
        self.assertEqual(fields["diagnosis"].origin, FieldOrigin.EXTRACTED)

    def test_apply_llm_response_rejects_invalid_value_type(self):
        case = TreatmentPlanCase(
            case_id="case-006",
            profile_id="demo-profile",
            sections=[
                CaseSection(
                    section_id="patient",
                    title="Patient",
                    fields=[
                        CaseField(
                            field_id="age",
                            label="Age",
                            section_id="patient",
                            field_type=FieldKind.INTEGER,
                        )
                    ],
                )
            ],
        )

        with self.assertRaisesRegex(ValueError, "expects integer"):
            case.apply_llm_response(
                {
                    "caseId": "case-006",
                    "profileId": "demo-profile",
                    "optimizedFields": {"age": "42"},
                }
            )

    def test_apply_llm_response_does_not_partially_apply_invalid_payload(self):
        case = TreatmentPlanCase(
            case_id="case-007",
            profile_id="demo-profile",
            sections=[
                CaseSection(
                    section_id="plan",
                    title="Plan",
                    fields=[
                        CaseField(
                            field_id="diagnosis",
                            label="Diagnosis",
                            section_id="plan",
                            field_type=FieldKind.TEXT,
                            value="Original diagnosis",
                        ),
                        CaseField(
                            field_id="age",
                            label="Age",
                            section_id="plan",
                            field_type=FieldKind.INTEGER,
                            value=30,
                        ),
                    ],
                )
            ],
        )

        with self.assertRaisesRegex(ValueError, "expects integer"):
            case.apply_llm_response(
                {
                    "caseId": "case-007",
                    "profileId": "demo-profile",
                    "optimizedFields": {
                        "diagnosis": "Updated diagnosis",
                        "age": "bad-age",
                    },
                }
            )

        fields = case.field_map()
        self.assertEqual(fields["diagnosis"].value, "Original diagnosis")
        self.assertEqual(fields["diagnosis"].origin, FieldOrigin.EXTRACTED)
        self.assertEqual(fields["age"].value, 30)

    def test_profile_validation_rejects_unknown_field_in_review_layout(self):
        with self.assertRaisesRegex(ValueError, "unknown field_id 'missing_field'"):
            TargetAppProfile(
                profile_id="profile-001",
                name="Demo Profile",
                window_matchers=[WindowMatcher(executable_names=["demo.exe"])],
                field_definitions=[
                    FieldDefinition(
                        field_id="patient_name",
                        label="Patient Name",
                        section_id="patient",
                        field_type=FieldKind.TEXT,
                        review_control=ReviewControlType.SINGLE_LINE,
                    )
                ],
                review_sections=[
                    ReviewSectionLayout(section_id="patient", title="Patient", order=1)
                ],
                review_fields=[
                    ReviewFieldLayout(
                        field_id="missing_field",
                        section_id="patient",
                        row=0,
                        column=0,
                    )
                ],
            ).validate()

    def test_profile_validation_rejects_duplicate_fill_order(self):
        with self.assertRaisesRegex(ValueError, "duplicate fill order"):
            TargetAppProfile(
                profile_id="profile-002",
                name="Demo Profile",
                window_matchers=[WindowMatcher(executable_names=["demo.exe"])],
                field_definitions=[
                    FieldDefinition(
                        field_id="patient_name",
                        label="Patient Name",
                        section_id="patient",
                        field_type=FieldKind.TEXT,
                        review_control=ReviewControlType.SINGLE_LINE,
                    ),
                    FieldDefinition(
                        field_id="symptoms",
                        label="Symptoms",
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
                    ReviewFieldLayout(field_id="symptoms", section_id="clinical", row=0, column=0),
                ],
                fill_locators={
                    "patient_name": FieldLocator(
                        fill_order=1,
                        region=RegionLocator(x=10, y=20, width=100, height=24),
                    ),
                    "symptoms": FieldLocator(
                        fill_order=1,
                        anchor=AnchorLocator(text="Symptoms", offset_x=20, offset_y=0),
                    ),
                },
            ).validate()

    def test_profile_validation_rejects_duplicate_review_sections(self):
        with self.assertRaisesRegex(ValueError, "duplicate review section"):
            TargetAppProfile(
                profile_id="profile-003",
                name="Demo Profile",
                window_matchers=[WindowMatcher(executable_names=["demo.exe"])],
                field_definitions=[
                    FieldDefinition(
                        field_id="patient_name",
                        label="Patient Name",
                        section_id="patient",
                        field_type=FieldKind.TEXT,
                        review_control=ReviewControlType.SINGLE_LINE,
                    )
                ],
                review_sections=[
                    ReviewSectionLayout(section_id="patient", title="Patient", order=1),
                    ReviewSectionLayout(section_id="patient", title="Patient Duplicate", order=2),
                ],
                review_fields=[
                    ReviewFieldLayout(field_id="patient_name", section_id="patient", row=0, column=0)
                ],
            ).validate()

    def test_profile_validation_rejects_field_definition_without_review_section(self):
        with self.assertRaisesRegex(ValueError, "field definition section 'clinical'"):
            TargetAppProfile(
                profile_id="profile-004",
                name="Demo Profile",
                window_matchers=[WindowMatcher(executable_names=["demo.exe"])],
                field_definitions=[
                    FieldDefinition(
                        field_id="symptoms",
                        label="Symptoms",
                        section_id="clinical",
                        field_type=FieldKind.MULTILINE,
                        review_control=ReviewControlType.MULTI_LINE,
                    )
                ],
                review_sections=[
                    ReviewSectionLayout(section_id="patient", title="Patient", order=1)
                ],
                review_fields=[],
            ).validate()

    def test_profile_validation_rejects_dynamic_only_locator(self):
        with self.assertRaisesRegex(ValueError, "must define at least one stable locator"):
            TargetAppProfile(
                profile_id="profile-005",
                name="Demo Profile",
                window_matchers=[WindowMatcher(executable_names=["demo.exe"])],
                field_definitions=[
                    FieldDefinition(
                        field_id="diagnosis",
                        label="Diagnosis",
                        section_id="plan",
                        field_type=FieldKind.TEXT,
                        review_control=ReviewControlType.SINGLE_LINE,
                    )
                ],
                review_sections=[
                    ReviewSectionLayout(section_id="plan", title="Plan", order=1)
                ],
                review_fields=[
                    ReviewFieldLayout(field_id="diagnosis", section_id="plan", row=0, column=0)
                ],
                fill_locators={
                    "diagnosis": FieldLocator(fill_order=1, allow_dynamic_fallback=True)
                },
            ).validate()

    def test_profile_validation_requires_layout_for_each_field_definition(self):
        with self.assertRaisesRegex(ValueError, "missing review layout"):
            TargetAppProfile(
                profile_id="profile-006",
                name="Demo Profile",
                window_matchers=[WindowMatcher(executable_names=["demo.exe"])],
                field_definitions=[
                    FieldDefinition(
                        field_id="diagnosis",
                        label="Diagnosis",
                        section_id="plan",
                        field_type=FieldKind.TEXT,
                        review_control=ReviewControlType.SINGLE_LINE,
                    )
                ],
                review_sections=[
                    ReviewSectionLayout(section_id="plan", title="Plan", order=1)
                ],
                review_fields=[],
            ).validate()

    def test_profile_validation_rejects_duplicate_review_field_entries(self):
        with self.assertRaisesRegex(ValueError, "duplicate review layout"):
            TargetAppProfile(
                profile_id="profile-007",
                name="Demo Profile",
                window_matchers=[WindowMatcher(executable_names=["demo.exe"])],
                field_definitions=[
                    FieldDefinition(
                        field_id="diagnosis",
                        label="Diagnosis",
                        section_id="plan",
                        field_type=FieldKind.TEXT,
                        review_control=ReviewControlType.SINGLE_LINE,
                    )
                ],
                review_sections=[
                    ReviewSectionLayout(section_id="plan", title="Plan", order=1)
                ],
                review_fields=[
                    ReviewFieldLayout(field_id="diagnosis", section_id="plan", row=0, column=0),
                    ReviewFieldLayout(field_id="diagnosis", section_id="plan", row=1, column=0),
                ],
            ).validate()

    def test_locator_priority_prefers_stable_strategies(self):
        locator = FieldLocator(
            fill_order=3,
            control=ControlLocator(automation_id="txtDiagnosis", control_type="Edit"),
            anchor=AnchorLocator(text="Diagnosis", offset_x=25, offset_y=4),
            region=RegionLocator(x=100, y=200, width=260, height=32),
            allow_dynamic_fallback=True,
        )

        self.assertEqual(
            locator.ordered_strategies(),
            [
                LocatorStrategy.UI_CONTROL,
                LocatorStrategy.ANCHOR,
                LocatorStrategy.REGION,
                LocatorStrategy.DYNAMIC,
            ],
        )


if __name__ == "__main__":
    unittest.main()
