"""Deploy repo-owned skills to OpenClaw-like agent runtimes.

This script supports two deployment modes:

- local: run on the target host directly
- ssh: connect to a remote host over SSH and bootstrap a local deployment there

The script is intentionally conservative. It can clone/update the repo, install
repo and optional skill dependencies, start reusable services such as qmd MCP,
copy the deployable skill/runtime bundle into a configured agent skill folder,
and generate runtime config templates. It does not mutate the live agent-system
config automatically.
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Sequence

from bootstrap_skill_e2e import (  # type: ignore[import-not-found]
    DEFAULT_MCP_HOST,
    DEFAULT_MCP_PORT,
    REQUIRED_PYTHON_PACKAGES,
    build_machine_install_commands,
    create_or_reuse_venv,
    ensure_mcp_daemon,
    install_python_packages,
    run_command,
)

DeployMode = Literal["local", "ssh"]
TargetOS = Literal["windows", "linux", "macos"]

ROOT_SKILL_DIRECTORIES = (
    "skills/tcm-treatment-review",
    "skills/tcm-treatment-plan",
    "skills/sh-yb-policy-monitor",
    "skills/knowledge-base-update",
    "skills/wechat-daily-monitor",
)
SHARED_RUNTIME_FILES = (
    "scripts/review_db.py",
    "scripts/update_kb_manifest.py",
    "scripts/xlsx_to_markdown.py",
    "scripts/binary_docs_to_markdown.py",
    "scripts/wechat_article_pipeline.py",
    "skills/sh-yb-policy-monitor/scripts/fetch_policies.py",
)
WECHAT_ROUTER_REQUIREMENTS = "wechat-router/requirements.txt"
WECHAT_DECRYPT_REQUIREMENTS = "wechat-router/wechat-decrypt/requirements.txt"
WECHAT_DECRYPT_MCP_SCRIPT = "wechat-router/wechat-decrypt/mcp_server.py"
WECHAT_DECRYPT_WEB_SCRIPT = "wechat-router/wechat-decrypt/main.py"


class DeployError(RuntimeError):
    """Raised when deployment cannot proceed."""


@dataclass
class SSHSettings:
    host: str
    user: str | None = None
    port: int | None = None
    identity_file: str | None = None


@dataclass
class OptionalComponents:
    wechat_router: bool = False
    wechat_decrypt: bool = False


@dataclass
class QmdSettings:
    enabled: bool = True
    start: bool = True
    install_if_missing: bool = True
    install_machine_tools: bool = False
    restart: bool = False
    host: str = DEFAULT_MCP_HOST
    port: int = DEFAULT_MCP_PORT


@dataclass
class WechatDecryptSettings:
    enabled: bool = False
    generate_mcp_template: bool = True
    launch_web_ui: bool = False
    web_host: str = "localhost"
    web_port: int = 5678


@dataclass
class DeployTargetConfig:
    mode: DeployMode
    target_os: TargetOS
    repo_url: str
    clone_dir: Path
    agent_skill_dir: Path
    template_output_dir: Path
    repo_branch: str = "main"
    dry_run: bool = False
    qmd: QmdSettings = field(default_factory=QmdSettings)
    optional_components: OptionalComponents = field(default_factory=OptionalComponents)
    wechat_decrypt: WechatDecryptSettings = field(default_factory=WechatDecryptSettings)
    ssh: SSHSettings | None = None

    def to_local_mode(self) -> "DeployTargetConfig":
        return DeployTargetConfig(
            mode="local",
            target_os=self.target_os,
            repo_url=self.repo_url,
            repo_branch=self.repo_branch,
            clone_dir=self.clone_dir,
            agent_skill_dir=self.agent_skill_dir,
            template_output_dir=self.template_output_dir,
            dry_run=self.dry_run,
            qmd=self.qmd,
            optional_components=self.optional_components,
            wechat_decrypt=self.wechat_decrypt,
            ssh=None,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["clone_dir"] = self.clone_dir.as_posix()
        payload["agent_skill_dir"] = self.agent_skill_dir.as_posix()
        payload["template_output_dir"] = self.template_output_dir.as_posix()
        return payload


@dataclass
class DeploymentInventory:
    skill_directories: tuple[str, ...]
    shared_runtime_files: tuple[str, ...]


@dataclass
class DependencyPlan:
    root_python_packages: tuple[str, ...]
    requirements_files: tuple[str, ...]
    service_commands: tuple[str, ...]
    template_commands: tuple[str, ...]
    manual_steps: tuple[str, ...]


@dataclass
class MachineBootstrapPlan:
    detected_tools: tuple[str, ...]
    automated_commands: tuple[list[str], ...]
    automated_steps: tuple[str, ...]
    manual_steps: tuple[str, ...]


@dataclass
class DeploySummary:
    mode: DeployMode
    dry_run: bool
    repo_checkout_steps: list[list[str]]
    copied_items: list[str] = field(default_factory=list)
    template_files: list[str] = field(default_factory=list)
    started_services: list[str] = field(default_factory=list)
    detected_tools: list[str] = field(default_factory=list)
    automated_steps: list[str] = field(default_factory=list)
    manual_steps: list[str] = field(default_factory=list)
    ssh_command: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "dry_run": self.dry_run,
            "repo_checkout_steps": self.repo_checkout_steps,
            "copied_items": self.copied_items,
            "template_files": self.template_files,
            "started_services": self.started_services,
            "detected_tools": self.detected_tools,
            "automated_steps": self.automated_steps,
            "manual_steps": self.manual_steps,
            "ssh_command": self.ssh_command,
        }


def _coerce_path(value: str | Path) -> Path:
    return Path(str(value)).expanduser()


def current_target_os() -> TargetOS:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def _parse_target_os(value: str | None) -> TargetOS:
    if value in {"windows", "linux", "macos"}:
        return value
    if value is None:
        return current_target_os()
    raise DeployError(f"Unsupported target_os: {value}")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _optional_components_from_dict(raw: dict[str, Any] | None) -> OptionalComponents:
    payload = raw or {}
    return OptionalComponents(
        wechat_router=bool(payload.get("wechat_router", False)),
        wechat_decrypt=bool(payload.get("wechat_decrypt", False)),
    )


def _qmd_from_dict(raw: dict[str, Any] | None) -> QmdSettings:
    payload = raw or {}
    return QmdSettings(
        enabled=bool(payload.get("enabled", True)),
        start=bool(payload.get("start", True)),
        install_if_missing=bool(payload.get("install_if_missing", True)),
        install_machine_tools=bool(payload.get("install_machine_tools", False)),
        restart=bool(payload.get("restart", False)),
        host=str(payload.get("host", DEFAULT_MCP_HOST)),
        port=int(payload.get("port", DEFAULT_MCP_PORT)),
    )


def _wechat_decrypt_from_dict(raw: dict[str, Any] | None) -> WechatDecryptSettings:
    payload = raw or {}
    return WechatDecryptSettings(
        enabled=bool(payload.get("enabled", False)),
        generate_mcp_template=bool(payload.get("generate_mcp_template", True)),
        launch_web_ui=bool(payload.get("launch_web_ui", False)),
        web_host=str(payload.get("web_host", "localhost")),
        web_port=int(payload.get("web_port", 5678)),
    )


def _ssh_from_dict(raw: dict[str, Any] | None) -> SSHSettings | None:
    payload = raw or {}
    host = str(payload.get("host", "")).strip()
    if not host:
        return None
    return SSHSettings(
        host=host,
        user=str(payload["user"]).strip() if payload.get("user") else None,
        port=int(payload["port"]) if payload.get("port") else None,
        identity_file=str(payload["identity_file"]).strip() if payload.get("identity_file") else None,
    )


def load_target_config(path: Path) -> DeployTargetConfig:
    raw = _load_json(path)
    return DeployTargetConfig(
        mode=str(raw.get("mode", "local")),  # type: ignore[arg-type]
        target_os=_parse_target_os(raw.get("target_os")),
        repo_url=str(raw["repo_url"]),
        repo_branch=str(raw.get("repo_branch", "main")),
        clone_dir=_coerce_path(raw["clone_dir"]),
        agent_skill_dir=_coerce_path(raw["agent_skill_dir"]),
        template_output_dir=_coerce_path(raw["template_output_dir"]),
        dry_run=bool(raw.get("dry_run", False)),
        qmd=_qmd_from_dict(raw.get("qmd")),
        optional_components=_optional_components_from_dict(raw.get("optional_components")),
        wechat_decrypt=_wechat_decrypt_from_dict(raw.get("wechat_decrypt")),
        ssh=_ssh_from_dict(raw.get("ssh")),
    )


def build_default_inventory(repo_root: Path) -> DeploymentInventory:
    existing_skill_directories = tuple(
        relative_path
        for relative_path in ROOT_SKILL_DIRECTORIES
        if (repo_root / relative_path).exists()
    )
    existing_shared_runtime_files = tuple(
        relative_path
        for relative_path in SHARED_RUNTIME_FILES
        if (repo_root / relative_path).exists()
    )
    return DeploymentInventory(
        skill_directories=existing_skill_directories,
        shared_runtime_files=existing_shared_runtime_files,
    )


def target_venv_python(clone_dir: Path, target_os: TargetOS) -> Path:
    if target_os == "windows":
        return clone_dir / ".venv" / "Scripts" / "python.exe"
    return clone_dir / ".venv" / "bin" / "python"


def _windows_tesseract_path() -> Path:
    return Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")


def _existing_tool_path(value: str | None, command_name: str) -> str | None:
    if value is not None:
        return value
    return shutil.which(command_name)


def _package_manager_path(value: str | None, command_name: str) -> str | None:
    return value if value is not None else shutil.which(command_name)


def build_machine_bootstrap_plan(
    config: DeployTargetConfig,
    *,
    git_path: str | None = None,
    node_path: str | None = None,
    npm_path: str | None = None,
    qmd_path: str | None = None,
    winget_path: str | None = None,
    brew_path: str | None = None,
    apt_get_path: str | None = None,
    dnf_path: str | None = None,
    yum_path: str | None = None,
) -> MachineBootstrapPlan:
    detected_tools: list[str] = [f"python={sys.executable}"]
    automated_commands: list[list[str]] = []
    automated_steps: list[str] = []
    manual_steps: list[str] = []

    resolved_git = _existing_tool_path(git_path, "git")
    resolved_node = _existing_tool_path(node_path, "node")
    resolved_npm = _existing_tool_path(npm_path, "npm")
    resolved_qmd = _existing_tool_path(qmd_path, "qmd")
    resolved_winget = _package_manager_path(winget_path, "winget")
    resolved_brew = _package_manager_path(brew_path, "brew")
    resolved_apt_get = _package_manager_path(apt_get_path, "apt-get")
    resolved_dnf = _package_manager_path(dnf_path, "dnf")
    resolved_yum = _package_manager_path(yum_path, "yum")
    resolved_tesseract = shutil.which("tesseract")
    if not resolved_tesseract and _windows_tesseract_path().exists():
        resolved_tesseract = str(_windows_tesseract_path())

    if resolved_git:
        detected_tools.append(f"git={resolved_git}")
    elif config.qmd.install_machine_tools:
        if config.target_os == "windows" and resolved_winget:
            automated_commands.append(
                [
                    resolved_winget,
                    "install",
                    "-e",
                    "--id",
                    "Git.Git",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                ]
            )
            automated_steps.append("Install Git via winget")
        elif config.target_os == "macos" and resolved_brew:
            automated_commands.append([resolved_brew, "install", "git"])
            automated_steps.append("Install Git via Homebrew")
        elif config.target_os == "linux" and resolved_apt_get:
            automated_commands.append(["sudo", resolved_apt_get, "update"])
            automated_commands.append(["sudo", resolved_apt_get, "install", "-y", "git"])
            automated_steps.append("Install Git via apt-get")
        elif config.target_os == "linux" and resolved_dnf:
            automated_commands.append(["sudo", resolved_dnf, "install", "-y", "git"])
            automated_steps.append("Install Git via dnf")
        elif config.target_os == "linux" and resolved_yum:
            automated_commands.append(["sudo", resolved_yum, "install", "-y", "git"])
            automated_steps.append("Install Git via yum")
        else:
            manual_steps.append("Install Git on the target host before cloning the repo.")
    else:
        manual_steps.append("Install Git on the target host before cloning the repo.")

    if resolved_node:
        detected_tools.append(f"node={resolved_node}")
    if resolved_npm:
        detected_tools.append(f"npm={resolved_npm}")
    if resolved_qmd:
        detected_tools.append(f"qmd={resolved_qmd}")
    elif config.qmd.enabled and config.qmd.install_if_missing:
        if not resolved_node or not resolved_npm:
            if config.qmd.install_machine_tools:
                if config.target_os == "windows" and resolved_winget:
                    automated_commands.append(
                        [
                            resolved_winget,
                            "install",
                            "-e",
                            "--id",
                            "OpenJS.NodeJS.LTS",
                            "--accept-package-agreements",
                            "--accept-source-agreements",
                        ]
                    )
                    automated_steps.append("Install Node.js LTS via winget")
                elif config.target_os == "macos" and resolved_brew:
                    automated_commands.append([resolved_brew, "install", "node"])
                    automated_steps.append("Install Node.js via Homebrew")
                elif config.target_os == "linux" and resolved_apt_get:
                    automated_commands.append(["sudo", resolved_apt_get, "update"])
                    automated_commands.append(
                        ["sudo", resolved_apt_get, "install", "-y", "nodejs", "npm"]
                    )
                    automated_steps.append("Install Node.js and npm via apt-get")
                elif config.target_os == "linux" and resolved_dnf:
                    automated_commands.append(
                        ["sudo", resolved_dnf, "install", "-y", "nodejs", "npm"]
                    )
                    automated_steps.append("Install Node.js and npm via dnf")
                elif config.target_os == "linux" and resolved_yum:
                    automated_commands.append(
                        ["sudo", resolved_yum, "install", "-y", "nodejs", "npm"]
                    )
                    automated_steps.append("Install Node.js and npm via yum")
                else:
                    manual_steps.append(
                        "Install Node.js and npm on the target host so qmd can be installed."
                    )
            else:
                manual_steps.append(
                    "Install Node.js and npm on the target host so qmd can be installed."
                )
        automated_commands.append([resolved_npm or "npm", "install", "-g", "@tobilu/qmd"])
        automated_steps.append("Install qmd globally with npm")

    if config.optional_components.wechat_router:
        if resolved_tesseract:
            detected_tools.append(f"tesseract={resolved_tesseract}")
        else:
            manual_steps.append(
                "Install Tesseract and the chi_sim language pack before enabling wechat-router OCR automation."
            )
    if config.optional_components.wechat_router or config.optional_components.wechat_decrypt:
        manual_steps.append(
            "Verify desktop WeChat is installed and signed in on the target host before using WeChat-dependent skills."
        )
    if config.wechat_decrypt.enabled:
        manual_steps.append(
            "Run wechat-decrypt key extraction and confirm the target host has the required permissions before using the wechat MCP."
        )

    return MachineBootstrapPlan(
        detected_tools=tuple(detected_tools),
        automated_commands=tuple(automated_commands),
        automated_steps=tuple(automated_steps),
        manual_steps=tuple(dict.fromkeys(manual_steps)),
    )


def build_dependency_plan(config: DeployTargetConfig, clone_dir: Path) -> DependencyPlan:
    requirements_files: list[str] = []
    if config.optional_components.wechat_router:
        requirements_files.append(WECHAT_ROUTER_REQUIREMENTS)
    if config.optional_components.wechat_decrypt:
        requirements_files.append(WECHAT_DECRYPT_REQUIREMENTS)

    service_commands: list[str] = []
    if config.qmd.enabled and config.qmd.start:
        service_commands.append("qmd mcp --http --daemon")
    if config.wechat_decrypt.enabled and config.wechat_decrypt.launch_web_ui:
        service_commands.append(
            f"{target_venv_python(clone_dir, config.target_os).as_posix()} "
            f"{(clone_dir / WECHAT_DECRYPT_WEB_SCRIPT).as_posix()}"
        )

    template_commands: list[str] = []
    if config.wechat_decrypt.enabled and config.wechat_decrypt.generate_mcp_template:
        template_commands.append(
            f"{target_venv_python(clone_dir, config.target_os).as_posix()} "
            f"{(clone_dir / WECHAT_DECRYPT_MCP_SCRIPT).as_posix()}"
        )

    return DependencyPlan(
        root_python_packages=tuple(REQUIRED_PYTHON_PACKAGES),
        requirements_files=tuple(requirements_files),
        service_commands=tuple(service_commands),
        template_commands=tuple(template_commands),
        manual_steps=(),
    )


def plan_repo_checkout_steps(repo_url: str, repo_branch: str, clone_dir: Path) -> list[list[str]]:
    if not (clone_dir / ".git").exists():
        return [
            ["git", "clone", "--branch", repo_branch, repo_url, str(clone_dir)],
        ]
    return [
        ["git", "-C", str(clone_dir), "fetch", "--all"],
        ["git", "-C", str(clone_dir), "checkout", repo_branch],
        ["git", "-C", str(clone_dir), "pull", "--ff-only", "origin", repo_branch],
    ]


def render_agent_runtime_template(
    config: DeployTargetConfig,
    clone_dir: Path,
    inventory: DeploymentInventory,
) -> dict[str, Any]:
    shared_runtime_dir = config.agent_skill_dir / "_shared_runtime"
    template: dict[str, Any] = {
        "agentSystem": "openclaw-like",
        "mode": config.mode,
        "targetOs": config.target_os,
        "repoCloneDir": clone_dir.as_posix(),
        "skillsDir": config.agent_skill_dir.as_posix(),
        "sharedRuntimeDir": shared_runtime_dir.as_posix(),
        "skills": [Path(relative_path).name for relative_path in inventory.skill_directories],
        "mcpServers": {},
        "serviceCommands": {},
        "manualSteps": list(build_dependency_plan(config, clone_dir).manual_steps),
    }
    if config.qmd.enabled:
        template["mcpServers"]["qmd"] = {
            "type": "http",
            "url": f"http://{config.qmd.host}:{config.qmd.port}/mcp",
        }
        template["serviceCommands"]["qmd_mcp"] = "qmd mcp --http --daemon"
    if config.wechat_decrypt.enabled and config.wechat_decrypt.generate_mcp_template:
        template["mcpServers"]["wechat"] = {
            "type": "stdio",
            "command": target_venv_python(clone_dir, config.target_os).as_posix(),
            "args": [(clone_dir / WECHAT_DECRYPT_MCP_SCRIPT).as_posix()],
        }
    if config.wechat_decrypt.enabled and config.wechat_decrypt.launch_web_ui:
        template["serviceCommands"]["wechat_decrypt_web"] = (
            f"{target_venv_python(clone_dir, config.target_os).as_posix()} "
            f"{(clone_dir / WECHAT_DECRYPT_WEB_SCRIPT).as_posix()}"
        )
    return template


def render_service_script(config: DeployTargetConfig, clone_dir: Path) -> tuple[str, str]:
    dependency_plan = build_dependency_plan(config, clone_dir)
    if config.target_os == "windows":
        filename = "service-commands.ps1"
        lines = [
            "$ErrorActionPreference = 'Stop'",
            "",
        ]
        if "qmd mcp --http --daemon" in dependency_plan.service_commands:
            lines.append("qmd mcp --http --daemon")
        if config.wechat_decrypt.enabled and config.wechat_decrypt.generate_mcp_template:
            lines.extend(
                [
                    "",
                    "# Register this stdio MCP entry in the target agent runtime config:",
                    f"# {target_venv_python(clone_dir, config.target_os).as_posix()} {(clone_dir / WECHAT_DECRYPT_MCP_SCRIPT).as_posix()}",
                ]
            )
        if config.wechat_decrypt.enabled and config.wechat_decrypt.launch_web_ui:
            lines.extend(
                [
                    "",
                    "# Optional local web UI for manual wechat-decrypt operations:",
                    f"{target_venv_python(clone_dir, config.target_os).as_posix()} {(clone_dir / WECHAT_DECRYPT_WEB_SCRIPT).as_posix()}",
                ]
            )
        return filename, "\n".join(lines).rstrip() + "\n"

    filename = "service-commands.sh"
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
    ]
    if "qmd mcp --http --daemon" in dependency_plan.service_commands:
        lines.append("qmd mcp --http --daemon")
    if config.wechat_decrypt.enabled and config.wechat_decrypt.generate_mcp_template:
        lines.extend(
            [
                "",
                "# Register this stdio MCP entry in the target agent runtime config:",
                f"# {target_venv_python(clone_dir, config.target_os).as_posix()} {(clone_dir / WECHAT_DECRYPT_MCP_SCRIPT).as_posix()}",
            ]
        )
    if config.wechat_decrypt.enabled and config.wechat_decrypt.launch_web_ui:
        lines.extend(
            [
                "",
                "# Optional local web UI for manual wechat-decrypt operations:",
                f"{target_venv_python(clone_dir, config.target_os).as_posix()} {(clone_dir / WECHAT_DECRYPT_WEB_SCRIPT).as_posix()}",
            ]
        )
    return filename, "\n".join(lines).rstrip() + "\n"


def render_systemd_unit(config: DeployTargetConfig, clone_dir: Path) -> tuple[str, str] | None:
    if config.target_os != "linux" or not config.qmd.enabled:
        return None
    content = "\n".join(
        [
            "[Unit]",
            "Description=Hospital Claw qmd MCP",
            "After=network.target",
            "",
            "[Service]",
            "Type=oneshot",
            "RemainAfterExit=yes",
            f"WorkingDirectory={clone_dir.as_posix()}",
            f"ExecStart=/usr/bin/env bash -lc 'cd {clone_dir.as_posix()} && qmd mcp --http --daemon'",
            "ExecStop=/usr/bin/env bash -lc 'qmd mcp stop'",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )
    return ("qmd-mcp.service", content)


def render_launchd_plist(config: DeployTargetConfig, clone_dir: Path) -> tuple[str, str] | None:
    if config.target_os != "macos" or not config.qmd.enabled:
        return None
    log_root = config.template_output_dir.as_posix()
    shell_command = f'cd "{clone_dir.as_posix()}" && qmd mcp --http --daemon'
    content = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
            '<plist version="1.0">',
            "<dict>",
            "  <key>Label</key>",
            "  <string>com.hospitalclaw.qmd.mcp</string>",
            "  <key>ProgramArguments</key>",
            "  <array>",
            "    <string>/bin/bash</string>",
            "    <string>-lc</string>",
            f"    <string>{shell_command}</string>",
            "  </array>",
            "  <key>WorkingDirectory</key>",
            f"  <string>{clone_dir.as_posix()}</string>",
            "  <key>RunAtLoad</key>",
            "  <true/>",
            "  <key>StandardOutPath</key>",
            f"  <string>{log_root}/qmd-mcp.stdout.log</string>",
            "  <key>StandardErrorPath</key>",
            f"  <string>{log_root}/qmd-mcp.stderr.log</string>",
            "</dict>",
            "</plist>",
            "",
        ]
    )
    return ("qmd-mcp.launchd.plist", content)


def render_template_files(
    config: DeployTargetConfig,
    clone_dir: Path,
    inventory: DeploymentInventory,
) -> dict[str, str]:
    runtime_template = render_agent_runtime_template(config, clone_dir, inventory)
    service_script_name, service_script_content = render_service_script(config, clone_dir)
    rendered = {
        "agent-runtime-config.template.json": json.dumps(
            runtime_template,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        service_script_name: service_script_content,
    }
    systemd_unit = render_systemd_unit(config, clone_dir)
    if systemd_unit:
        filename, content = systemd_unit
        rendered[filename] = content
    launchd_plist = render_launchd_plist(config, clone_dir)
    if launchd_plist:
        filename, content = launchd_plist
        rendered[filename] = content
    return rendered


def _remote_python_command(target_os: TargetOS) -> str:
    return "py -3" if target_os == "windows" else "python3"


def build_remote_bootstrap_command(config: DeployTargetConfig) -> list[str]:
    if config.ssh is None:
        raise DeployError("SSH settings are required when mode=ssh")

    local_mode_config = config.to_local_mode()
    config_payload = base64.b64encode(
        json.dumps(local_mode_config.to_dict(), ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    escaped_payload = config_payload.replace("\\", "\\\\").replace('"', '\\"')
    remote_command = (
        f'{_remote_python_command(config.target_os)} -c "import base64, json, pathlib, subprocess, sys; '
        f'cfg=json.loads(base64.b64decode(\\"{escaped_payload}\\").decode(\\"utf-8\\")); '
        f'clone_dir=pathlib.Path(cfg[\\"clone_dir\\"]); '
        f'repo_url=cfg[\\"repo_url\\"]; '
        f'repo_branch=cfg[\\"repo_branch\\"]; '
        f'git_dir=clone_dir / \\".git\\"; '
        f'git_dir.exists() and subprocess.run([\\"git\\", \\"-C\\", str(clone_dir), \\"fetch\\", \\"--all\\"], check=True); '
        f'git_dir.exists() and subprocess.run([\\"git\\", \\"-C\\", str(clone_dir), \\"checkout\\", repo_branch], check=True); '
        f'git_dir.exists() and subprocess.run([\\"git\\", \\"-C\\", str(clone_dir), \\"pull\\", \\"--ff-only\\", \\"origin\\", repo_branch], check=True); '
        f'(not git_dir.exists()) and clone_dir.parent.mkdir(parents=True, exist_ok=True); '
        f'(not git_dir.exists()) and subprocess.run([\\"git\\", \\"clone\\", \\"--branch\\", repo_branch, repo_url, str(clone_dir)], check=True); '
        f'config_path=clone_dir / \\".deploy-agent-config.json\\"; '
        f'config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + \\"\\\\n\\", encoding=\\"utf-8\\"); '
        f'script_path=clone_dir / \\"scripts\\" / \\"deploy_agent_skills.py\\"; '
        f'\\"deploy_agent_skills.py --mode local\\"; '
        f'args=[sys.executable, str(script_path), \\"--config\\", str(config_path), \\"--mode\\", \\"local\\", \\"--target-os\\", cfg[\\"target_os\\"]]; '
        f'cfg.get(\\"dry_run\\") and args.append(\\"--dry-run\\"); '
        f'subprocess.run(args, check=True)"'
    )

    command = ["ssh"]
    if config.ssh.port:
        command.extend(["-p", str(config.ssh.port)])
    if config.ssh.identity_file:
        command.extend(["-i", config.ssh.identity_file])
    destination = config.ssh.host
    if config.ssh.user:
        destination = f"{config.ssh.user}@{destination}"
    command.extend([destination, remote_command])
    return command


def _ensure_qmd_for_deploy(config: DeployTargetConfig) -> str:
    existing = shutil.which("qmd")
    if existing:
        return existing
    if not config.qmd.install_if_missing:
        raise DeployError("qmd is not installed and install_if_missing is disabled.")
    if not config.qmd.install_machine_tools:
        raise DeployError(
            "qmd is not installed and qmd.install_machine_tools is false. Install qmd manually or enable machine tool bootstrap."
        )

    npm_path = shutil.which("npm")
    node_exists = shutil.which("node") is not None
    if config.target_os == "windows":
        winget_path = shutil.which("winget")
        if not node_exists:
            if not winget_path:
                raise DeployError("Node.js is missing and winget is not available for automatic qmd installation.")
            run_command(
                [
                    winget_path,
                    "install",
                    "-e",
                    "--id",
                    "OpenJS.NodeJS.LTS",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                ],
                timeout=1800,
            )
        run_command([npm_path or "npm", "install", "-g", "@tobilu/qmd"], timeout=1800)
    else:
        if not npm_path:
            if config.target_os == "macos":
                brew_path = shutil.which("brew")
                if not brew_path:
                    raise DeployError("Homebrew is required to install Node.js/qmd automatically on macOS.")
                run_command([brew_path, "install", "node"], timeout=1800)
            elif config.target_os == "linux":
                apt_get_path = shutil.which("apt-get")
                dnf_path = shutil.which("dnf")
                yum_path = shutil.which("yum")
                if apt_get_path:
                    run_command(["sudo", apt_get_path, "update"], timeout=1800)
                    run_command(["sudo", apt_get_path, "install", "-y", "nodejs", "npm"], timeout=1800)
                elif dnf_path:
                    run_command(["sudo", dnf_path, "install", "-y", "nodejs", "npm"], timeout=1800)
                elif yum_path:
                    run_command(["sudo", yum_path, "install", "-y", "nodejs", "npm"], timeout=1800)
                else:
                    raise DeployError("No supported package manager found to install Node.js and npm automatically.")
            npm_path = shutil.which("npm")
        run_command([npm_path or "npm", "install", "-g", "@tobilu/qmd"], timeout=1800)

    refreshed = shutil.which("qmd")
    if not refreshed:
        raise DeployError("qmd is still not available after the install attempt.")
    return refreshed


def _install_requirement_files(python_path: Path, clone_dir: Path, requirements_files: Sequence[str]) -> None:
    for relative_path in requirements_files:
        run_command(
            [
                str(python_path),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "-r",
                str(clone_dir / relative_path),
            ],
            timeout=1200,
        )


def _copy_directory(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def ensure_repo_checkout(config: DeployTargetConfig) -> list[list[str]]:
    steps = plan_repo_checkout_steps(config.repo_url, config.repo_branch, config.clone_dir)
    if len(steps) == 1:
        config.clone_dir.parent.mkdir(parents=True, exist_ok=True)
    for command in steps:
        run_command(command, timeout=1800)
    return steps


def sync_deployment_bundle(
    source_root: Path,
    config: DeployTargetConfig,
    inventory: DeploymentInventory,
) -> list[str]:
    config.agent_skill_dir.mkdir(parents=True, exist_ok=True)
    shared_root = config.agent_skill_dir / "_shared_runtime"
    copied_items: list[str] = []
    for relative_path in inventory.skill_directories:
        source = source_root / relative_path
        destination = config.agent_skill_dir / Path(relative_path).name
        _copy_directory(source, destination)
        copied_items.append(destination.as_posix())
    for relative_path in inventory.shared_runtime_files:
        source = source_root / relative_path
        destination = shared_root / relative_path
        _copy_file(source, destination)
        copied_items.append(destination.as_posix())
    return copied_items


def write_template_files(
    config: DeployTargetConfig,
    clone_dir: Path,
    inventory: DeploymentInventory,
) -> list[str]:
    config.template_output_dir.mkdir(parents=True, exist_ok=True)
    rendered_templates = render_template_files(config, clone_dir, inventory)
    written_paths: list[str] = []
    for filename, content in rendered_templates.items():
        target_path = config.template_output_dir / filename
        target_path.write_text(content, encoding="utf-8")
        written_paths.append(target_path.as_posix())
    summary_path = config.template_output_dir / "deploy-summary.json"
    summary_payload = {
        "clone_dir": clone_dir.as_posix(),
        "agent_skill_dir": config.agent_skill_dir.as_posix(),
        "target_os": config.target_os,
        "mode": config.mode,
    }
    summary_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    written_paths.append(summary_path.as_posix())
    return written_paths


def launch_optional_services(
    config: DeployTargetConfig,
    clone_dir: Path,
) -> list[str]:
    started_services: list[str] = []
    if config.qmd.enabled and config.qmd.start:
        qmd_executable = _ensure_qmd_for_deploy(config)
        ensure_mcp_daemon(
            qmd_executable,
            restart=config.qmd.restart,
            host=config.qmd.host,
            port=config.qmd.port,
        )
        started_services.append("qmd mcp --http --daemon")
    if config.wechat_decrypt.enabled and config.wechat_decrypt.launch_web_ui:
        python_path = target_venv_python(clone_dir, config.target_os)
        process = subprocess.Popen(
            [str(python_path), str(clone_dir / WECHAT_DECRYPT_WEB_SCRIPT)],
            cwd=clone_dir / "wechat-router" / "wechat-decrypt",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        started_services.append(f"wechat-decrypt web ui pid={process.pid}")
    return started_services


def execute_local_deploy(config: DeployTargetConfig, source_repo_root: Path) -> DeploySummary:
    bootstrap_plan = build_machine_bootstrap_plan(config)
    dependency_plan = build_dependency_plan(config, config.clone_dir)
    repo_checkout_steps = plan_repo_checkout_steps(config.repo_url, config.repo_branch, config.clone_dir)
    manual_steps = list(
        dict.fromkeys([*bootstrap_plan.manual_steps, *dependency_plan.manual_steps])
    )
    if config.dry_run:
        return DeploySummary(
            mode="local",
            dry_run=True,
            repo_checkout_steps=repo_checkout_steps,
            detected_tools=list(bootstrap_plan.detected_tools),
            automated_steps=list(bootstrap_plan.automated_steps),
            manual_steps=manual_steps,
        )

    for command in bootstrap_plan.automated_commands:
        run_command(command, timeout=1800)
    if shutil.which("git") is None:
        raise DeployError("Git is not available after bootstrap planning. Install it manually and rerun deploy.")
    ensure_repo_checkout(config)
    inventory = build_default_inventory(config.clone_dir)
    python_path = create_or_reuse_venv(config.clone_dir)
    install_python_packages(python_path, REQUIRED_PYTHON_PACKAGES)
    _install_requirement_files(python_path, config.clone_dir, dependency_plan.requirements_files)
    started_services = launch_optional_services(config, config.clone_dir)
    copied_items = sync_deployment_bundle(config.clone_dir, config, inventory)
    template_files = write_template_files(config, config.clone_dir, inventory)
    return DeploySummary(
        mode="local",
        dry_run=False,
        repo_checkout_steps=repo_checkout_steps,
        copied_items=copied_items,
        template_files=template_files,
        started_services=started_services,
        detected_tools=list(bootstrap_plan.detected_tools),
        automated_steps=list(bootstrap_plan.automated_steps),
        manual_steps=manual_steps,
    )


def execute_ssh_deploy(config: DeployTargetConfig) -> DeploySummary:
    ssh_command = build_remote_bootstrap_command(config)
    repo_checkout_steps = [
        ["ssh", "remote-bootstrap", config.clone_dir.as_posix()],
    ]
    if not config.dry_run:
        completed = subprocess.run(ssh_command, text=True)
        if completed.returncode != 0:
            raise DeployError(f"Remote deployment failed with exit code {completed.returncode}")
    dependency_plan = build_dependency_plan(config, config.clone_dir)
    return DeploySummary(
        mode="ssh",
        dry_run=config.dry_run,
        repo_checkout_steps=repo_checkout_steps,
        ssh_command=ssh_command,
        manual_steps=list(dependency_plan.manual_steps),
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy repo-owned skills to an OpenClaw-like runtime.")
    parser.add_argument("--config", type=Path, required=True, help="Path to the target deployment JSON config.")
    parser.add_argument("--mode", choices=["local", "ssh"], default=None, help="Optional deploy mode override.")
    parser.add_argument("--target-os", choices=["windows", "linux", "macos"], default=None, help="Optional target OS override.")
    parser.add_argument("--repo-url", default=None, help="Optional repo URL override.")
    parser.add_argument("--repo-branch", default=None, help="Optional repo branch override.")
    parser.add_argument("--clone-dir", type=Path, default=None, help="Optional clone destination override.")
    parser.add_argument("--skill-dir", type=Path, default=None, help="Optional agent skill directory override.")
    parser.add_argument("--template-output-dir", type=Path, default=None, help="Optional template output directory override.")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without mutating the target host.")
    return parser.parse_args(argv)


def apply_cli_overrides(config: DeployTargetConfig, args: argparse.Namespace) -> DeployTargetConfig:
    return DeployTargetConfig(
        mode=args.mode or config.mode,
        target_os=_parse_target_os(args.target_os or config.target_os),
        repo_url=args.repo_url or config.repo_url,
        repo_branch=args.repo_branch or config.repo_branch,
        clone_dir=_coerce_path(args.clone_dir or config.clone_dir),
        agent_skill_dir=_coerce_path(args.skill_dir or config.agent_skill_dir),
        template_output_dir=_coerce_path(args.template_output_dir or config.template_output_dir),
        dry_run=bool(args.dry_run or config.dry_run),
        qmd=config.qmd,
        optional_components=config.optional_components,
        wechat_decrypt=config.wechat_decrypt,
        ssh=config.ssh,
    )


def print_summary(summary: DeploySummary) -> None:
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = apply_cli_overrides(load_target_config(args.config), args)
    source_repo_root = Path(__file__).resolve().parent.parent

    if config.mode == "ssh":
        summary = execute_ssh_deploy(config)
    else:
        summary = execute_local_deploy(config, source_repo_root)
    print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
