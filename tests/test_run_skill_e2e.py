"""Tests for scripts/run_skill_e2e.py."""

from __future__ import annotations

import os
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from run_skill_e2e import (  # type: ignore[import-not-found]
    exit_code_from_results,
    main,
    render_markdown_report,
    summarize_results,
)
from skill_e2e_matrix import ScenarioResult


class TestRunSkillE2E(unittest.TestCase):
    def test_summarize_results_counts_statuses(self):
        results = [
            ScenarioResult(
                scenario_id="a",
                skill_id="skill-a",
                status="PASS",
                summary="ok",
            ),
            ScenarioResult(
                scenario_id="b",
                skill_id="skill-b",
                status="SKIP",
                summary="missing dependency",
            ),
            ScenarioResult(
                scenario_id="c",
                skill_id="skill-c",
                status="FAIL",
                summary="command failed",
            ),
        ]

        summary = summarize_results(results)

        self.assertEqual(summary["PASS"], 1)
        self.assertEqual(summary["SKIP"], 1)
        self.assertEqual(summary["FAIL"], 1)
        self.assertEqual(summary["total"], 3)

    def test_exit_code_is_zero_without_failures(self):
        results = [
            ScenarioResult("a", "skill-a", "PASS", "ok"),
            ScenarioResult("b", "skill-b", "SKIP", "not configured"),
        ]

        self.assertEqual(exit_code_from_results(results), 0)

    def test_exit_code_is_one_with_failures(self):
        results = [ScenarioResult("a", "skill-a", "FAIL", "broken")]

        self.assertEqual(exit_code_from_results(results), 1)

    def test_render_markdown_report_includes_counts_and_rows(self):
        results = [
            ScenarioResult("review_db_local", "tcm-treatment-review", "PASS", "db works"),
            ScenarioResult("wechat_daily_monitor_manual_url", "wechat-daily-monitor", "SKIP", "missing URL"),
        ]

        markdown = render_markdown_report(results)

        self.assertIn("# Skill E2E Report", markdown)
        self.assertIn("| PASS | 1 |", markdown)
        self.assertIn("| SKIP | 1 |", markdown)
        self.assertIn("review_db_local", markdown)
        self.assertIn("wechat_daily_monitor_manual_url", markdown)

    def test_render_markdown_report_escapes_table_breaking_summary_content(self):
        results = [
            ScenarioResult(
                "probe",
                "skill",
                "PASS",
                "line one | line two\nline three",
            )
        ]

        markdown = render_markdown_report(results)

        self.assertIn("line one \\| line two line three", markdown)

    def test_render_markdown_report_includes_labels_details_and_artifacts(self):
        results = [
            ScenarioResult(
                scenario_id="tcm_treatment_plan_prereqs",
                skill_id="tcm-treatment-plan",
                status="PASS",
                summary="Composite treatment-plan validation passed",
                details=[
                    "prereq: qmd=qmd 1.0.7",
                    "probe: external driver accepted the treatment plan",
                ],
                artifacts=[Path("data/skill_e2e/probe_payloads/tcm_treatment_plan_prereqs.json")],
                live=True,
                optional_probe=True,
            )
        ]

        markdown = render_markdown_report(results)

        self.assertIn("| Scenario | Skill | Status | Labels | Summary |", markdown)
        self.assertIn("| tcm_treatment_plan_prereqs | tcm-treatment-plan | PASS | live, probe | Composite treatment-plan validation passed |", markdown)
        self.assertIn("## Scenario Details", markdown)
        self.assertIn("### `tcm_treatment_plan_prereqs`", markdown)
        self.assertIn("prereq: qmd=qmd 1.0.7", markdown)
        self.assertIn("probe: external driver accepted the treatment plan", markdown)
        self.assertIn("data/skill_e2e/probe_payloads/tcm_treatment_plan_prereqs.json", markdown)

    def test_main_returns_non_zero_and_prints_message_for_unknown_scenario(self):
        stdout = StringIO()
        stderr = StringIO()

        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            exit_code = main(["--scenario", "missing_scenario"])

        self.assertEqual(exit_code, 1)
        self.assertIn("Unknown scenario", stderr.getvalue())

    def test_main_forwards_explicit_artifact_root_to_context_builder(self):
        fake_context = object()
        stdout = StringIO()
        artifact_root = Path("C:/repo/data/skill_e2e/runs/20260411-130231-456789")

        with patch("run_skill_e2e.build_default_context", return_value=fake_context) as build_context, patch(
            "run_skill_e2e.run_selected_scenarios",
            return_value=[],
        ), patch("sys.stdout", stdout):
            exit_code = main(["--artifact-root", str(artifact_root)])

        self.assertEqual(exit_code, 0)
        build_context.assert_called_once_with(
            allow_live=False,
            artifact_root=artifact_root,
        )


if __name__ == "__main__":
    unittest.main()
