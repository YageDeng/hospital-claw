"""Tests for skill_e2e_probes.py."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from skill_e2e_probes import (
    ProbeOutcome,
    probes_enabled,
    probe_driver_command,
    run_agent_probe,
)


def test_probes_enabled_default():
    """Default environment should have probes disabled."""
    env = dict(os.environ)
    env.pop("SKILL_E2E_ENABLE_PROBES", None)
    assert probes_enabled(env) is False


def test_probes_enabled_explicit():
    """SKILL_E2E_ENABLE_PROBES=1 should enable probes."""
    env = {"SKILL_E2E_ENABLE_PROBES": "1"}
    assert probes_enabled(env) is True


def test_probes_enabled_false():
    """SKILL_E2E_ENABLE_PROBES=0 should disable probes."""
    env = {"SKILL_E2E_ENABLE_PROBES": "0"}
    assert probes_enabled(env) is False


def test_probe_driver_command_default():
    """Default environment should have no driver."""
    env = dict(os.environ)
    env.pop("SKILL_E2E_AGENT_DRIVER", None)
    assert probe_driver_command(env) is None


def test_probe_driver_command_explicit():
    """SKILL_E2E_AGENT_DRIVER should be returned."""
    env = {"SKILL_E2E_AGENT_DRIVER": "my-driver --arg {payload}"}
    assert probe_driver_command(env) == "my-driver --arg {payload}"


def test_run_agent_probe_skips_when_disabled():
    """Disabled probes should return SKIP immediately."""
    env = {"SKILL_E2E_ENABLE_PROBES": "0"}
    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_agent_probe(
            "test_probe",
            "Say hello",
            Path(tmpdir),
            env=env,
        )
    assert result.status == "SKIP"
    assert "disabled" in result.summary.lower()


def test_run_agent_probe_skips_without_driver():
    """No driver configured should return SKIP."""
    env = {"SKILL_E2E_ENABLE_PROBES": "1", "SKILL_E2E_AGENT_DRIVER": ""}
    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_agent_probe(
            "test_probe",
            "Say hello",
            Path(tmpdir),
            env=env,
        )
    assert result.status == "SKIP"
    assert "driver" in result.summary.lower()


def test_probe_outcome_defaults():
    """ProbeOutcome should have sensible defaults."""
    outcome = ProbeOutcome(status="PASS", summary="ok")
    assert outcome.details == []
    assert outcome.artifacts == []


def test_probe_outcome_full():
    """ProbeOutcome should hold all fields."""
    artifacts = [Path("/tmp/out.json")]
    outcome = ProbeOutcome(
        status="FAIL",
        summary="error",
        details=["detail 1"],
        artifacts=artifacts,
    )
    assert outcome.status == "FAIL"
    assert outcome.details == ["detail 1"]
    assert outcome.artifacts == artifacts
