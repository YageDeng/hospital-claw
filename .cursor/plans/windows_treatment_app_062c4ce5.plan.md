---
name: Windows Treatment App
overview: Design and implementation plan for a Python-packaged Windows desktop app that captures treatment-plan forms, normalizes them into structured JSON, optimizes them through remote services, and fills target apps field-by-field after operator review.
todos:
  - id: define-schemas
    content: Define the canonical treatment-plan JSON contract and the target-app profile schema, including review layout and fill locators.
    status: completed
  - id: extract-shared-automation
    content: Refactor reusable OCR/window automation pieces from `wechat-router` into shared modules the desktop app can consume.
    status: completed
  - id: build-shell-ui
    content: Build the PySide6 hover widget and expandable review surface that renders fields in a source-app-like layout.
    status: completed
  - id: implement-capture-pipeline
    content: Implement screen/window capture, OCR-first extraction, confidence handling, and schema mapping into structured case JSON.
    status: completed
  - id: add-remote-adapters
    content: Add backend API/direct-DB adapters and remote LLM/VLM adapters with strict JSON validation and retries.
    status: completed
  - id: implement-form-filling
    content: Implement field-by-field filling with profile locators, fallback rules, and operator approval gates.
    status: completed
  - id: package-and-validate
    content: Package the app as a Windows `.exe` and validate with unit, integration, golden-sample, and smoke tests.
    status: pending
isProject: false
---

# Windows Treatment App

## Approved Direction
- Build a Python Windows desktop app packaged as a directly runnable `.exe`.
- Use a `PySide6` always-on-top hover widget with an expandable structured review panel.
- Keep the product multi-app, but make it profile-centric: each target app uses a generated-and-tuned profile for extraction, review rendering, and field filling.
- Send and receive structured JSON to the remote LLM; never rely on free-form text as the system contract.
- Show returned fields in a layout that mirrors the source app for review/edit, then fill the target app field-by-field after user approval.

## Reuse From Current Repo
- Reuse OCR abstractions from [wechat-router/src/ocr_engine.py](wechat-router/src/ocr_engine.py).
- Reuse window/capture patterns from [wechat-router/src/platform_adapter.py](wechat-router/src/platform_adapter.py).
- Reuse automation/navigation ideas from [wechat-router/src/navigator.py](wechat-router/src/navigator.py).
- Keep the new desktop app isolated from the existing `wechat-router` entrypoints, but factor shared OCR/automation helpers so both systems can use them.

## Target Architecture
- `desktop_shell`: hover widget, review panel, tray, hotkeys, run history.
- `capture_service`: capture active window/screen while excluding the app’s own overlay.
- `perception_service`: OCR-first pipeline with VLM escalation when confidence is low.
- `schema_mapper`: normalize extracted/backend values into a canonical `TreatmentPlanCase` JSON object.
- `integration_adapters`: `backend_api` first, optional `direct_db`, `remote_llm`, optional `remote_vlm`.
- `profile_system`: `field_schema`, `review_layout`, `capture_regions`, `fill_locators`, `fill_order`, bootstrap helper from sample captures.
- `form_filler`: fills approved fields back into target apps using locator priority: UI control -> anchor-relative -> saved region -> dynamic fallback.
- `audit_store`: local run history, warnings, confidence notes, final approved field values.

## Reliability Rules
- Treat every field independently: low-confidence or unmapped fields remain editable and are skipped from fill unless approved.
- Reject invalid/incomplete LLM JSON responses.
- Never start auto-fill unless the operator has reviewed the structured result.
- Log extraction source, edits, fill results, and profile version for each run.

## Suggested Implementation Slices
- Slice 1: define canonical case schema and app-profile schema; extract common OCR/window helpers.
- Slice 2: build the `PySide6` hover widget and structured review panel with mock data.
- Slice 3: implement capture + OCR/VLM extraction + schema mapping.
- Slice 4: add backend/LLM adapters and structured request/response validation.
- Slice 5: implement field-by-field filler and profile bootstrap helper from sample captures.
- Slice 6: package as `.exe`, add smoke tests, and validate against a controlled demo form plus one real target profile.
