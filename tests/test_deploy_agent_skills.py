"""Tests for scripts/deploy_agent_skills.py."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from deploy_agent_skills import (  # type: ignore[import-not-found]
    build_knowledge_base_paths,
    MachineBootstrapPlan,
    build_machine_bootstrap_plan,
    build_default_inventory,
    build_dependency_plan,
    DeploymentInventory,
    ensure_knowledge_base_layout,
    execute_local_deploy,
    load_target_config,
    plan_repo_checkout_steps,
    render_agent_runtime_template,
    render_template_files,
    sync_deployment_bundle,
)


class TestDeployAgentSkills(unittest.TestCase):
    def fixture_path(self, name: str) -> Path:
        return Path(__file__).resolve().parent / "fixtures" / "deploy" / name

    def config_path(self, name: str) -> Path:
        return Path(__file__).resolve().parent.parent / "config" / name

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

    def test_load_target_config_derives_paths_from_deploy_root_dir_and_resolves_relative_repo_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_root = Path(tmpdir)
            config_dir = temp_root / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            deploy_root_dir = temp_root / "runtime-home"
            config_path = config_dir / "agent_deploy.json"
            config_path.write_text(
                json.dumps(
                    {
                        "mode": "local",
                        "target_os": "windows",
                        "repo_url": "..",
                        "repo_branch": "main",
                        "deploy_root_dir": str(deploy_root_dir),
                        "dry_run": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            config = load_target_config(config_path)

        self.assertEqual(Path(config.repo_url).resolve(), temp_root.resolve())
        self.assertEqual(config.clone_dir, deploy_root_dir / "hospital-claw")
        self.assertEqual(config.agent_skill_dir, deploy_root_dir / "skills")
        self.assertEqual(config.template_output_dir, deploy_root_dir / "generated")

    def test_local_sample_configs_use_portable_deploy_root_dir_schema(self):
        expected_targets = {
            "agent_deploy.win.local.json": "windows",
            "agent_deploy.linux.local.json": "linux",
            "agent_deploy.macos.local.json": "macos",
        }

        for filename, target_os in expected_targets.items():
            with self.subTest(filename=filename):
                config = load_target_config(self.config_path(filename))

                self.assertEqual(config.target_os, target_os)
                self.assertEqual(config.repo_url, Path(__file__).resolve().parent.parent.as_posix())
                self.assertEqual(config.clone_dir.as_posix(), Path("~/.workbuddy/hospital-claw").expanduser().as_posix())
                self.assertEqual(config.agent_skill_dir.as_posix(), Path("~/.workbuddy/skills").expanduser().as_posix())
                self.assertEqual(
                    config.template_output_dir.as_posix(),
                    Path("~/.workbuddy/generated").expanduser().as_posix(),
                )

    def test_example_config_uses_portable_workbuddy_paths(self):
        config = load_target_config(self.config_path("agent_deploy.example.json"))

        self.assertEqual(config.target_os, "linux")
        self.assertEqual(config.repo_url, "https://github.com/your-org/hospital-claw.git")
        self.assertEqual(config.clone_dir.as_posix(), Path("~/.workbuddy/hospital-claw").expanduser().as_posix())
        self.assertEqual(config.agent_skill_dir.as_posix(), Path("~/.workbuddy/skills").expanduser().as_posix())
        self.assertEqual(
            config.template_output_dir.as_posix(),
            Path("~/.workbuddy/generated").expanduser().as_posix(),
        )

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
        self.assertEqual(
            template["knowledgeBase"]["rootDir"],
            "/opt/hospital-claw/docs/knowledge-base",
        )
        self.assertEqual(
            template["knowledgeBase"]["sourceDocsDir"],
            "/opt/hospital-claw/docs/医院材料学习",
        )
        self.assertEqual(
            template["knowledgeBase"]["policySaveDir"],
            "/opt/hospital-claw/data/sh-yb-policies",
        )
        self.assertEqual(
            template["knowledgeBase"]["sharedInfoFile"],
            "/opt/openclaw/skills/_shared_runtime/knowledge-base-paths.json",
        )

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

    def test_build_knowledge_base_paths_covers_windows_macos_and_linux(self):
        config = load_target_config(self.fixture_path("target_config.json"))
        clone_dirs = {
            "windows": Path("C:/Users/roger/.workbuddy/hospital-claw"),
            "macos": Path("/Users/roger/.workbuddy/hospital-claw"),
            "linux": Path("/opt/hospital-claw"),
        }
        skill_dirs = {
            "windows": Path("C:/Users/roger/.workbuddy/skills"),
            "macos": Path("/Users/roger/.workbuddy/skills"),
            "linux": Path("/opt/openclaw/skills"),
        }

        for target_os, clone_dir in clone_dirs.items():
            with self.subTest(target_os=target_os):
                config.target_os = target_os
                config.clone_dir = clone_dir
                config.agent_skill_dir = skill_dirs[target_os]
                paths = build_knowledge_base_paths(config, clone_dir)

                self.assertEqual(
                    paths.root_dir.as_posix(),
                    f"{clone_dir.as_posix()}/docs/knowledge-base",
                )
                self.assertEqual(
                    paths.source_docs_dir.as_posix(),
                    f"{clone_dir.as_posix()}/docs/医院材料学习",
                )
                self.assertEqual(
                    paths.policy_save_dir.as_posix(),
                    f"{clone_dir.as_posix()}/data/sh-yb-policies",
                )
                self.assertEqual(
                    paths.shared_info_file.as_posix(),
                    f"{skill_dirs[target_os].as_posix()}/_shared_runtime/knowledge-base-paths.json",
                )

    def test_ensure_knowledge_base_layout_creates_expected_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            clone_dir = Path(tmpdir) / "hospital-claw"
            ensure_knowledge_base_layout(clone_dir)

            expected_dirs = [
                clone_dir / "docs" / "knowledge-base",
                clone_dir / "docs" / "knowledge-base" / "wiki",
                clone_dir / "docs" / "knowledge-base" / "index",
                clone_dir / "docs" / "knowledge-base" / ".staging",
                clone_dir / "docs" / "knowledge-base" / ".staging-binary-md",
                clone_dir / "docs" / "knowledge-base" / ".manual-rules",
                clone_dir / "docs" / "knowledge-base" / ".wiki-ingest-src",
                clone_dir / "docs" / "医院材料学习",
                clone_dir / "data" / "sh-yb-policies",
            ]

            for path in expected_dirs:
                self.assertTrue(path.is_dir(), msg=f"Expected directory missing: {path}")

    def test_sync_deployment_bundle_writes_shared_knowledge_base_info(self):
        config = load_target_config(self.fixture_path("target_config.json"))
        with tempfile.TemporaryDirectory() as tmpdir:
            source_root = Path(tmpdir) / "source"
            source_root.mkdir(parents=True, exist_ok=True)
            config.agent_skill_dir = Path(tmpdir) / "skills"
            config.clone_dir = source_root

            copied_items = sync_deployment_bundle(
                source_root,
                config,
                DeploymentInventory(skill_directories=(), shared_runtime_files=()),
            )

            shared_info_file = config.agent_skill_dir / "_shared_runtime" / "knowledge-base-paths.json"
            self.assertIn(shared_info_file.as_posix(), copied_items)
            self.assertTrue(shared_info_file.exists())

            payload = json.loads(shared_info_file.read_text(encoding="utf-8"))
            self.assertEqual(
                payload["knowledgeBase"]["rootDir"],
                source_root.joinpath("docs", "knowledge-base").as_posix(),
            )
            self.assertEqual(
                payload["knowledgeBase"]["sourceDocsDir"],
                source_root.joinpath("docs", "医院材料学习").as_posix(),
            )
            self.assertEqual(
                payload["knowledgeBase"]["policySaveDir"],
                source_root.joinpath("data", "sh-yb-policies").as_posix(),
            )

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
