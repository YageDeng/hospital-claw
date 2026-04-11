"""Verify a WorkBuddy deployment created by deploy_agent_skills.py."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from deploy_agent_skills import SHARED_RUNTIME_FILES  # type: ignore[import-not-found]

StatusValue = Literal["pass", "fail", "skip", "cannot_prove_from_filesystem"]


@dataclass
class CheckResult:
    name: str
    status: StatusValue
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
        }


@dataclass
class VerificationReport:
    config_checks: list[CheckResult]
    skill_checks: list[CheckResult]
    runtime_file_checks: list[CheckResult]
    live_checks: list[CheckResult]
    summary: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "config_checks": [check.to_dict() for check in self.config_checks],
            "skill_checks": [check.to_dict() for check in self.skill_checks],
            "runtime_file_checks": [check.to_dict() for check in self.runtime_file_checks],
            "live_checks": [check.to_dict() for check in self.live_checks],
            "summary": dict(self.summary),
        }


def summarize_results(results: Sequence[CheckResult]) -> dict[str, int]:
    summary = {
        "pass": 0,
        "fail": 0,
        "skip": 0,
        "cannot_prove_from_filesystem": 0,
        "total": len(results),
    }
    for result in results:
        summary[result.status] += 1
    return summary


def _load_json_file(path: Path, check_name: str) -> tuple[dict[str, Any] | None, CheckResult]:
    if not path.exists():
        return None, CheckResult(check_name, "fail", f"Missing file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return None, CheckResult(check_name, "fail", f"Invalid JSON in {path}: {error}")
    if not isinstance(payload, dict):
        return None, CheckResult(check_name, "fail", f"Expected a JSON object in {path}")
    return payload, CheckResult(check_name, "pass", f"Loaded {path}")


def _path_from_payload(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(value).expanduser()


def _probeable_path_exists(path_value: str | None) -> tuple[Path | None, bool]:
    path = _path_from_payload(path_value)
    if path is None:
        return None, False
    return path, path.exists()


def probe_qmd_http(url: str, timeout: float = 2.0) -> CheckResult:
    request = Request(url, headers={"User-Agent": "workbuddy-deploy-check/1.0"})
    try:
        with urlopen(request, timeout=timeout):
            return CheckResult("qmd_http", "pass", f"qmd MCP responded at {url}")
    except HTTPError as error:
        return CheckResult(
            "qmd_http",
            "pass",
            f"qmd MCP endpoint at {url} returned HTTP {error.code}, which still confirms reachability",
        )
    except URLError as error:
        return CheckResult("qmd_http", "fail", f"Could not reach qmd MCP at {url}: {error}")


def probe_wechat_stdio(command: str, args: Sequence[str], timeout: float = 2.0) -> CheckResult:
    try:
        process = subprocess.Popen(
            [command, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as error:
        return CheckResult("wechat_stdio", "fail", f"Could not start wechat MCP process: {error}")

    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            process.kill()
        return CheckResult(
            "wechat_stdio",
            "pass",
            "wechat MCP process started successfully and stayed alive past the probe timeout",
        )

    details = stderr.strip() or stdout.strip() or f"Exited with code {process.returncode}"
    return CheckResult(
        "wechat_stdio",
        "fail",
        f"wechat MCP process exited too early with code {process.returncode}: {details}",
    )


def verify_workbuddy_deploy(
    root: Path,
    *,
    check_qmd: bool = False,
    check_wechat_mcp: bool = False,
    timeout: float = 2.0,
) -> VerificationReport:
    resolved_root = root.expanduser().resolve()

    mcp_payload, mcp_check = _load_json_file(resolved_root / "mcp.json", "mcp_json_parseable")
    settings_payload, settings_check = _load_json_file(
        resolved_root / "settings.json",
        "settings_json_parseable",
    )
    template_payload, template_check = _load_json_file(
        resolved_root / "generated" / "agent-runtime-config.template.json",
        "generated_template_parseable",
    )
    deploy_summary_payload, deploy_summary_check = _load_json_file(
        resolved_root / "generated" / "deploy-summary.json",
        "deploy_summary_parseable",
    )
    deploy_config_payload, deploy_config_check = _load_json_file(
        resolved_root / "agent_deploy.local.json",
        "deploy_config_parseable",
    )

    config_checks = [
        mcp_check,
        settings_check,
        template_check,
        deploy_summary_check,
        deploy_config_check,
    ]

    if mcp_payload is not None and template_payload is not None:
        if mcp_payload.get("mcpServers") == template_payload.get("mcpServers"):
            config_checks.append(
                CheckResult(
                    "mcp_servers_match_template",
                    "pass",
                    "Live WorkBuddy MCP config matches the generated deployment template",
                )
            )
        else:
            config_checks.append(
                CheckResult(
                    "mcp_servers_match_template",
                    "fail",
                    "Live WorkBuddy MCP config does not match the generated deployment template",
                )
            )
    else:
        config_checks.append(
            CheckResult(
                "mcp_servers_match_template",
                "skip",
                "Skipped because either mcp.json or the generated template could not be loaded",
            )
        )

    if (
        deploy_summary_payload is not None
        and deploy_config_payload is not None
        and template_payload is not None
    ):
        clone_match = (
            deploy_summary_payload.get("clone_dir") == deploy_config_payload.get("clone_dir") == template_payload.get("repoCloneDir")
        )
        skill_dir_match = (
            deploy_summary_payload.get("agent_skill_dir") == deploy_config_payload.get("agent_skill_dir") == template_payload.get("skillsDir")
        )
        if clone_match and skill_dir_match:
            config_checks.append(
                CheckResult(
                    "deploy_paths_match_config",
                    "pass",
                    "Deploy summary, generated template, and local deploy config agree on clone and skill directories",
                )
            )
        else:
            config_checks.append(
                CheckResult(
                    "deploy_paths_match_config",
                    "fail",
                    "Deploy summary, generated template, and local deploy config disagree on clone or skill directories",
                )
            )
    else:
        config_checks.append(
            CheckResult(
                "deploy_paths_match_config",
                "skip",
                "Skipped because a required deploy config artifact could not be loaded",
            )
        )

    config_checks.append(
        CheckResult(
            "runtime_load_confirmation",
            "cannot_prove_from_filesystem",
            "No WorkBuddy log or state file in the checked paths confirms that the app has loaded the deployed skills and MCP servers",
        )
    )

    skill_checks: list[CheckResult] = []
    runtime_file_checks: list[CheckResult] = []
    expected_skills = list(template_payload.get("skills", [])) if template_payload is not None else []
    skills_dir = _path_from_payload(template_payload.get("skillsDir")) if template_payload is not None else None
    shared_runtime_dir = _path_from_payload(template_payload.get("sharedRuntimeDir")) if template_payload is not None else None

    for skill_name in expected_skills:
        skill_file = (skills_dir / skill_name / "SKILL.md") if skills_dir is not None else None
        if skill_file and skill_file.exists():
            skill_checks.append(
                CheckResult(
                    f"skill_{skill_name}",
                    "pass",
                    f"Found deployed skill file: {skill_file}",
                )
            )
        else:
            skill_checks.append(
                CheckResult(
                    f"skill_{skill_name}",
                    "fail",
                    f"Missing deployed skill file for `{skill_name}`",
                )
            )

    if shared_runtime_dir is not None:
        for relative_path in SHARED_RUNTIME_FILES:
            runtime_path = shared_runtime_dir / relative_path
            check_name = f"shared_runtime_{relative_path.replace('/', '_')}"
            if runtime_path.exists():
                runtime_file_checks.append(
                    CheckResult(check_name, "pass", f"Found shared runtime file: {runtime_path}")
                )
            else:
                runtime_file_checks.append(
                    CheckResult(check_name, "fail", f"Missing shared runtime file: {runtime_path}")
                )
    else:
        runtime_file_checks.append(
            CheckResult(
                "shared_runtime_dir_present",
                "fail",
                "Generated template did not provide a shared runtime directory",
            )
        )

    mcp_servers = mcp_payload.get("mcpServers", {}) if mcp_payload is not None else {}
    wechat_mcp = mcp_servers.get("wechat", {}) if isinstance(mcp_servers, dict) else {}
    wechat_command_path, command_exists = _probeable_path_exists(
        wechat_mcp.get("command") if isinstance(wechat_mcp, dict) else None
    )
    runtime_file_checks.append(
        CheckResult(
            "wechat_stdio_command_exists",
            "pass" if command_exists else "fail",
            f"wechat stdio command {'exists' if command_exists else 'is missing'}: {wechat_command_path}",
        )
    )
    for index, arg in enumerate(wechat_mcp.get("args", []) if isinstance(wechat_mcp, dict) else []):
        arg_path, arg_exists = _probeable_path_exists(arg)
        runtime_file_checks.append(
            CheckResult(
                f"wechat_stdio_arg_{index}_exists",
                "pass" if arg_exists else "fail",
                f"wechat stdio arg {index} {'exists' if arg_exists else 'is missing'}: {arg_path}",
            )
        )

    live_checks: list[CheckResult] = []
    qmd_mcp = mcp_servers.get("qmd", {}) if isinstance(mcp_servers, dict) else {}
    if check_qmd and isinstance(qmd_mcp, dict) and isinstance(qmd_mcp.get("url"), str):
        live_checks.append(probe_qmd_http(qmd_mcp["url"], timeout=timeout))
    else:
        live_checks.append(
            CheckResult("qmd_http", "skip", "qmd live probe not requested")
        )

    if check_wechat_mcp and isinstance(wechat_mcp, dict):
        command = wechat_mcp.get("command")
        args = wechat_mcp.get("args", [])
        if isinstance(command, str) and isinstance(args, list):
            live_checks.append(
                probe_wechat_stdio(command, [str(item) for item in args], timeout=timeout)
            )
        else:
            live_checks.append(
                CheckResult(
                    "wechat_stdio",
                    "fail",
                    "wechat MCP configuration is missing a valid stdio command or args list",
                )
            )
    else:
        live_checks.append(
            CheckResult("wechat_stdio", "skip", "wechat MCP live probe not requested")
        )

    all_results = [*config_checks, *skill_checks, *runtime_file_checks, *live_checks]
    return VerificationReport(
        config_checks=config_checks,
        skill_checks=skill_checks,
        runtime_file_checks=runtime_file_checks,
        live_checks=live_checks,
        summary=summarize_results(all_results),
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a WorkBuddy deployment.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.home() / ".workbuddy",
        help="Path to the WorkBuddy home directory. Defaults to ~/.workbuddy",
    )
    parser.add_argument(
        "--check-qmd",
        action="store_true",
        help="Run a live HTTP probe against the configured qmd MCP server.",
    )
    parser.add_argument(
        "--check-wechat-mcp",
        action="store_true",
        help="Run a live stdio process-start probe against the configured wechat MCP server.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=2.0,
        help="Timeout in seconds for optional live probes.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = verify_workbuddy_deploy(
        args.root,
        check_qmd=args.check_qmd,
        check_wechat_mcp=args.check_wechat_mcp,
        timeout=args.timeout,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 1 if report.summary["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
