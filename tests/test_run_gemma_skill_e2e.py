"""Tests for run_gemma_skill_e2e.py."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from skill_e2e_matrix import ScenarioResult


class GemmaClientForTest:
    """Test double that records calls instead of calling Ollama."""

    def __init__(self, base_url: str, model: str, **kwargs) -> None:
        self.base_url = base_url
        self.model = model
        self.calls = []
        self._response_text = "Test response from Gemma mock"

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls.append({"prompt": prompt, "system": system})
        return self._response_text

    def is_available(self) -> bool:
        return True

    def set_response(self, text: str) -> None:
        self._response_text = text


def test_gemma_client_records_calls():
    """GemmaClient should record every complete() call."""
    from run_gemma_skill_e2e import GemmaClient

    client = GemmaClientForTest(base_url="http://localhost:11434", model="gemma3:4b")
    result = client.complete("Hello, Gemma", system="You are a doctor.")
    assert result == "Test response from Gemma mock"
    assert len(client.calls) == 1
    assert client.calls[0]["prompt"] == "Hello, Gemma"
    assert client.calls[0]["system"] == "You are a doctor."


def test_gemma_client_is_available():
    """is_available() should return True for the test double."""
    from run_gemma_skill_e2e import GemmaClient

    client = GemmaClientForTest(base_url="http://localhost:11434", model="gemma3:4b")
    assert client.is_available() is True


def test_summarize_results_empty():
    """summarize_results should return zeros for empty input."""
    from run_gemma_skill_e2e import summarize_results

    summary = summarize_results([])
    assert summary == {"PASS": 0, "FAIL": 0, "SKIP": 0, "total": 0}


def test_summarize_results_mixed():
    """summarize_results should count each status correctly."""
    from run_gemma_skill_e2e import summarize_results

    results = [
        ScenarioResult(scenario_id="s1", skill_id="skill-a", status="PASS", summary="ok"),
        ScenarioResult(scenario_id="s2", skill_id="skill-b", status="FAIL", summary="error"),
        ScenarioResult(scenario_id="s3", skill_id="skill-a", status="SKIP", summary="skipped"),
        ScenarioResult(scenario_id="s4", skill_id="skill-c", status="PASS", summary="ok"),
    ]
    summary = summarize_results(results)
    assert summary == {"PASS": 2, "FAIL": 1, "SKIP": 1, "total": 4}


def test_escape_md():
    """_escape_md should strip newlines and escape pipes."""
    from run_gemma_skill_e2e import _escape_md

    assert _escape_md("hello\nworld") == "hello world"
    assert _escape_md("a | b | c") == r"a \| b \| c"
    assert _escape_md("  spaces  ") == "spaces"


def test_render_markdown_report_smoke():
    """render_markdown_report should produce a valid Markdown table."""
    from run_gemma_skill_e2e import GemmaClient, render_markdown_report

    results = [
        ScenarioResult(
            scenario_id="test_scenario",
            skill_id="test-skill",
            status="PASS",
            summary="All good",
        ),
    ]
    client = GemmaClientForTest(base_url="http://localhost:11434", model="gemma3:4b")
    report = render_markdown_report(results, client, elapsed_seconds=12.5)
    assert "# Gemma Skill E2E Evaluation Report" in report
    assert "gemma3:4b" in report
    assert "12.5s" in report
    assert "| PASS   | 1 |" in report
    assert "test_scenario" in report


def test_write_json_report_creates_file():
    """write_json_report should create the output file with correct content."""
    from run_gemma_skill_e2e import write_json_report

    results = [
        ScenarioResult(scenario_id="s1", skill_id="sk", status="PASS", summary="ok"),
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "report.json"
        write_json_report(path, results, model="gemma3:4b")
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["model"] == "gemma3:4b"
        assert data["summary"]["total"] == 1
        assert data["summary"]["PASS"] == 1
