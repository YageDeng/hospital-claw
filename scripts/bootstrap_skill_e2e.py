"""Bootstrap the local skill E2E harness.

This script prepares the local environment and then invokes the existing
`run_skill_e2e.py` runner.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import venv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REQUIRED_PYTHON_PACKAGES = [
    "requests",
    "beautifulsoup4",
    "openpyxl",
    "pymupdf",
    "python-docx",
    "python-pptx",
]

DEFAULT_MCP_HOST = "localhost"
DEFAULT_MCP_PORT = 8181


class BootstrapError(RuntimeError):
    """Raised when bootstrap setup cannot proceed."""


@dataclass
class BootstrapConfig:
    workspace_root: Path
    allow_live: bool = False
    wechat_url: str | None = None
    json_out: Path | None = None
    markdown_out: Path | None = None
    install_machine_tools: bool = False
    restart_mcp: bool = False
    scenarios: list[str] = field(default_factory=list)
    skip_python_install: bool = False
    mcp_host: str = DEFAULT_MCP_HOST
    mcp_port: int = DEFAULT_MCP_PORT


def default_wechat_url_path(workspace_root: Path) -> Path:
    return workspace_root / "data" / "skill_e2e" / "default_wechat_url.txt"


def default_report_paths(workspace_root: Path, *, today: date | None = None) -> tuple[Path, Path]:
    stamp = (today or date.today()).isoformat()
    return (
        workspace_root / "data" / "skill_e2e" / "latest-bootstrap-report.json",
        workspace_root
        / "docs"
        / "superpowers"
        / "test-results"
        / f"{stamp}-local-all-skills-e2e-bootstrap.md",
    )


def build_runner_env(config: BootstrapConfig, base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env or os.environ)
    if config.wechat_url:
        env["SKILL_E2E_WECHAT_URL"] = config.wechat_url
    elif not env.get("SKILL_E2E_WECHAT_URL"):
        local_default = default_wechat_url_path(config.workspace_root)
        if local_default.exists():
            value = local_default.read_text(encoding="utf-8").strip()
            if value:
                env["SKILL_E2E_WECHAT_URL"] = value
    return env


def build_harness_command(config: BootstrapConfig, python_executable: str) -> list[str]:
    command = [
        python_executable,
        (config.workspace_root / "scripts" / "run_skill_e2e.py").resolve().as_posix(),
    ]
    if config.allow_live:
        command.append("--allow-live")
    for scenario in config.scenarios:
        command.extend(["--scenario", scenario])
    if config.json_out:
        command.extend(["--json-out", config.json_out.as_posix()])
    if config.markdown_out:
        command.extend(["--markdown-out", config.markdown_out.as_posix()])
    return command


def build_machine_install_commands(
    *,
    platform: str,
    node_exists: bool,
    npm_path: str | None,
    winget_path: str | None,
) -> list[list[str]]:
    if platform != "win32":
        raise BootstrapError("Automatic machine-tool installation is only implemented for Windows.")
    if not npm_path:
        raise BootstrapError("npm is required for machine-level qmd installation.")

    commands: list[list[str]] = []
    if not node_exists:
        if not winget_path:
            raise BootstrapError("Node.js is missing and winget is not available for automatic installation.")
        commands.append(
            [
                winget_path,
                "install",
                "-e",
                "--id",
                "OpenJS.NodeJS.LTS",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ]
        )
    commands.append([npm_path, "install", "-g", "@tobilu/qmd"])
    return commands


def run_command(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 300,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip()
        raise BootstrapError(f"Command failed ({' '.join(command)}): {stderr}")
    return completed


def workspace_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent


def venv_dir(workspace_root: Path) -> Path:
    return workspace_root / ".venv"


def venv_python(workspace_root: Path) -> Path:
    root = venv_dir(workspace_root)
    if os.name == "nt":
        return root / "Scripts" / "python.exe"
    return root / "bin" / "python"


def create_or_reuse_venv(workspace_root: Path) -> Path:
    target = venv_dir(workspace_root)
    python_path = venv_python(workspace_root)
    if python_path.exists():
        return python_path
    if target.exists():
        shutil.rmtree(target)
    builder = venv.EnvBuilder(with_pip=True)
    builder.create(target)
    if not python_path.exists():
        raise BootstrapError(f"Failed to create venv at {target}")
    return python_path


def has_pip(python_path: Path) -> bool:
    completed = run_command([str(python_path), "-m", "pip", "--version"], check=False)
    return completed.returncode == 0


def ensure_pip(python_path: Path) -> None:
    if has_pip(python_path):
        return
    completed = run_command(
        [str(python_path), "-m", "ensurepip", "--upgrade"],
        check=False,
    )
    if completed.returncode != 0 or not has_pip(python_path):
        raise BootstrapError("Could not make pip available inside the project venv.")


def install_python_packages(python_path: Path, packages: Sequence[str]) -> None:
    ensure_pip(python_path)
    run_command(
        [
            str(python_path),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            *packages,
        ],
        timeout=1200,
    )


def detect_qmd() -> str | None:
    return shutil.which("qmd")


def is_mcp_http_ready(host: str, port: int, timeout: float = 2.0) -> bool:
    url = f"http://{host}:{port}/mcp"
    request = Request(url, headers={"User-Agent": "skill-e2e-bootstrap/1.0"})
    try:
        with urlopen(request, timeout=timeout):
            return True
    except HTTPError:
        return True
    except URLError:
        return False


def _mcp_probe_hosts(host: str) -> list[str]:
    hosts = [host, "localhost", "127.0.0.1"]
    deduped: list[str] = []
    for item in hosts:
        if item not in deduped:
            deduped.append(item)
    return deduped


def ensure_mcp_daemon(
    qmd_executable: str,
    *,
    restart: bool = False,
    host: str = DEFAULT_MCP_HOST,
    port: int = DEFAULT_MCP_PORT,
    ready_timeout: int = 30,
) -> str:
    def any_ready() -> bool:
        return any(is_mcp_http_ready(candidate, port) for candidate in _mcp_probe_hosts(host))

    if restart:
        run_command([qmd_executable, "mcp", "stop"], check=False)
    elif any_ready():
        return "reused"

    run_command([qmd_executable, "mcp", "--http", "--daemon"], timeout=120)
    deadline = time.time() + ready_timeout
    while time.time() < deadline:
        if any_ready():
            return "started"
        time.sleep(1)
    raise BootstrapError(f"qmd MCP did not become ready on {host}:{port}")


def ensure_qmd(
    *,
    install_machine_tools: bool,
) -> str:
    existing = detect_qmd()
    if existing:
        return existing

    if not install_machine_tools:
        raise BootstrapError(
            "qmd is not installed. Install it first or rerun with --install-machine-tools."
        )

    npm_path = shutil.which("npm")
    winget_path = shutil.which("winget")
    node_exists = shutil.which("node") is not None
    commands = build_machine_install_commands(
        platform=sys.platform,
        node_exists=node_exists,
        npm_path=npm_path,
        winget_path=winget_path,
    )
    for command in commands:
        run_command(command, timeout=1800)

    refreshed = detect_qmd()
    if not refreshed:
        raise BootstrapError(
            "qmd is still not available after the install attempt. Reopen the shell or install manually."
        )
    return refreshed


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap and run local skill E2E validation.")
    parser.add_argument(
        "--allow-live",
        action="store_true",
        help="Pass --allow-live to the underlying skill E2E harness.",
    )
    parser.add_argument(
        "--wechat-url",
        help="Set SKILL_E2E_WECHAT_URL for the live WeChat scenario.",
    )
    parser.add_argument("--json-out", type=Path, default=None, help="Optional JSON report output path.")
    parser.add_argument("--markdown-out", type=Path, default=None, help="Optional Markdown report output path.")
    parser.add_argument(
        "--install-machine-tools",
        action="store_true",
        help="Attempt machine-level qmd installation when qmd is missing.",
    )
    parser.add_argument(
        "--restart-mcp",
        action="store_true",
        help="Restart qmd MCP instead of reusing an already-healthy daemon.",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        help="Run only the named harness scenario id. May be repeated.",
    )
    parser.add_argument(
        "--skip-python-install",
        action="store_true",
        help="Skip Python package installation into the project venv.",
    )
    return parser.parse_args(argv)


def build_config(args: argparse.Namespace) -> BootstrapConfig:
    workspace_root = workspace_root_from_script()
    json_out, markdown_out = default_report_paths(workspace_root)
    return BootstrapConfig(
        workspace_root=workspace_root,
        allow_live=args.allow_live,
        wechat_url=args.wechat_url,
        json_out=args.json_out or json_out,
        markdown_out=args.markdown_out or markdown_out,
        install_machine_tools=args.install_machine_tools,
        restart_mcp=args.restart_mcp,
        scenarios=list(args.scenario),
        skip_python_install=args.skip_python_install,
    )


def run_harness(config: BootstrapConfig, python_path: Path, env: dict[str, str]) -> int:
    command = build_harness_command(config, str(python_path))
    completed = subprocess.run(
        command,
        cwd=config.workspace_root,
        env=env,
        text=True,
    )
    return completed.returncode


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = build_config(args)

    python_path = create_or_reuse_venv(config.workspace_root)
    if not config.skip_python_install:
        install_python_packages(python_path, REQUIRED_PYTHON_PACKAGES)

    qmd_executable = ensure_qmd(install_machine_tools=config.install_machine_tools)
    ensure_mcp_daemon(
        qmd_executable,
        restart=config.restart_mcp,
        host=config.mcp_host,
        port=config.mcp_port,
    )

    env = build_runner_env(config)
    return run_harness(config, python_path, env)


if __name__ == "__main__":
    raise SystemExit(main())
