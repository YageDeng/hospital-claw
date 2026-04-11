"""Scenario registry and execution helpers for the skill E2E harness."""

from __future__ import annotations

import json
import locale
import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from importlib.util import find_spec
from pathlib import Path
from typing import Callable, Literal, Sequence
from urllib.error import URLError
from urllib.request import Request, urlopen

from skill_e2e_probes import ProbeOutcome, probes_enabled, run_agent_probe

StatusValue = Literal["PASS", "FAIL", "SKIP"]


@dataclass
class SkillE2EContext:
    workspace_root: Path
    artifact_root: Path
    python_executable: str = sys.executable
    allow_live: bool = False
    environment: dict[str, str] = field(default_factory=lambda: dict(os.environ))
    timeout_seconds: int = 180

    def scenario_dir(self, scenario_id: str) -> Path:
        path = self.artifact_root / scenario_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def fixture_root(self) -> Path:
        return self.workspace_root / "tests" / "fixtures" / "skill_e2e"


@dataclass
class ScenarioResult:
    scenario_id: str
    skill_id: str
    status: StatusValue
    summary: str
    details: list[str] = field(default_factory=list)
    artifacts: list[Path | str] = field(default_factory=list)
    live: bool = False
    optional_probe: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "skill_id": self.skill_id,
            "status": self.status,
            "summary": self.summary,
            "details": list(self.details),
            "artifacts": [
                artifact.as_posix() if isinstance(artifact, Path) else str(artifact)
                for artifact in self.artifacts
            ],
            "live": self.live,
            "optional_probe": self.optional_probe,
        }


@dataclass
class SkillScenario:
    scenario_id: str
    skill_id: str
    description: str
    runner: Callable[[SkillE2EContext], ScenarioResult] = field(repr=False)
    live: bool = False
    optional_probe: bool = False


def build_default_context(
    workspace_root: Path | None = None,
    *,
    allow_live: bool = False,
    artifact_root: Path | None = None,
) -> SkillE2EContext:
    root = (workspace_root or Path(__file__).resolve().parent.parent).resolve()
    resolved_artifact_root = (artifact_root or (root / "data" / "skill_e2e")).resolve()
    resolved_artifact_root.mkdir(parents=True, exist_ok=True)
    return SkillE2EContext(
        workspace_root=root,
        artifact_root=resolved_artifact_root,
        python_executable=sys.executable,
        allow_live=allow_live,
    )


def list_scenarios(*, include_probes: bool = False) -> list[SkillScenario]:
    scenarios = [
        SkillScenario(
            scenario_id="review_db_local",
            skill_id="tcm-treatment-review",
            description="Exercise the review_db CLI with deterministic fixtures.",
            runner=_run_review_db_local,
        ),
        SkillScenario(
            scenario_id="tcm_treatment_plan_prereqs",
            skill_id="tcm-treatment-plan",
            description="Validate KB or static-fallback prerequisites for treatment planning.",
            runner=_run_tcm_treatment_plan_prereqs,
        ),
        SkillScenario(
            scenario_id="sh_yb_policy_monitor_live",
            skill_id="sh-yb-policy-monitor",
            description="Fetch recent Shanghai policy content into a harness-owned output directory.",
            runner=_run_sh_yb_policy_monitor_live,
            live=True,
        ),
        SkillScenario(
            scenario_id="knowledge_base_docs_live",
            skill_id="knowledge-base-update",
            description="Run the docs-mode KB refresh flow against a temporary workspace.",
            runner=_run_knowledge_base_docs_live,
            live=True,
        ),
        SkillScenario(
            scenario_id="knowledge_base_rules_live",
            skill_id="knowledge-base-update",
            description="Run the rules-mode KB refresh flow against a temporary workspace.",
            runner=_run_knowledge_base_rules_live,
            live=True,
        ),
        SkillScenario(
            scenario_id="wechat_daily_monitor_manual_url",
            skill_id="wechat-daily-monitor",
            description="Fetch a live WeChat article into a temporary workspace and verify KB side effects.",
            runner=_run_wechat_daily_monitor_manual_url,
            live=True,
        ),
    ]
    if include_probes:
        scenarios.extend(
            [
                SkillScenario(
                    scenario_id="tcm_treatment_review_agent_probe",
                    skill_id="tcm-treatment-review",
                    description="Optional external agent probe for the treatment-review skill prompt path.",
                    runner=_run_tcm_treatment_review_agent_probe,
                    optional_probe=True,
                ),
                SkillScenario(
                    scenario_id="wechat_daily_monitor_discovered_probe",
                    skill_id="wechat-daily-monitor",
                    description="Optional external agent probe for discovered-link WeChat monitoring.",
                    runner=_run_wechat_daily_monitor_discovered_probe,
                    optional_probe=True,
                    live=True,
                ),
            ]
        )
    return scenarios


def select_scenarios(
    requested_ids: Sequence[str] | None = None,
    *,
    include_probes: bool = False,
) -> list[SkillScenario]:
    scenarios = list_scenarios(include_probes=include_probes)
    if not requested_ids:
        return scenarios

    scenario_map = {scenario.scenario_id: scenario for scenario in scenarios}
    missing = [scenario_id for scenario_id in requested_ids if scenario_id not in scenario_map]
    if missing:
        raise ValueError(f"Unknown scenario id(s): {', '.join(missing)}")
    return [scenario_map[scenario_id] for scenario_id in requested_ids]


def run_selected_scenarios(
    context: SkillE2EContext,
    requested_ids: Sequence[str] | None = None,
    *,
    include_probes: bool = False,
) -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    for scenario in select_scenarios(requested_ids, include_probes=include_probes):
        if scenario.live and not context.allow_live:
            results.append(
                _skip_result(
                    scenario.scenario_id,
                    scenario.skill_id,
                    "Live scenario skipped because --allow-live was not provided",
                    live=scenario.live,
                    optional_probe=scenario.optional_probe,
                )
            )
            continue
        try:
            result = scenario.runner(context)
            result.live = result.live or scenario.live
            result.optional_probe = result.optional_probe or scenario.optional_probe
            results.append(result)
        except Exception as error:  # pragma: no cover - last-resort safety net
            results.append(
                _fail_result(
                    scenario.scenario_id,
                    scenario.skill_id,
                    f"Unhandled exception: {error}",
                    live=scenario.live,
                    optional_probe=scenario.optional_probe,
                )
            )
    return results


def _pass_result(
    scenario_id: str,
    skill_id: str,
    summary: str,
    *,
    details: Sequence[str] | None = None,
    artifacts: Sequence[Path | str] | None = None,
    live: bool = False,
    optional_probe: bool = False,
) -> ScenarioResult:
    return ScenarioResult(
        scenario_id=scenario_id,
        skill_id=skill_id,
        status="PASS",
        summary=summary,
        details=list(details or []),
        artifacts=list(artifacts or []),
        live=live,
        optional_probe=optional_probe,
    )


def _skip_result(
    scenario_id: str,
    skill_id: str,
    summary: str,
    *,
    details: Sequence[str] | None = None,
    artifacts: Sequence[Path | str] | None = None,
    live: bool = False,
    optional_probe: bool = False,
) -> ScenarioResult:
    return ScenarioResult(
        scenario_id=scenario_id,
        skill_id=skill_id,
        status="SKIP",
        summary=summary,
        details=list(details or []),
        artifacts=list(artifacts or []),
        live=live,
        optional_probe=optional_probe,
    )


def _fail_result(
    scenario_id: str,
    skill_id: str,
    summary: str,
    *,
    details: Sequence[str] | None = None,
    artifacts: Sequence[Path | str] | None = None,
    live: bool = False,
    optional_probe: bool = False,
) -> ScenarioResult:
    return ScenarioResult(
        scenario_id=scenario_id,
        skill_id=skill_id,
        status="FAIL",
        summary=summary,
        details=list(details or []),
        artifacts=list(artifacts or []),
        live=live,
        optional_probe=optional_probe,
    )


def _script_path(context: SkillE2EContext, relative_path: str) -> Path:
    return (context.workspace_root / relative_path).resolve()


def _module_available(module_name: str) -> bool:
    return find_spec(module_name) is not None


def _command_exists(command_name: str) -> bool:
    return shutil.which(command_name) is not None


def _run_subprocess(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    normalized_command = list(command)
    if os.name == "nt" and normalized_command:
        executable = normalized_command[0]
        if "\\" not in executable and "/" not in executable:
            resolved = shutil.which(executable, path=env.get("PATH"))
            if resolved:
                normalized_command[0] = resolved

    completed = subprocess.run(
        normalized_command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=False,
        timeout=timeout,
        check=False,
    )
    return subprocess.CompletedProcess(
        args=completed.args,
        returncode=completed.returncode,
        stdout=_decode_subprocess_output(completed.stdout),
        stderr=_decode_subprocess_output(completed.stderr),
    )


def _decode_subprocess_output(data: bytes | None) -> str:
    if not data:
        return ""

    tried: set[str] = set()
    for encoding in ["utf-8", locale.getpreferredencoding(False)]:
        normalized = (encoding or "").lower()
        if not normalized or normalized in tried:
            continue
        tried.add(normalized)
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue

    return data.decode("utf-8", errors="replace")


def _run_python_script(
    context: SkillE2EContext,
    script_relative_path: str,
    *args: str,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [context.python_executable, str(_script_path(context, script_relative_path)), *args]
    return _run_subprocess(
        command,
        cwd=cwd or context.workspace_root,
        env=context.environment,
        timeout=context.timeout_seconds,
    )


def _can_reach_url(url: str, timeout: int = 10) -> bool:
    request = Request(url, headers={"User-Agent": "skill-e2e-harness/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return getattr(response, "status", 200) < 500
    except (URLError, TimeoutError, ValueError):
        return False


def _unique_collection_name(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _remove_collection_if_exists(
    context: SkillE2EContext,
    collection_name: str,
    *,
    cwd: Path,
) -> None:
    if not _command_exists("qmd"):
        return
    _run_subprocess(
        ["qmd", "collection", "remove", collection_name],
        cwd=cwd,
        env=context.environment,
        timeout=context.timeout_seconds,
    )


def _write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _prefixed_result_details(prefix: str, summary: str, details: Sequence[str]) -> list[str]:
    items = list(details)
    if summary and summary not in items:
        items.insert(0, summary)
    return [f"{prefix}: {item}" for item in items]


def _unique_artifacts(artifacts: Sequence[Path | str]) -> list[Path | str]:
    deduped: list[Path | str] = []
    seen: set[str] = set()
    for artifact in artifacts:
        key = artifact.as_posix() if isinstance(artifact, Path) else str(artifact)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(artifact)
    return deduped


def _split_multiline_values(raw_value: str) -> list[str]:
    values = [line.strip() for line in raw_value.splitlines() if line.strip()]
    if values:
        return values
    stripped = raw_value.strip()
    return [stripped] if stripped else []


def _load_json_from_stdout(completed: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return json.loads(completed.stdout.strip())


def _prepare_temp_workspace(context: SkillE2EContext, scenario_id: str) -> Path:
    scenario_dir = context.scenario_dir(scenario_id)
    temp_root = scenario_dir / "workspace"
    if temp_root.exists():
        shutil.rmtree(temp_root)
    temp_root.mkdir(parents=True, exist_ok=True)
    return temp_root


def _run_review_db_local(context: SkillE2EContext) -> ScenarioResult:
    scenario_id = "review_db_local"
    skill_id = "tcm-treatment-review"
    scenario_dir = context.scenario_dir(scenario_id)
    fixture_dir = context.fixture_root() / "review_db"
    fixtures = sorted(fixture_dir.glob("*.json"))
    if not fixtures:
        return _fail_result(scenario_id, skill_id, "Review DB fixtures are missing")

    db_path = scenario_dir / "reviews.db"
    if db_path.exists():
        db_path.unlink()

    init_run = _run_python_script(
        context,
        "scripts/review_db.py",
        "init",
        "--image-count",
        "3",
        "--db",
        str(db_path),
    )
    if init_run.returncode != 0:
        return _fail_result(
            scenario_id,
            skill_id,
            "review_db init failed",
            details=[init_run.stderr.strip() or init_run.stdout.strip()],
        )

    session_id = str(_load_json_from_stdout(init_run)["session_id"])

    for fixture in fixtures:
        save_run = _run_python_script(
            context,
            "scripts/review_db.py",
            "save",
            "--session",
            session_id,
            "--json-file",
            str(fixture),
            "--db",
            str(db_path),
        )
        if save_run.returncode != 0:
            return _fail_result(
                scenario_id,
                skill_id,
                f"Failed to save review fixture `{fixture.name}`",
                details=[save_run.stderr.strip() or save_run.stdout.strip()],
            )

    status_run = _run_python_script(
        context,
        "scripts/review_db.py",
        "status",
        "--session",
        session_id,
        "--db",
        str(db_path),
    )
    summary_run = _run_python_script(
        context,
        "scripts/review_db.py",
        "summary",
        "--session",
        session_id,
        "--db",
        str(db_path),
    )
    export_run = _run_python_script(
        context,
        "scripts/review_db.py",
        "export",
        "--session",
        session_id,
        "--db",
        str(db_path),
    )

    if status_run.returncode != 0 or summary_run.returncode != 0 or export_run.returncode != 0:
        return _fail_result(
            scenario_id,
            skill_id,
            "review_db follow-up commands failed",
            details=[
                detail
                for detail in [
                    status_run.stderr.strip(),
                    summary_run.stderr.strip(),
                    export_run.stderr.strip(),
                ]
                if detail
            ],
        )

    status_payload = _load_json_from_stdout(status_run)
    export_payload = _load_json_from_stdout(export_run)
    summary_text = summary_run.stdout.strip()

    _write_text(scenario_dir / "status.json", json.dumps(status_payload, ensure_ascii=False, indent=2) + "\n")
    _write_text(scenario_dir / "export.json", json.dumps(export_payload, ensure_ascii=False, indent=2) + "\n")
    _write_text(scenario_dir / "summary.md", summary_text + "\n")

    if status_payload.get("reviewed_count") != 3 or not status_payload.get("is_complete"):
        return _fail_result(
            scenario_id,
            skill_id,
            "review_db status did not report a complete 3-image session",
            details=[json.dumps(status_payload, ensure_ascii=False)],
            artifacts=[db_path, scenario_dir / "status.json"],
        )

    results = export_payload.get("results", [])
    if not isinstance(results, list) or len(results) != len(fixtures):
        return _fail_result(
            scenario_id,
            skill_id,
            "review_db export did not contain the expected number of rows",
            details=[json.dumps(export_payload, ensure_ascii=False)],
            artifacts=[scenario_dir / "export.json"],
        )

    if "治疗单批量审查报告" not in summary_text:
        return _fail_result(
            scenario_id,
            skill_id,
            "review_db summary output did not contain the expected report header",
            details=[summary_text],
            artifacts=[scenario_dir / "summary.md"],
        )

    return _pass_result(
        scenario_id,
        skill_id,
        "review_db CLI completed a full batch session using committed fixtures",
        details=[
            f"session_id={session_id}",
            f"saved_rows={len(results)}",
        ],
        artifacts=[
            db_path,
            scenario_dir / "status.json",
            scenario_dir / "export.json",
            scenario_dir / "summary.md",
        ],
    )


def _run_tcm_treatment_plan_prereq_subcheck(context: SkillE2EContext) -> ScenarioResult:
    scenario_id = "tcm_treatment_plan_prereqs"
    skill_id = "tcm-treatment-plan"
    details: list[str] = []

    fallback_paths = [
        context.workspace_root / "skills" / "tcm-treatment-review" / "standards.md",
        context.workspace_root / "skills" / "tcm-treatment-review" / "SKILL.md",
        context.workspace_root / "skills" / "tcm-treatment-plan" / "SKILL.md",
    ]
    fallback_available = [path for path in fallback_paths if path.exists()]

    if _command_exists("qmd"):
        qmd_run = _run_subprocess(
            ["qmd", "--version"],
            cwd=context.workspace_root,
            env=context.environment,
            timeout=context.timeout_seconds,
        )
        if qmd_run.returncode == 0:
            details.append(f"qmd={qmd_run.stdout.strip()}")
            return _pass_result(
                scenario_id,
                skill_id,
                "qmd is available for KB-backed treatment-plan validation",
                details=details,
            )
        details.append(qmd_run.stderr.strip() or qmd_run.stdout.strip())

    if fallback_available:
        details.extend(f"fallback={path.as_posix()}" for path in fallback_available)
        return _pass_result(
            scenario_id,
            skill_id,
            "Static fallback assets are available even without a live KB session",
            details=details,
            artifacts=fallback_available,
        )

    return _fail_result(
        scenario_id,
        skill_id,
        "Neither qmd nor documented fallback assets are available",
        details=details,
    )


def _build_tcm_treatment_plan_probe_payload(context: SkillE2EContext) -> tuple[Path, dict[str, object]]:
    case_path = context.fixture_root() / "tcm_plan_case.json"
    if not case_path.exists():
        raise FileNotFoundError(f"Missing treatment-plan case fixture: {case_path}")

    case_payload = json.loads(case_path.read_text(encoding="utf-8"))
    if not isinstance(case_payload, dict):
        raise ValueError("Treatment-plan case fixture must contain a JSON object")

    payload = dict(case_payload)
    payload.setdefault(
        "required_sections",
        ["患者信息", "辨证分析", "治疗方案", "费用汇总", "数据来源"],
    )
    payload.setdefault(
        "required_patient_fields",
        ["gender", "age", "weight_kg", "chief_complaint", "optional_context"],
    )
    payload.setdefault(
        "expected_keywords",
        ["第一阶段", "第二阶段", "中医诊断", "单次费用", "治疗频次", "数据来源"],
    )
    payload["case_file"] = str(case_path)
    payload["case_data"] = case_payload
    return case_path, payload


def _run_tcm_treatment_plan_probe(
    context: SkillE2EContext,
    *,
    probe_name: str = "tcm_treatment_plan_prereqs",
) -> ProbeOutcome:
    _, payload = _build_tcm_treatment_plan_probe_payload(context)
    prompt = (
        "Use the treatment-plan skill on the committed synthetic patient case fixture. "
        "Return success only if the response is written in Chinese and includes patient info, "
        "diagnosis, at least two phased treatment sections, fee breakdowns, treatment frequency, "
        "and data-source notes."
    )
    return run_agent_probe(
        probe_name,
        prompt,
        context.workspace_root,
        payload,
        timeout=context.timeout_seconds,
        env=context.environment,
    )


def _run_tcm_treatment_plan_prereqs(context: SkillE2EContext) -> ScenarioResult:
    scenario_id = "tcm_treatment_plan_prereqs"
    skill_id = "tcm-treatment-plan"
    prereq_result = _run_tcm_treatment_plan_prereq_subcheck(context)
    probe_requested = probes_enabled(context.environment)
    details = _prefixed_result_details(
        "prereq",
        prereq_result.summary,
        prereq_result.details,
    )
    artifacts = _unique_artifacts(prereq_result.artifacts)

    if prereq_result.status == "FAIL":
        return _fail_result(
            scenario_id,
            skill_id,
            prereq_result.summary,
            details=details,
            artifacts=artifacts,
            optional_probe=probe_requested,
        )

    if not probe_requested:
        return _pass_result(
            scenario_id,
            skill_id,
            prereq_result.summary,
            details=details,
            artifacts=artifacts,
        )

    try:
        probe_outcome = _run_tcm_treatment_plan_probe(context)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as error:
        return _fail_result(
            scenario_id,
            skill_id,
            f"Treatment-plan probe setup failed: {error}",
            details=details,
            artifacts=artifacts,
            optional_probe=True,
        )

    details.extend(
        _prefixed_result_details(
            "probe",
            probe_outcome.summary,
            probe_outcome.details,
        )
    )
    artifacts = _unique_artifacts([*artifacts, *probe_outcome.artifacts])

    if probe_outcome.status == "PASS":
        return _pass_result(
            scenario_id,
            skill_id,
            "Composite treatment-plan validation passed",
            details=details,
            artifacts=artifacts,
            optional_probe=True,
        )

    if probe_outcome.status == "SKIP":
        return _skip_result(
            scenario_id,
            skill_id,
            f"Treatment-plan probe skipped after prerequisite validation: {probe_outcome.summary}",
            details=details,
            artifacts=artifacts,
            optional_probe=True,
        )

    return _fail_result(
        scenario_id,
        skill_id,
        f"Treatment-plan probe failed after prerequisite validation: {probe_outcome.summary}",
        details=details,
        artifacts=artifacts,
        optional_probe=True,
    )


def _run_sh_yb_policy_monitor_live(context: SkillE2EContext) -> ScenarioResult:
    scenario_id = "sh_yb_policy_monitor_live"
    skill_id = "sh-yb-policy-monitor"
    if not _module_available("requests") or not _module_available("bs4"):
        return _skip_result(
            scenario_id,
            skill_id,
            "Policy monitor dependencies are missing",
            details=["required: requests, bs4"],
        )
    if not _can_reach_url("https://ybj.sh.gov.cn"):
        return _skip_result(
            scenario_id,
            skill_id,
            "Shanghai policy site is not reachable from this machine",
        )

    scenario_dir = context.scenario_dir(scenario_id)
    output_dir = scenario_dir / "policies"
    output_dir.mkdir(parents=True, exist_ok=True)

    run = _run_python_script(
        context,
        "skills/sh-yb-policy-monitor/scripts/fetch_policies.py",
        "--days",
        "1",
        "--save-dir",
        str(output_dir),
    )
    _write_text(scenario_dir / "stdout.txt", run.stdout)
    _write_text(scenario_dir / "stderr.txt", run.stderr)

    if run.returncode != 0:
        return _fail_result(
            scenario_id,
            skill_id,
            "Policy monitor script exited with a non-zero status",
            details=[run.stderr.strip() or run.stdout.strip()],
            artifacts=[scenario_dir / "stdout.txt", scenario_dir / "stderr.txt"],
        )

    files = sorted(output_dir.glob("*.md"))
    error_markers = [text for text in [run.stderr.strip(), run.stdout.strip()] if "获取失败" in text]
    if error_markers:
        return _fail_result(
            scenario_id,
            skill_id,
            "Policy monitor script reported fetch errors",
            details=error_markers,
            artifacts=[scenario_dir / "stdout.txt", scenario_dir / "stderr.txt"],
        )

    no_updates_markers = [
        "无新发布内容",
        "三个栏目均无新发布内容",
    ]
    if not files and not any(marker in run.stdout for marker in no_updates_markers):
        return _fail_result(
            scenario_id,
            skill_id,
            "Policy monitor script produced no output files and no clean no-update summary",
            details=[run.stdout.strip(), run.stderr.strip()],
            artifacts=[scenario_dir / "stdout.txt", scenario_dir / "stderr.txt"],
        )

    details = [f"saved_files={len(files)}"]
    if "检查日期" in run.stdout:
        details.append("stdout includes date banner")

    return _pass_result(
        scenario_id,
        skill_id,
        "Policy monitor script completed against the live site",
        details=details,
        artifacts=[scenario_dir / "stdout.txt", *files[:5]],
    )


def _run_knowledge_base_docs_live(context: SkillE2EContext) -> ScenarioResult:
    scenario_id = "knowledge_base_docs_live"
    skill_id = "knowledge-base-update"
    required_modules = ["openpyxl", "fitz", "docx", "pptx"]
    missing_modules = [name for name in required_modules if not _module_available(name)]
    if not _command_exists("qmd"):
        return _skip_result(scenario_id, skill_id, "qmd is not installed")
    if missing_modules:
        return _skip_result(
            scenario_id,
            skill_id,
            "KB conversion dependencies are missing",
            details=[", ".join(missing_modules)],
        )

    temp_root = _prepare_temp_workspace(context, scenario_id)
    docs_root = temp_root / "docs" / "医院材料学习"
    kb_root = temp_root / "docs" / "knowledge-base"
    docs_root.mkdir(parents=True, exist_ok=True)
    (kb_root / ".staging").mkdir(parents=True, exist_ok=True)
    (kb_root / ".staging-binary-md").mkdir(parents=True, exist_ok=True)
    (kb_root / ".manual-rules").mkdir(parents=True, exist_ok=True)
    (kb_root / ".wiki-ingest-src").mkdir(parents=True, exist_ok=True)

    source_md = docs_root / "skill-e2e-source.md"
    source_md.write_text("# Skill E2E Source\n\nmarker: docs-flow\n", encoding="utf-8")

    from openpyxl import Workbook  # type: ignore[import-not-found]

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Sheet1"
    worksheet.append(["项目", "价格"])
    worksheet.append(["针法", 50])
    workbook_path = docs_root / "skill_e2e_prices.xlsx"
    workbook.save(workbook_path)

    xlsx_run = _run_python_script(
        context,
        "scripts/xlsx_to_markdown.py",
        "--input",
        str(docs_root),
        "--output",
        str(kb_root / ".staging"),
    )
    binary_run = _run_python_script(
        context,
        "scripts/binary_docs_to_markdown.py",
        "--input",
        str(docs_root),
        "--output",
        str(kb_root / ".staging-binary-md"),
    )
    manifest_run = _run_python_script(
        context,
        "scripts/update_kb_manifest.py",
        "--root",
        str(temp_root),
    )
    if xlsx_run.returncode != 0 or binary_run.returncode != 0 or manifest_run.returncode != 0:
        return _fail_result(
            scenario_id,
            skill_id,
            "KB docs flow commands failed",
            details=[
                detail
                for detail in [
                    xlsx_run.stderr.strip() or xlsx_run.stdout.strip(),
                    binary_run.stderr.strip() or binary_run.stdout.strip(),
                    manifest_run.stderr.strip() or manifest_run.stdout.strip(),
                ]
                if detail
            ],
        )

    manifest_path = kb_root / ".manifest.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_paths = {entry["path"] for entry in manifest_payload["files"]}
    expected_paths = {
        "docs/医院材料学习/skill-e2e-source.md",
        "docs/knowledge-base/.staging/skill_e2e_prices.md",
    }
    if not expected_paths.issubset(manifest_paths):
        return _fail_result(
            scenario_id,
            skill_id,
            "Manifest did not include the expected docs flow files",
            details=[json.dumps(sorted(manifest_paths), ensure_ascii=False)],
            artifacts=[manifest_path],
        )

    source_collection = _unique_collection_name("skill_e2e_source")
    xlsx_collection = _unique_collection_name("skill_e2e_xlsx")
    try:
        source_add = _run_subprocess(
            [
                "qmd",
                "collection",
                "add",
                str(docs_root),
                "--name",
                source_collection,
                "--mask",
                "**/*.md",
            ],
            cwd=temp_root,
            env=context.environment,
            timeout=context.timeout_seconds,
        )
        xlsx_add = _run_subprocess(
            [
                "qmd",
                "collection",
                "add",
                str(kb_root / ".staging"),
                "--name",
                xlsx_collection,
                "--mask",
                "**/*.md",
            ],
            cwd=temp_root,
            env=context.environment,
            timeout=context.timeout_seconds,
        )
    finally:
        _remove_collection_if_exists(context, source_collection, cwd=temp_root)
        _remove_collection_if_exists(context, xlsx_collection, cwd=temp_root)

    if source_add.returncode != 0 or xlsx_add.returncode != 0:
        return _fail_result(
            scenario_id,
            skill_id,
            "qmd collection add failed for the KB docs flow",
            details=[
                detail
                for detail in [
                    source_add.stderr.strip() or source_add.stdout.strip(),
                    xlsx_add.stderr.strip() or xlsx_add.stdout.strip(),
                ]
                if detail
            ],
            artifacts=[manifest_path],
        )

    return _pass_result(
        scenario_id,
        skill_id,
        "KB docs flow succeeded in a temporary workspace",
        details=[
            "source_md collection refresh succeeded",
            "xlsxmd collection refresh succeeded",
        ],
        artifacts=[manifest_path, source_md, kb_root / ".staging" / "skill_e2e_prices.md"],
    )


def _run_knowledge_base_rules_live(context: SkillE2EContext) -> ScenarioResult:
    scenario_id = "knowledge_base_rules_live"
    skill_id = "knowledge-base-update"
    if not _command_exists("qmd"):
        return _skip_result(scenario_id, skill_id, "qmd is not installed")

    temp_root = _prepare_temp_workspace(context, scenario_id)
    manual_rules_dir = temp_root / "docs" / "knowledge-base" / ".manual-rules"
    manual_rules_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = context.fixture_root() / "manual_rule.md"
    if not fixture_path.exists():
        return _fail_result(scenario_id, skill_id, "Manual-rule fixture is missing")

    target_rule = manual_rules_dir / "2026-04-11_skill-e2e-rule.md"
    target_rule.write_text(fixture_path.read_text(encoding="utf-8"), encoding="utf-8")

    manifest_run = _run_python_script(
        context,
        "scripts/update_kb_manifest.py",
        "--root",
        str(temp_root),
    )
    if manifest_run.returncode != 0:
        return _fail_result(
            scenario_id,
            skill_id,
            "KB rules manifest update failed",
            details=[manifest_run.stderr.strip() or manifest_run.stdout.strip()],
        )

    manifest_path = temp_root / "docs" / "knowledge-base" / ".manifest.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_paths = {entry["path"] for entry in manifest_payload["files"]}
    expected_rule = "docs/knowledge-base/.manual-rules/2026-04-11_skill-e2e-rule.md"
    if expected_rule not in manifest_paths:
        return _fail_result(
            scenario_id,
            skill_id,
            "Manifest did not include the injected manual rule",
            details=[json.dumps(sorted(manifest_paths), ensure_ascii=False)],
            artifacts=[manifest_path],
        )

    collection_name = _unique_collection_name("skill_e2e_rules")
    try:
        collection_add = _run_subprocess(
            [
                "qmd",
                "collection",
                "add",
                str(manual_rules_dir),
                "--name",
                collection_name,
                "--mask",
                "**/*.md",
            ],
            cwd=temp_root,
            env=context.environment,
            timeout=context.timeout_seconds,
        )
    finally:
        _remove_collection_if_exists(context, collection_name, cwd=temp_root)

    if collection_add.returncode != 0:
        return _fail_result(
            scenario_id,
            skill_id,
            "qmd collection add failed for the KB rules flow",
            details=[collection_add.stderr.strip() or collection_add.stdout.strip()],
            artifacts=[manifest_path],
        )

    return _pass_result(
        scenario_id,
        skill_id,
        "KB rules flow succeeded in a temporary workspace",
        artifacts=[manifest_path, target_rule],
    )


def _run_wechat_daily_monitor_manual_url(context: SkillE2EContext) -> ScenarioResult:
    scenario_id = "wechat_daily_monitor_manual_url"
    skill_id = "wechat-daily-monitor"
    wechat_urls = _split_multiline_values(context.environment.get("SKILL_E2E_WECHAT_URL", ""))
    if not wechat_urls:
        return _skip_result(
            scenario_id,
            skill_id,
            "SKILL_E2E_WECHAT_URL is not configured",
        )
    if not _command_exists("qmd"):
        return _skip_result(
            scenario_id,
            skill_id,
            "qmd is required to verify KB side effects for the WeChat scenario",
        )
    if not _can_reach_url("https://mp.weixin.qq.com"):
        return _skip_result(
            scenario_id,
            skill_id,
            "mp.weixin.qq.com is not reachable from this machine",
        )

    temp_root = _prepare_temp_workspace(context, scenario_id)
    output_root = temp_root / "docs" / "医院材料学习" / "公众号每日监测"
    output_root.mkdir(parents=True, exist_ok=True)

    pipeline_run = _run_python_script(
        context,
        "scripts/wechat_article_pipeline.py",
        *wechat_urls,
        "--output-dir",
        str(output_root),
        "--save-html",
    )
    if pipeline_run.returncode != 0:
        return _fail_result(
            scenario_id,
            skill_id,
            "WeChat article pipeline failed",
            details=[pipeline_run.stderr.strip() or pipeline_run.stdout.strip()],
        )

    report_dir = output_root / "_reports"
    report_files = sorted(report_dir.glob("*.json"))
    if not report_files:
        return _fail_result(
            scenario_id,
            skill_id,
            "No structured report was written by the WeChat pipeline",
            details=[pipeline_run.stdout.strip()],
        )
    report_path = report_files[-1]
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    articles = report_payload.get("articles", [])
    if not isinstance(articles, list) or not articles:
        return _fail_result(
            scenario_id,
            skill_id,
            "The WeChat pipeline report did not contain any article records",
            details=[json.dumps(report_payload, ensure_ascii=False)],
            artifacts=[report_path],
        )

    first_article = articles[0]
    article_dir = Path(str(first_article["local_path"]))
    markdown_path = Path(str(first_article["markdown_path"]))
    metadata_path = article_dir / "metadata.json"
    if not markdown_path.exists() or not metadata_path.exists():
        return _fail_result(
            scenario_id,
            skill_id,
            "Expected article outputs are missing",
            details=[f"markdown={markdown_path}", f"metadata={metadata_path}"],
            artifacts=[report_path],
        )

    manifest_run = _run_python_script(
        context,
        "scripts/update_kb_manifest.py",
        "--root",
        str(temp_root),
    )
    if manifest_run.returncode != 0:
        return _fail_result(
            scenario_id,
            skill_id,
            "Manifest refresh failed for the WeChat KB side-effect check",
            details=[manifest_run.stderr.strip() or manifest_run.stdout.strip()],
            artifacts=[report_path, markdown_path, metadata_path],
        )

    manifest_path = temp_root / "docs" / "knowledge-base" / ".manifest.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_paths = {entry["path"] for entry in manifest_payload["files"]}
    expected_relative = markdown_path.resolve().relative_to(temp_root.resolve()).as_posix()
    if expected_relative not in manifest_paths:
        return _fail_result(
            scenario_id,
            skill_id,
            "Manifest did not include the generated WeChat markdown file",
            details=[expected_relative],
            artifacts=[manifest_path, report_path],
        )

    collection_name = _unique_collection_name("skill_e2e_wechat")
    try:
        collection_add = _run_subprocess(
            [
                "qmd",
                "collection",
                "add",
                str(temp_root / "docs" / "医院材料学习"),
                "--name",
                collection_name,
                "--mask",
                "**/*.md",
            ],
            cwd=temp_root,
            env=context.environment,
            timeout=context.timeout_seconds,
        )
    finally:
        _remove_collection_if_exists(context, collection_name, cwd=temp_root)

    if collection_add.returncode != 0:
        return _fail_result(
            scenario_id,
            skill_id,
            "qmd collection add failed for the WeChat KB side-effect check",
            details=[collection_add.stderr.strip() or collection_add.stdout.strip()],
            artifacts=[manifest_path, report_path],
        )

    return _pass_result(
        scenario_id,
        skill_id,
        "Manual-url WeChat monitoring completed with KB side effects in a temporary workspace",
        details=[f"articles={len(articles)}"],
        artifacts=[report_path, markdown_path, metadata_path, manifest_path],
    )


def _probe_result_to_scenario(
    scenario_id: str,
    skill_id: str,
    outcome: ProbeOutcome,
    *,
    live: bool = False,
    optional_probe: bool = True,
) -> ScenarioResult:
    return ScenarioResult(
        scenario_id=scenario_id,
        skill_id=skill_id,
        status=outcome.status,
        summary=outcome.summary,
        details=outcome.details,
        artifacts=outcome.artifacts,
        live=live,
        optional_probe=optional_probe,
    )


def _run_tcm_treatment_review_agent_probe(context: SkillE2EContext) -> ScenarioResult:
    scenario_id = "tcm_treatment_review_agent_probe"
    prompt = (
        "Use the treatment-review skill flow on deterministic fixture inputs and "
        "return whether the expected seven-dimension review structure was produced."
    )
    payload = {
        "fixture_dir": str(context.fixture_root() / "review_db"),
        "expected_keywords": ["合格", "不合格", "七大维度"],
    }
    return _probe_result_to_scenario(
        scenario_id,
        "tcm-treatment-review",
        run_agent_probe(
            scenario_id,
            prompt,
            context.workspace_root,
            payload,
            timeout=context.timeout_seconds,
            env=context.environment,
        ),
    )


def _run_tcm_treatment_plan_agent_probe(context: SkillE2EContext) -> ScenarioResult:
    return _probe_result_to_scenario(
        "tcm_treatment_plan_agent_probe",
        "tcm-treatment-plan",
        _run_tcm_treatment_plan_probe(
            context,
            probe_name="tcm_treatment_plan_agent_probe",
        ),
    )


def _run_wechat_daily_monitor_discovered_probe(context: SkillE2EContext) -> ScenarioResult:
    scenario_id = "wechat_daily_monitor_discovered_probe"
    prompt = (
        "Use the discovered-link branch of the wechat-daily-monitor skill. "
        "Only proceed if local WeChat discovery data is available."
    )
    payload = {
        "discovery_hint": context.environment.get("SKILL_E2E_WECHAT_DISCOVERY_HINT", ""),
        "expected_keywords": ["urgent_alerts", "daily_summary", "weekly_candidates"],
    }
    return _probe_result_to_scenario(
        scenario_id,
        "wechat-daily-monitor",
        run_agent_probe(
            scenario_id,
            prompt,
            context.workspace_root,
            payload,
            timeout=context.timeout_seconds,
            env=context.environment,
        ),
        live=True,
    )
