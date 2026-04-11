"""Tests for scripts/bootstrap_skill_e2e.py."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from urllib.error import HTTPError
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from bootstrap_skill_e2e import (  # type: ignore[import-not-found]
    BootstrapConfig,
    REQUIRED_PYTHON_PACKAGES,
    build_harness_command,
    build_machine_install_commands,
    build_config,
    build_runner_env,
    default_report_paths,
    default_wechat_url_path,
    ensure_mcp_daemon,
    is_mcp_http_ready,
)


class TestBootstrapSkillE2E(unittest.TestCase):
    def test_default_report_paths_use_timestamped_run_directory(self):
        workspace_root = Path("C:/repo")

        json_out, markdown_out = default_report_paths(
            workspace_root,
            now=datetime(2026, 4, 11, 13, 2, 31, 456789),
        )

        self.assertEqual(
            json_out.as_posix(),
            "C:/repo/data/skill_e2e/runs/20260411-130231-456789/bootstrap-report.json",
        )
        self.assertEqual(
            markdown_out.as_posix(),
            "C:/repo/data/skill_e2e/runs/20260411-130231-456789/bootstrap-report.md",
        )
        self.assertEqual(json_out.parent, markdown_out.parent)

    def test_build_harness_command_forwards_core_flags(self):
        config = BootstrapConfig(
            workspace_root=Path("C:/repo"),
            allow_live=True,
            artifact_root=Path("C:/repo/data/skill_e2e/runs/20260411-130231-456789"),
            scenarios=["review_db_local", "knowledge_base_rules_live"],
            json_out=Path("C:/repo/data/skill_e2e/runs/20260411-130231-456789/bootstrap-report.json"),
            markdown_out=Path("C:/repo/data/skill_e2e/runs/20260411-130231-456789/bootstrap-report.md"),
        )

        command = build_harness_command(config, "C:/repo/.venv/Scripts/python.exe")

        self.assertEqual(command[0], "C:/repo/.venv/Scripts/python.exe")
        self.assertIn("scripts/run_skill_e2e.py", command[1].replace("\\", "/"))
        self.assertIn("--allow-live", command)
        self.assertIn("--artifact-root", command)
        self.assertIn("C:/repo/data/skill_e2e/runs/20260411-130231-456789", command)
        self.assertEqual(command.count("--scenario"), 2)
        self.assertIn("C:/repo/data/skill_e2e/runs/20260411-130231-456789/bootstrap-report.json", command)
        self.assertIn("C:/repo/data/skill_e2e/runs/20260411-130231-456789/bootstrap-report.md", command)

    def test_build_runner_env_sets_wechat_url(self):
        config = BootstrapConfig(
            workspace_root=Path("C:/repo"),
            wechat_url="https://mp.weixin.qq.com/s/example",
        )

        env = build_runner_env(config, {"BASE": "1"})

        self.assertEqual(env["BASE"], "1")
        self.assertEqual(env["SKILL_E2E_WECHAT_URL"], "https://mp.weixin.qq.com/s/example")

    def test_build_runner_env_uses_env_var_when_cli_url_missing(self):
        config = BootstrapConfig(workspace_root=Path("C:/repo"))

        env = build_runner_env(
            config,
            {"SKILL_E2E_WECHAT_URL": "https://mp.weixin.qq.com/s/from-env"},
        )

        self.assertEqual(env["SKILL_E2E_WECHAT_URL"], "https://mp.weixin.qq.com/s/from-env")

    def test_build_runner_env_uses_local_default_file_when_cli_and_env_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            default_file = default_wechat_url_path(workspace_root)
            default_file.parent.mkdir(parents=True, exist_ok=True)
            default_file.write_text("https://mp.weixin.qq.com/s/from-file\n", encoding="utf-8")
            config = BootstrapConfig(workspace_root=workspace_root)

            env = build_runner_env(config, {})

        self.assertEqual(env["SKILL_E2E_WECHAT_URL"], "https://mp.weixin.qq.com/s/from-file")

    def test_build_runner_env_prefers_cli_over_env_and_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            default_file = default_wechat_url_path(workspace_root)
            default_file.parent.mkdir(parents=True, exist_ok=True)
            default_file.write_text("https://mp.weixin.qq.com/s/from-file\n", encoding="utf-8")
            config = BootstrapConfig(
                workspace_root=workspace_root,
                wechat_url="https://mp.weixin.qq.com/s/from-cli",
            )

            env = build_runner_env(
                config,
                {"SKILL_E2E_WECHAT_URL": "https://mp.weixin.qq.com/s/from-env"},
            )

        self.assertEqual(env["SKILL_E2E_WECHAT_URL"], "https://mp.weixin.qq.com/s/from-cli")

    def test_build_runner_env_preserves_probe_env_when_cli_flags_absent(self):
        config = BootstrapConfig(workspace_root=Path("C:/repo"))

        env = build_runner_env(
            config,
            {
                "SKILL_E2E_ENABLE_PROBES": "1",
                "SKILL_E2E_AGENT_DRIVER": "python env_probe_driver.py",
            },
        )

        self.assertEqual(env["SKILL_E2E_ENABLE_PROBES"], "1")
        self.assertEqual(env["SKILL_E2E_AGENT_DRIVER"], "python env_probe_driver.py")

    def test_build_runner_env_prefers_cli_probe_settings_over_env(self):
        config = BootstrapConfig(
            workspace_root=Path("C:/repo"),
            enable_probes=True,
            agent_driver="python cli_probe_driver.py",
        )

        env = build_runner_env(
            config,
            {
                "SKILL_E2E_ENABLE_PROBES": "0",
                "SKILL_E2E_AGENT_DRIVER": "python env_probe_driver.py",
            },
        )

        self.assertEqual(env["SKILL_E2E_ENABLE_PROBES"], "1")
        self.assertEqual(env["SKILL_E2E_AGENT_DRIVER"], "python cli_probe_driver.py")

    def test_build_config_defaults_allow_live_to_false(self):
        args = type(
            "Args",
            (),
            {
                "allow_live": False,
                "wechat_url": None,
                "json_out": None,
                "markdown_out": None,
                "install_machine_tools": False,
                "restart_mcp": False,
                "scenario": [],
                "skip_python_install": False,
                "enable_probes": False,
                "agent_driver": None,
            },
        )()

        with patch("bootstrap_skill_e2e.workspace_root_from_script", return_value=Path("C:/repo")):
            config = build_config(args)

        self.assertFalse(config.allow_live)
        self.assertEqual(
            config.artifact_root.as_posix(),
            config.json_out.parent.as_posix(),
        )

    def test_build_config_populates_probe_settings(self):
        args = type(
            "Args",
            (),
            {
                "allow_live": True,
                "wechat_url": None,
                "json_out": None,
                "markdown_out": None,
                "install_machine_tools": False,
                "restart_mcp": False,
                "scenario": ["tcm_treatment_plan_prereqs"],
                "skip_python_install": False,
                "enable_probes": True,
                "agent_driver": "python cli_probe_driver.py",
            },
        )()

        with patch("bootstrap_skill_e2e.workspace_root_from_script", return_value=Path("C:/repo")):
            config = build_config(args)

        self.assertTrue(config.enable_probes)
        self.assertEqual(config.agent_driver, "python cli_probe_driver.py")

    def test_required_python_packages_cover_known_skill_dependencies(self):
        self.assertIn("requests", REQUIRED_PYTHON_PACKAGES)
        self.assertIn("beautifulsoup4", REQUIRED_PYTHON_PACKAGES)
        self.assertIn("openpyxl", REQUIRED_PYTHON_PACKAGES)
        self.assertIn("pymupdf", REQUIRED_PYTHON_PACKAGES)
        self.assertIn("python-docx", REQUIRED_PYTHON_PACKAGES)
        self.assertIn("python-pptx", REQUIRED_PYTHON_PACKAGES)

    def test_build_machine_install_commands_uses_npm_when_available(self):
        commands = build_machine_install_commands(
            platform="win32",
            node_exists=True,
            npm_path="C:/Program Files/nodejs/npm.cmd",
            winget_path=None,
        )

        self.assertEqual(
            commands,
            [["C:/Program Files/nodejs/npm.cmd", "install", "-g", "@tobilu/qmd"]],
        )

    def test_build_machine_install_commands_uses_winget_then_npm_when_node_missing(self):
        commands = build_machine_install_commands(
            platform="win32",
            node_exists=False,
            npm_path="C:/Program Files/nodejs/npm.cmd",
            winget_path="C:/Windows/System32/winget.exe",
        )

        self.assertEqual(
            commands[0],
            [
                "C:/Windows/System32/winget.exe",
                "install",
                "-e",
                "--id",
                "OpenJS.NodeJS.LTS",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ],
        )
        self.assertEqual(
            commands[1],
            ["C:/Program Files/nodejs/npm.cmd", "install", "-g", "@tobilu/qmd"],
        )

    def test_ensure_mcp_daemon_reuses_running_server_by_default(self):
        with patch("bootstrap_skill_e2e.is_mcp_http_ready", return_value=True), patch(
            "bootstrap_skill_e2e.run_command"
        ) as run_command:
            action = ensure_mcp_daemon("qmd", restart=False)

        self.assertEqual(action, "reused")
        run_command.assert_not_called()

    def test_ensure_mcp_daemon_restarts_when_requested(self):
        calls: list[list[str]] = []

        def fake_run(command, **kwargs):
            calls.append(command)
            return None

        with patch("bootstrap_skill_e2e.is_mcp_http_ready", side_effect=[False, True]), patch(
            "bootstrap_skill_e2e.run_command",
            side_effect=fake_run,
        ):
            action = ensure_mcp_daemon("qmd", restart=True)

        self.assertEqual(action, "started")
        self.assertEqual(
            calls,
            [
                ["qmd", "mcp", "stop"],
                ["qmd", "mcp", "--http", "--daemon"],
            ],
        )

    def test_is_mcp_http_ready_treats_http_error_response_as_ready(self):
        with patch(
            "bootstrap_skill_e2e.urlopen",
            side_effect=HTTPError(
                url="http://localhost:8181/mcp",
                code=400,
                msg="Bad Request",
                hdrs=None,
                fp=None,
            ),
        ):
            ready = is_mcp_http_ready("localhost", 8181)

        self.assertTrue(ready)


if __name__ == "__main__":
    unittest.main()
