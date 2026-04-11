"""Tests for scripts/deploy_agent_skills.py."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from deploy_agent_skills import (  # type: ignore[import-not-found]
    MachineBootstrapPlan,
    build_machine_bootstrap_plan,
    build_default_inventory,
    build_dependency_plan,
    DeploymentInventory,
    execute_local_deploy,
    load_target_config,
    plan_repo_checkout_steps,
    render_agent_runtime_template,
    render_template_files,
)


class TestDeployAgentSkills(unittest.TestCase):
    def fixture_path(self, name: str) -> Path:
        return Path(__file__).resolve().parent / "fixtures" / "deploy" / name

    def test_load_target_config_reads_fixture_schema(self):
        config = load_target_config(self.fixture_path("target_config.json"))

        self.assertEqual(config.mode, "local")
        self.assertEqual(config.target_os, "linux")
        self.assertEqual(config.repo_branch, "main")
        self.assertEqual(config.clone_dir.as_posix(), "/opt/hospital-claw")
        self.assertEqual(config.agent_skill_dir.as_posix(), "/opt/openclaw/skills")
        self.assertTrue(config.optional_components.wechat_router)
        self.assertTrue(config.optional_components.wechat_decrypt)
        self.assertTrue(config.wechat_decrypt.enabled)
        self.assertEqual(config.ssh.host, "mini.local")

    def test_build_default_inventory_includes_root_skills_and_shared_scripts(self):
        repo_root = Path(__file__).resolve().parent.parent

        inventory = build_default_inventory(repo_root)

        self.assertIn("skills/tcm-treatment-review", inventory.skill_directories)
        self.assertIn("skills/tcm-treatment-plan", inventory.skill_directories)
        self.assertIn("skills/sh-yb-policy-monitor", inventory.skill_directories)
        self.assertIn("skills/knowledge-base-update", inventory.skill_directories)
        self.assertIn("skills/wechat-daily-monitor", inventory.skill_directories)
        self.assertIn("scripts/review_db.py", inventory.shared_runtime_files)
        self.assertIn("scripts/update_kb_manifest.py", inventory.shared_runtime_files)
        self.assertIn("scripts/wechat_article_pipeline.py", inventory.shared_runtime_files)
        self.assertIn(
            "skills/sh-yb-policy-monitor/scripts/fetch_policies.py",
            inventory.shared_runtime_files,
        )

    def test_build_dependency_plan_includes_optional_requirements_and_services(self):
        config = load_target_config(self.fixture_path("target_config.json"))

        plan = build_dependency_plan(config, config.clone_dir)

        self.assertIn("requests", plan.root_python_packages)
        self.assertIn("beautifulsoup4", plan.root_python_packages)
        self.assertIn("wechat-router/requirements.txt", plan.requirements_files)
        self.assertIn("wechat-router/wechat-decrypt/requirements.txt", plan.requirements_files)
        self.assertIn("qmd mcp --http --daemon", plan.service_commands)
        self.assertIn("mcp_server.py", " ".join(plan.template_commands))

    def test_build_machine_bootstrap_plan_windows_can_plan_git_and_qmd_tooling_install(self):
        config = load_target_config(self.fixture_path("target_config.json"))
        config.target_os = "windows"
        config.qmd.install_machine_tools = True

        plan = build_machine_bootstrap_plan(
            config,
            git_path="",
            node_path="",
            npm_path="",
            qmd_path="",
            winget_path="C:/Windows/System32/winget.exe",
        )

        self.assertIn("python=", " ".join(plan.detected_tools))
        self.assertIn(
            ["C:/Windows/System32/winget.exe", "install", "-e", "--id", "Git.Git", "--accept-package-agreements", "--accept-source-agreements"],
            plan.automated_commands,
        )
        self.assertIn(
            ["C:/Windows/System32/winget.exe", "install", "-e", "--id", "OpenJS.NodeJS.LTS", "--accept-package-agreements", "--accept-source-agreements"],
            plan.automated_commands,
        )
        self.assertIn(["npm", "install", "-g", "@tobilu/qmd"], plan.automated_commands)
        self.assertFalse(any("git" in step.lower() for step in plan.manual_steps))

    def test_plan_repo_checkout_steps_clones_when_target_is_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            clone_dir = Path(tmpdir) / "hospital-claw"
            steps = plan_repo_checkout_steps(
                repo_url="https://example.com/roger/hospital-claw.git",
                repo_branch="main",
                clone_dir=clone_dir,
            )

        self.assertEqual(
            steps[0],
            [
                "git",
                "clone",
                "--branch",
                "main",
                "https://example.com/roger/hospital-claw.git",
                str(clone_dir),
            ],
        )

    def test_plan_repo_checkout_steps_updates_existing_clone(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            clone_dir = Path(tmpdir) / "hospital-claw"
            (clone_dir / ".git").mkdir(parents=True, exist_ok=True)
            steps = plan_repo_checkout_steps(
                repo_url="https://example.com/roger/hospital-claw.git",
                repo_branch="main",
                clone_dir=clone_dir,
            )

        self.assertEqual(steps[0], ["git", "-C", str(clone_dir), "fetch", "--all"])
        self.assertEqual(steps[1], ["git", "-C", str(clone_dir), "checkout", "main"])
        self.assertEqual(
            steps[2],
            ["git", "-C", str(clone_dir), "pull", "--ff-only", "origin", "main"],
        )

    def test_render_agent_runtime_template_includes_qmd_and_wechat_mcp_entries(self):
        config = load_target_config(self.fixture_path("target_config.json"))
        repo_root = Path(__file__).resolve().parent.parent
        inventory = build_default_inventory(repo_root)

        template = render_agent_runtime_template(config, config.clone_dir, inventory)

        self.assertEqual(template["skillsDir"], config.agent_skill_dir.as_posix())
        self.assertEqual(template["repoCloneDir"], config.clone_dir.as_posix())
        self.assertEqual(template["mcpServers"]["qmd"]["type"], "http")
        self.assertEqual(template["mcpServers"]["qmd"]["url"], "http://localhost:8181/mcp")
        self.assertEqual(template["mcpServers"]["wechat"]["type"], "stdio")
        self.assertIn("mcp_server.py", template["mcpServers"]["wechat"]["args"][0])
        self.assertIn("_shared_runtime", template["sharedRuntimeDir"])

    def test_render_template_files_returns_runtime_json_and_service_script(self):
        config = load_target_config(self.fixture_path("target_config.json"))
        repo_root = Path(__file__).resolve().parent.parent
        inventory = build_default_inventory(repo_root)

        templates = render_template_files(config, config.clone_dir, inventory)

        self.assertIn("agent-runtime-config.template.json", templates)
        self.assertIn("service-commands.sh", templates)
        self.assertIn("qmd mcp --http --daemon", templates["service-commands.sh"])

    def test_render_template_files_returns_systemd_unit_for_linux(self):
        config = load_target_config(self.fixture_path("target_config.json"))
        repo_root = Path(__file__).resolve().parent.parent
        inventory = build_default_inventory(repo_root)

        templates = render_template_files(config, config.clone_dir, inventory)

        self.assertIn("qmd-mcp.service", templates)
        self.assertIn("[Unit]", templates["qmd-mcp.service"])
        self.assertIn("ExecStart=/usr/bin/env bash -lc 'cd /opt/hospital-claw && qmd mcp --http --daemon'", templates["qmd-mcp.service"])
        self.assertIn("ExecStop=/usr/bin/env bash -lc 'qmd mcp stop'", templates["qmd-mcp.service"])

    def test_render_template_files_returns_launchd_plist_for_macos(self):
        config = load_target_config(self.fixture_path("target_config.json"))
        config.target_os = "macos"
        repo_root = Path(__file__).resolve().parent.parent
        inventory = build_default_inventory(repo_root)

        templates = render_template_files(config, config.clone_dir, inventory)

        self.assertIn("qmd-mcp.launchd.plist", templates)
        self.assertIn("<key>Label</key>", templates["qmd-mcp.launchd.plist"])
        self.assertIn("com.hospitalclaw.qmd.mcp", templates["qmd-mcp.launchd.plist"])
        self.assertIn('cd "/opt/hospital-claw" && qmd mcp --http --daemon', templates["qmd-mcp.launchd.plist"])

    def test_execute_local_deploy_dry_run_returns_checkout_steps_and_manual_steps(self):
        config = load_target_config(self.fixture_path("target_config.json"))
        repo_root = Path(__file__).resolve().parent.parent

        summary = execute_local_deploy(config, repo_root)

        self.assertEqual(summary.mode, "local")
        self.assertTrue(summary.dry_run)
        self.assertTrue(summary.repo_checkout_steps)
        self.assertIn("desktop WeChat is installed and signed in", " ".join(summary.manual_steps))

    def test_execute_local_deploy_uses_cloned_repo_for_inventory_when_not_dry_run(self):
        config = load_target_config(self.fixture_path("target_config.json"))
        config.dry_run = False

        with tempfile.TemporaryDirectory() as tmpdir:
            clone_dir = Path(tmpdir) / "hospital-claw"
            clone_dir.mkdir(parents=True, exist_ok=True)
            config.clone_dir = clone_dir
            config.agent_skill_dir = Path(tmpdir) / "skills"
            config.template_output_dir = Path(tmpdir) / "generated"
            build_calls: list[Path] = []

            def fake_build_inventory(repo_root: Path) -> DeploymentInventory:
                build_calls.append(repo_root)
                return DeploymentInventory(
                    skill_directories=("skills/tcm-treatment-review",),
                    shared_runtime_files=(),
                )

            with patch(
                "deploy_agent_skills.build_machine_bootstrap_plan",
                return_value=MachineBootstrapPlan(
                    detected_tools=("python=test",),
                    automated_commands=(),
                    automated_steps=(),
                    manual_steps=(),
                ),
            ), patch(
                "deploy_agent_skills.ensure_repo_checkout"
            ), patch(
                "deploy_agent_skills.create_or_reuse_venv",
                return_value=clone_dir / ".venv" / "Scripts" / "python.exe",
            ), patch(
                "deploy_agent_skills.install_python_packages"
            ), patch(
                "deploy_agent_skills._install_requirement_files"
            ), patch(
                "deploy_agent_skills.launch_optional_services",
                return_value=[],
            ), patch(
                "deploy_agent_skills.sync_deployment_bundle",
                return_value=[],
            ), patch(
                "deploy_agent_skills.write_template_files",
                return_value=[],
            ), patch(
                "deploy_agent_skills.build_default_inventory",
                side_effect=fake_build_inventory,
            ):
                execute_local_deploy(config, Path(tmpdir) / "source-repo")

        self.assertEqual(build_calls[-1], clone_dir)


if __name__ == "__main__":
    unittest.main()
