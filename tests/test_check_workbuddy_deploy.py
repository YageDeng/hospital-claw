"""Tests for scripts/check_workbuddy_deploy.py."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from check_workbuddy_deploy import (  # type: ignore[import-not-found]
    CheckResult,
    summarize_results,
    verify_workbuddy_deploy,
)


class TestCheckWorkBuddyDeploy(unittest.TestCase):
    def fixture_path(self, name: str) -> Path:
        return Path(__file__).resolve().parent / "fixtures" / "workbuddy" / name

    def materialize_fixture(self) -> tuple[str, Path]:
        tmpdir = tempfile.TemporaryDirectory()
        root = Path(tmpdir.name)
        fixture_payload = json.loads(self.fixture_path("deployed_home.json").read_text(encoding="utf-8"))
        for relative_path, template_content in fixture_payload["files"].items():
            target_path = root / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            content = template_content.replace("__ROOT__", root.as_posix())
            target_path.write_text(content, encoding="utf-8")
        return tmpdir, root

    def test_verify_workbuddy_deploy_reports_passes_for_fixture_filesystem_state(self):
        tmpdir, root = self.materialize_fixture()
        self.addCleanup(tmpdir.cleanup)

        report = verify_workbuddy_deploy(root)

        self.assertTrue(all(result.status == "pass" for result in report.skill_checks))
        self.assertTrue(all(result.status == "pass" for result in report.runtime_file_checks))
        self.assertTrue(any(result.status == "cannot_prove_from_filesystem" for result in report.config_checks))
        self.assertEqual(report.summary["fail"], 0)

    def test_verify_workbuddy_deploy_detects_mcp_mismatch(self):
        tmpdir, root = self.materialize_fixture()
        self.addCleanup(tmpdir.cleanup)

        mcp_path = root / "mcp.json"
        payload = json.loads(mcp_path.read_text(encoding="utf-8"))
        payload["mcpServers"]["qmd"]["url"] = "http://localhost:9999/mcp"
        mcp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        report = verify_workbuddy_deploy(root)

        mismatch_checks = [result for result in report.config_checks if result.name == "mcp_servers_match_template"]
        self.assertEqual(mismatch_checks[0].status, "fail")

    def test_verify_workbuddy_deploy_skips_live_checks_by_default(self):
        tmpdir, root = self.materialize_fixture()
        self.addCleanup(tmpdir.cleanup)

        report = verify_workbuddy_deploy(root)

        self.assertEqual(len(report.live_checks), 2)
        self.assertTrue(all(result.status == "skip" for result in report.live_checks))

    def test_verify_workbuddy_deploy_uses_optional_live_probe_results(self):
        tmpdir, root = self.materialize_fixture()
        self.addCleanup(tmpdir.cleanup)

        with patch(
            "check_workbuddy_deploy.probe_qmd_http",
            return_value=CheckResult("qmd_http", "pass", "ok"),
        ) as probe_qmd, patch(
            "check_workbuddy_deploy.probe_wechat_stdio",
            return_value=CheckResult("wechat_stdio", "pass", "ok"),
        ) as probe_wechat:
            report = verify_workbuddy_deploy(root, check_qmd=True, check_wechat_mcp=True)

        self.assertTrue(probe_qmd.called)
        self.assertTrue(probe_wechat.called)
        self.assertEqual([result.status for result in report.live_checks], ["pass", "pass"])

    def test_verify_workbuddy_deploy_fails_when_wechat_stdio_command_is_missing(self):
        tmpdir, root = self.materialize_fixture()
        self.addCleanup(tmpdir.cleanup)

        (root / "hospital-claw" / ".venv" / "Scripts" / "python.exe").unlink()

        report = verify_workbuddy_deploy(root)

        failed_checks = [result for result in report.runtime_file_checks if result.name == "wechat_stdio_command_exists"]
        self.assertEqual(failed_checks[0].status, "fail")

    def test_summarize_results_counts_all_statuses(self):
        summary = summarize_results(
            [
                CheckResult("a", "pass", "ok"),
                CheckResult("b", "fail", "broken"),
                CheckResult("c", "skip", "not requested"),
                CheckResult("d", "cannot_prove_from_filesystem", "no logs"),
            ]
        )

        self.assertEqual(summary["pass"], 1)
        self.assertEqual(summary["fail"], 1)
        self.assertEqual(summary["skip"], 1)
        self.assertEqual(summary["cannot_prove_from_filesystem"], 1)
        self.assertEqual(summary["total"], 4)


if __name__ == "__main__":
    unittest.main()
