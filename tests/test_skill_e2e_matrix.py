"""Tests for scripts/skill_e2e_matrix.py."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from skill_e2e_probes import ProbeOutcome  # type: ignore[import-not-found]
from skill_e2e_matrix import (  # type: ignore[import-not-found]
    ScenarioResult,
    _run_subprocess,
    _run_sh_yb_policy_monitor_live,
    _run_tcm_treatment_plan_prereqs,
    _run_wechat_daily_monitor_manual_url,
    build_default_context,
    list_scenarios,
    run_selected_scenarios,
    select_scenarios,
)


class TestSkillE2EMatrix(unittest.TestCase):
    def test_list_scenarios_excludes_optional_probes_by_default(self):
        scenario_ids = {scenario.scenario_id for scenario in list_scenarios()}

        self.assertIn("review_db_local", scenario_ids)
        self.assertIn("tcm_treatment_plan_prereqs", scenario_ids)
        self.assertIn("sh_yb_policy_monitor_live", scenario_ids)
        self.assertIn("knowledge_base_docs_live", scenario_ids)
        self.assertIn("knowledge_base_rules_live", scenario_ids)
        self.assertIn("wechat_daily_monitor_manual_url", scenario_ids)
        self.assertNotIn("tcm_treatment_plan_agent_probe", scenario_ids)

    def test_list_scenarios_can_include_optional_probes(self):
        scenario_ids = {
            scenario.scenario_id
            for scenario in list_scenarios(include_probes=True)
        }

        self.assertIn("tcm_treatment_review_agent_probe", scenario_ids)
        self.assertIn("wechat_daily_monitor_discovered_probe", scenario_ids)
        self.assertNotIn("tcm_treatment_plan_agent_probe", scenario_ids)

    def test_treatment_plan_main_scenario_runs_probe_with_richer_payload_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(__file__).resolve().parent.parent
            context = build_default_context(workspace_root, allow_live=False)
            context.artifact_root = Path(tmpdir).resolve() / "data" / "skill_e2e"
            context.artifact_root.mkdir(parents=True, exist_ok=True)
            context.environment = {
                "SKILL_E2E_ENABLE_PROBES": "1",
                "SKILL_E2E_AGENT_DRIVER": "python probe_driver.py",
            }
            qmd_run = subprocess.CompletedProcess(
                args=["qmd", "--version"],
                returncode=0,
                stdout="qmd 1.0.7\n",
                stderr="",
            )
            probe_outcome = ProbeOutcome(
                status="PASS",
                summary="probe ok",
                details=["stdout: plan accepted"],
                artifacts=[context.artifact_root / "probe_payloads" / "tcm_treatment_plan_prereqs.json"],
            )

            with patch("skill_e2e_matrix._command_exists", return_value=True), patch(
                "skill_e2e_matrix._run_subprocess", return_value=qmd_run
            ), patch(
                "skill_e2e_matrix.run_agent_probe", return_value=probe_outcome
            ) as run_probe:
                result = _run_tcm_treatment_plan_prereqs(context)

        self.assertEqual(result.status, "PASS")
        self.assertIn("prereq:", " ".join(result.details))
        self.assertIn("probe:", " ".join(result.details))
        payload = run_probe.call_args.args[3]
        self.assertEqual(
            payload["case_file"],
            str(context.fixture_root() / "tcm_plan_case.json"),
        )
        self.assertIn("患者信息", payload["required_sections"])
        self.assertIn("治疗方案", payload["required_sections"])
        self.assertIn("费用汇总", payload["required_sections"])
        self.assertIn("数据来源", payload["required_sections"])
        self.assertIn("chief_complaint", payload["required_patient_fields"])
        self.assertIn("optional_context", payload["required_patient_fields"])
        self.assertIn("单次费用", payload["expected_keywords"])
        self.assertIn("治疗频次", payload["expected_keywords"])

    def test_select_scenarios_raises_for_unknown_id(self):
        with self.assertRaises(ValueError):
            select_scenarios(["missing_scenario"])

    def test_build_default_context_uses_ignored_data_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            context = build_default_context(Path(tmpdir))

        self.assertEqual(context.workspace_root, Path(tmpdir).resolve())
        self.assertEqual(
            context.artifact_root,
            Path(tmpdir).resolve() / "data" / "skill_e2e",
        )

    def test_scenario_result_to_dict_preserves_core_fields(self):
        result = ScenarioResult(
            scenario_id="review_db_local",
            skill_id="tcm-treatment-review",
            status="PASS",
            summary="review pipeline works",
            details=["saved four rows"],
            artifacts=[Path("data/skill_e2e/review/report.md")],
        )

        payload = result.to_dict()

        self.assertEqual(payload["scenario_id"], "review_db_local")
        self.assertEqual(payload["skill_id"], "tcm-treatment-review")
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["artifacts"], ["data/skill_e2e/review/report.md"])

    def test_run_selected_scenarios_skips_live_scenarios_without_flag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            context = build_default_context(Path(tmpdir), allow_live=False)
            results = run_selected_scenarios(context, ["knowledge_base_rules_live"])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "SKIP")
        self.assertIn("--allow-live", results[0].summary)

    def test_run_selected_scenarios_executes_review_db_local(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(__file__).resolve().parent.parent
            context = build_default_context(workspace_root, allow_live=False)
            context.artifact_root = Path(tmpdir).resolve() / "data" / "skill_e2e"
            context.artifact_root.mkdir(parents=True, exist_ok=True)
            results = run_selected_scenarios(context, ["review_db_local"])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "PASS")
        self.assertIn("review_db CLI completed", results[0].summary)

    def test_discovered_probe_is_skipped_without_allow_live(self):
        context = build_default_context(allow_live=False)
        results = run_selected_scenarios(
            context,
            ["wechat_daily_monitor_discovered_probe"],
            include_probes=True,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "SKIP")
        self.assertIn("--allow-live", results[0].summary)

    def test_policy_monitor_live_fails_when_script_reports_fetch_errors(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            context = build_default_context(Path(tmpdir), allow_live=True)
            completed = subprocess.CompletedProcess(
                args=["python", "fetch_policies.py"],
                returncode=0,
                stdout="检查日期：2026-04-11\n",
                stderr="  ✗ 获取失败：timeout\n",
            )

            with patch("skill_e2e_matrix._module_available", return_value=True), patch(
                "skill_e2e_matrix._can_reach_url", return_value=True
            ), patch(
                "skill_e2e_matrix._run_python_script", return_value=completed
            ):
                result = _run_sh_yb_policy_monitor_live(context)

        self.assertEqual(result.status, "FAIL")
        self.assertIn("fetch errors", result.summary.lower())

    def test_wechat_manual_url_splits_multiline_env_input_into_multiple_pipeline_args(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            context = build_default_context(Path(tmpdir), allow_live=True)
            first_url = "https://mp.weixin.qq.com/s/first"
            second_url = "https://mp.weixin.qq.com/s/second"
            context.environment = {
                "SKILL_E2E_WECHAT_URL": f"{first_url}\n{second_url}",
            }
            completed = subprocess.CompletedProcess(
                args=["python", "wechat_article_pipeline.py"],
                returncode=1,
                stdout="",
                stderr="pipeline failed",
            )

            with patch("skill_e2e_matrix._command_exists", return_value=True), patch(
                "skill_e2e_matrix._can_reach_url", return_value=True
            ), patch(
                "skill_e2e_matrix._run_python_script", return_value=completed
            ) as run_python_script:
                result = _run_wechat_daily_monitor_manual_url(context)

        self.assertEqual(result.status, "FAIL")
        self.assertIn("pipeline failed", result.details[0])
        self.assertEqual(run_python_script.call_args.args[2], first_url)
        self.assertEqual(run_python_script.call_args.args[3], second_url)
        self.assertEqual(run_python_script.call_args.args[4], "--output-dir")

    def test_run_subprocess_resolves_windows_cmd_shims_from_path(self):
        if os.name != "nt":
            self.skipTest("Windows-specific command shim behavior")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            shim = root / "fakeqmd.cmd"
            shim.write_text("@echo off\r\necho fakeqmd %*\r\n", encoding="utf-8")
            env = dict(os.environ)
            env["PATH"] = str(root) + os.pathsep + env.get("PATH", "")

            completed = _run_subprocess(
                ["fakeqmd", "--version"],
                cwd=root,
                env=env,
                timeout=30,
            )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout.strip(), "fakeqmd --version")

    def test_run_subprocess_captures_bytes_and_decodes_itself(self):
        def fake_run(*args, **kwargs):
            self.assertFalse(kwargs["text"])
            return subprocess.CompletedProcess(
                args=kwargs.get("args", args[0] if args else []),
                returncode=0,
                stdout=b"\x93hello\n",
                stderr=b"",
            )

        with patch("skill_e2e_matrix.subprocess.run", side_effect=fake_run):
            completed = _run_subprocess(
                [sys.executable, "-c", "print('ignored')"],
                cwd=Path.cwd(),
                env=dict(os.environ),
                timeout=30,
            )

        self.assertEqual(completed.returncode, 0)
        self.assertTrue(isinstance(completed.stdout, str))
        self.assertNotEqual(completed.stdout, "")


if __name__ == "__main__":
    unittest.main()
