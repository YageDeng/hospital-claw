"""Tests for backend API adapter, remote LLM adapter, and form filler."""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from treatment_app.adapters.backend_api import HTTPBackendAPI
from treatment_app.adapters.remote_llm import RemoteLLMAdapter
from treatment_app.schemas import (
    AnchorLocator,
    CaseField,
    CaseSection,
    ControlLocator,
    FieldDefinition,
    FieldKind,
    FieldLocator,
    FieldOrigin,
    FieldReviewState,
    RegionLocator,
    ReviewControlType,
    ReviewFieldLayout,
    ReviewSectionLayout,
    TargetAppProfile,
    TreatmentPlanCase,
    WindowMatcher,
)
from treatment_app.services.form_filler import FillResult, FillStatus, FormFiller
from treatment_app.shared.windows import DesktopWindow, WindowsDesktopAutomation


# ── Fake HTTP client ──────────────────────────────────────────────────


class FakeResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def json(self):
        return self._data


class FakeHTTPClient:
    def __init__(self, responses=None):
        self.calls = []
        self._responses = list(responses or [])
        self._idx = 0

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self._idx < len(self._responses):
            resp = self._responses[self._idx]
            self._idx += 1
            return resp
        return FakeResponse({"ok": True})


# ── Fake LLM client ──────────────────────────────────────────────────


class FakeLLMClient:
    def __init__(self, response=None):
        self.calls = []
        self._response = response or {}

    def complete(self, payload):
        self.calls.append(payload)
        return self._response


class FailingLLMClient:
    def __init__(self, fail_count=1, then_response=None):
        self._fail_count = fail_count
        self._then_response = then_response or {}
        self._call_count = 0

    def complete(self, payload):
        self._call_count += 1
        if self._call_count <= self._fail_count:
            raise ConnectionError("network error")
        return self._then_response


# ── Tests ─────────────────────────────────────────────────────────────


class TestHTTPBackendAPI(unittest.TestCase):
    def test_fetch_patient_sends_get(self):
        client = FakeHTTPClient([FakeResponse({"name": "Alice"})])
        api = HTTPBackendAPI("http://localhost:8080/api", http_client=client)
        result = api.fetch_patient("P001")

        self.assertEqual(result, {"name": "Alice"})
        self.assertEqual(client.calls[0][0], "GET")
        self.assertIn("/patients/P001", client.calls[0][1])

    def test_submit_case_sends_post(self):
        client = FakeHTTPClient([FakeResponse({"id": "C001"})])
        api = HTTPBackendAPI("http://localhost:8080/api", http_client=client)
        result = api.submit_case({"caseId": "c-001"})

        self.assertEqual(result, {"id": "C001"})
        self.assertEqual(client.calls[0][0], "POST")

    def test_retries_on_failure(self):
        client = FakeHTTPClient([
            FakeResponse({}, status_code=500),
            FakeResponse({"ok": True}),
        ])
        api = HTTPBackendAPI(
            "http://localhost:8080/api",
            http_client=client,
            max_retries=2,
            backoff=0.01,
        )
        result = api.fetch_patient("P001")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(client.calls), 2)

    def test_raises_after_max_retries(self):
        client = FakeHTTPClient([
            FakeResponse({}, status_code=500),
            FakeResponse({}, status_code=500),
        ])
        api = HTTPBackendAPI(
            "http://localhost:8080/api",
            http_client=client,
            max_retries=2,
            backoff=0.01,
        )
        with self.assertRaises(RuntimeError):
            api.fetch_patient("P001")


class TestRemoteLLMAdapter(unittest.TestCase):
    def _make_case(self):
        return TreatmentPlanCase(
            case_id="c-001",
            profile_id="demo",
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
                            value="Original",
                        )
                    ],
                )
            ],
        )

    def test_successful_optimization(self):
        llm = FakeLLMClient({
            "caseId": "c-001",
            "profileId": "demo",
            "optimizedFields": {"diagnosis": "Qi stagnation"},
            "warnings": [],
        })
        adapter = RemoteLLMAdapter(llm)
        case = self._make_case()
        result = adapter.optimize(case)

        self.assertEqual(result.field_map()["diagnosis"].value, "Qi stagnation")
        self.assertEqual(len(llm.calls), 1)

    def test_rejects_invalid_response_and_retries(self):
        llm = FakeLLMClient({"bad": "response"})
        adapter = RemoteLLMAdapter(llm, max_retries=2, backoff=0.01)

        with self.assertRaises(ValueError):
            adapter.optimize(self._make_case())
        self.assertEqual(len(llm.calls), 2)

    def test_retries_on_network_error(self):
        llm = FailingLLMClient(
            fail_count=1,
            then_response={
                "caseId": "c-001",
                "profileId": "demo",
                "optimizedFields": {"diagnosis": "Fixed"},
                "warnings": [],
            },
        )
        adapter = RemoteLLMAdapter(llm, max_retries=3, backoff=0.01)
        case = self._make_case()
        result = adapter.optimize(case)

        self.assertEqual(result.field_map()["diagnosis"].value, "Fixed")

    def test_adds_empty_warnings_if_missing(self):
        llm = FakeLLMClient({
            "caseId": "c-001",
            "profileId": "demo",
            "optimizedFields": {"diagnosis": "OK"},
        })
        adapter = RemoteLLMAdapter(llm)
        case = self._make_case()
        result = adapter.optimize(case)

        self.assertEqual(result.warnings, [])


class TestFormFiller(unittest.TestCase):
    def _make_case_and_profile(self):
        case = TreatmentPlanCase(
            case_id="c-fill",
            profile_id="fill-demo",
            sections=[
                CaseSection(
                    section_id="info",
                    title="Info",
                    fields=[
                        CaseField(
                            field_id="name",
                            label="Name",
                            section_id="info",
                            field_type=FieldKind.TEXT,
                            value="Alice",
                            review_state=FieldReviewState.APPROVED,
                        ),
                        CaseField(
                            field_id="age",
                            label="Age",
                            section_id="info",
                            field_type=FieldKind.INTEGER,
                            value=42,
                            review_state=FieldReviewState.APPROVED,
                        ),
                        CaseField(
                            field_id="notes",
                            label="Notes",
                            section_id="info",
                            field_type=FieldKind.TEXT,
                            value="Blocked field",
                            review_state=FieldReviewState.BLOCKED,
                        ),
                    ],
                )
            ],
        )
        profile = TargetAppProfile(
            profile_id="fill-demo",
            name="Fill Demo",
            window_matchers=[WindowMatcher(executable_names=["app.exe"])],
            field_definitions=[
                FieldDefinition(field_id="name", label="Name", section_id="info",
                                field_type=FieldKind.TEXT, review_control=ReviewControlType.SINGLE_LINE),
                FieldDefinition(field_id="age", label="Age", section_id="info",
                                field_type=FieldKind.INTEGER, review_control=ReviewControlType.SINGLE_LINE),
                FieldDefinition(field_id="notes", label="Notes", section_id="info",
                                field_type=FieldKind.TEXT, review_control=ReviewControlType.SINGLE_LINE),
            ],
            review_sections=[ReviewSectionLayout(section_id="info", title="Info", order=1)],
            review_fields=[
                ReviewFieldLayout(field_id="name", section_id="info", row=0, column=0),
                ReviewFieldLayout(field_id="age", section_id="info", row=1, column=0),
                ReviewFieldLayout(field_id="notes", section_id="info", row=2, column=0),
            ],
            fill_locators={
                "name": FieldLocator(fill_order=1, region=RegionLocator(x=10, y=20, width=100, height=24)),
                "age": FieldLocator(fill_order=2, region=RegionLocator(x=10, y=50, width=100, height=24)),
            },
        )
        return case, profile

    def test_fills_approved_fields_in_order(self):
        clicked = []
        automation = WindowsDesktopAutomation(clicker=lambda x, y: clicked.append((x, y)))
        filler = FormFiller(automation, typer=lambda v: None, inter_field_delay=0.0)
        case, profile = self._make_case_and_profile()
        window = DesktopWindow(
            title="App", executable_name="app.exe", class_name="W",
            left=100, top=200, width=800, height=600,
        )

        result = filler.fill(case, profile, window)

        filled_ids = [r.field_id for r in result.records if r.status == FillStatus.SUCCESS]
        self.assertEqual(filled_ids, ["name", "age"])

    def test_blocked_fields_not_filled(self):
        automation = WindowsDesktopAutomation(clicker=lambda x, y: None)
        filler = FormFiller(automation, inter_field_delay=0.0)
        case, profile = self._make_case_and_profile()
        window = DesktopWindow(
            title="App", executable_name="app.exe", class_name="W",
            left=0, top=0, width=800, height=600,
        )

        result = filler.fill(case, profile, window)

        blocked = [r for r in result.records if r.field_id == "notes"]
        self.assertEqual(blocked, [])

    def test_no_locator_skips_field(self):
        case = TreatmentPlanCase(
            case_id="c-skip",
            profile_id="fill-demo",
            sections=[
                CaseSection(
                    section_id="info",
                    title="Info",
                    fields=[
                        CaseField(
                            field_id="name",
                            label="Name",
                            section_id="info",
                            field_type=FieldKind.TEXT,
                            value="Bob",
                            review_state=FieldReviewState.APPROVED,
                        ),
                    ],
                )
            ],
        )
        profile = TargetAppProfile(
            profile_id="fill-demo",
            name="Fill Demo",
            window_matchers=[WindowMatcher(executable_names=["app.exe"])],
            field_definitions=[
                FieldDefinition(field_id="name", label="Name", section_id="info",
                                field_type=FieldKind.TEXT, review_control=ReviewControlType.SINGLE_LINE),
            ],
            review_sections=[ReviewSectionLayout(section_id="info", title="Info", order=1)],
            review_fields=[
                ReviewFieldLayout(field_id="name", section_id="info", row=0, column=0),
            ],
            fill_locators={},
        )
        automation = WindowsDesktopAutomation(clicker=lambda x, y: None)
        filler = FormFiller(automation, inter_field_delay=0.0)
        window = DesktopWindow(
            title="App", executable_name="app.exe", class_name="W",
            left=0, top=0, width=800, height=600,
        )

        result = filler.fill(case, profile, window)

        self.assertEqual(result.records[0].status, FillStatus.SKIPPED)
        self.assertEqual(result.records[0].error, "no locator defined")

    def test_empty_approved_returns_empty_result(self):
        case = TreatmentPlanCase(
            case_id="c-empty",
            profile_id="fill-demo",
            sections=[
                CaseSection(
                    section_id="info",
                    title="Info",
                    fields=[
                        CaseField(
                            field_id="name",
                            label="Name",
                            section_id="info",
                            field_type=FieldKind.TEXT,
                            value="",
                            review_state=FieldReviewState.APPROVED,
                        ),
                    ],
                )
            ],
        )
        profile = TargetAppProfile(
            profile_id="fill-demo",
            name="Fill Demo",
            window_matchers=[WindowMatcher(executable_names=["app.exe"])],
            field_definitions=[
                FieldDefinition(field_id="name", label="Name", section_id="info",
                                field_type=FieldKind.TEXT, review_control=ReviewControlType.SINGLE_LINE),
            ],
            review_sections=[ReviewSectionLayout(section_id="info", title="Info", order=1)],
            review_fields=[
                ReviewFieldLayout(field_id="name", section_id="info", row=0, column=0),
            ],
        )
        automation = WindowsDesktopAutomation(clicker=lambda x, y: None)
        filler = FormFiller(automation, inter_field_delay=0.0)
        window = DesktopWindow(
            title="App", executable_name="app.exe", class_name="W",
            left=0, top=0, width=800, height=600,
        )

        result = filler.fill(case, profile, window)
        self.assertEqual(len(result.records), 0)


if __name__ == "__main__":
    unittest.main()
