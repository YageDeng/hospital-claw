"""Supplementary tests for skill_e2e_matrix with Gemma focus."""

from __future__ import annotations

from pathlib import Path

import pytest

from skill_e2e_matrix import (
    ScenarioResult,
    SkillE2EContext,
    build_default_context,
    list_scenarios,
    select_scenarios,
)


def test_build_default_context_artifact_root(tmp_path: Path):
    """build_default_context should create the artifact root directory."""
    ctx = build_default_context(
        workspace_root=tmp_path,
        artifact_root=tmp_path / "my_artifacts",
    )
    assert (tmp_path / "my_artifacts").exists()
    assert ctx.artifact_root == (tmp_path / "my_artifacts")


def test_context_scenario_dir(tmp_path: Path):
    """context.scenario_dir should create subdirectories as needed."""
    ctx = SkillE2EContext(
        workspace_root=tmp_path,
        artifact_root=tmp_path / "artifacts",
    )
    d1 = ctx.scenario_dir("scenario-alpha")
    d2 = ctx.scenario_dir("scenario-beta")
    assert d1 == tmp_path / "artifacts" / "scenario-alpha"
    assert d2 == tmp_path / "artifacts" / "scenario-beta"
    assert d1.exists()
    assert d2.exists()


def test_scenario_result_to_dict():
    """ScenarioResult.to_dict should serialise all fields."""
    result = ScenarioResult(
        scenario_id="my-scenario",
        skill_id="my-skill",
        status="PASS",
        summary="All checks passed",
        details=["detail one", "detail two"],
        artifacts=[Path("/tmp/out.md")],
        live=True,
        optional_probe=False,
    )
    d = result.to_dict()
    assert d["scenario_id"] == "my-scenario"
    assert d["skill_id"] == "my-skill"
    assert d["status"] == "PASS"
    assert d["live"] is True
    assert d["optional_probe"] is False
    assert len(d["details"]) == 2
    assert "out.md" in d["artifacts"][0]


def test_list_scenarios_returns_nonempty():
    """list_scenarios should return the full registry."""
    scenarios = list_scenarios(include_probes=False)
    assert len(scenarios) > 0
    ids = {s.scenario_id for s in scenarios}
    assert "review_db_local" in ids
    assert "tcm_treatment_plan_prereqs" in ids


def test_list_scenarios_with_probes_adds_two():
    """Enabling probes should add two optional scenarios."""
    without = list_scenarios(include_probes=False)
    with_probes = list_scenarios(include_probes=True)
    assert len(with_probes) == len(without) + 2
    probe_ids = {s.scenario_id for s in with_probes if s.optional_probe}
    assert "tcm_treatment_review_agent_probe" in probe_ids


def test_select_scenarios_unknown_raises():
    """select_scenarios should raise ValueError for unknown IDs."""
    with pytest.raises(ValueError, match="Unknown scenario"):
        select_scenarios(["nonexistent_scenario"])
