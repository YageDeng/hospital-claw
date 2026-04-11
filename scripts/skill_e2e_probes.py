"""Optional agent-probe support for skill E2E scenarios.

The local harness defaults to concrete CLI/integration checks. These helpers
allow a scenario to delegate to an external agent driver only when explicitly
configured by the operator.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

StatusValue = Literal["PASS", "FAIL", "SKIP"]

@dataclass
class ProbeOutcome:
    status: StatusValue
    summary: str
    details: list[str] = field(default_factory=list)
    artifacts: list[Path] = field(default_factory=list)


def probes_enabled(env: dict[str, str] | None = None) -> bool:
    source = env or os.environ
    return source.get("SKILL_E2E_ENABLE_PROBES", "").strip() == "1"


def probe_driver_command(env: dict[str, str] | None = None) -> str | None:
    source = env or os.environ
    command = source.get("SKILL_E2E_AGENT_DRIVER", "").strip()
    return command or None


def run_agent_probe(
    probe_name: str,
    prompt: str,
    workspace_root: Path,
    payload: dict[str, Any] | None = None,
    timeout: int = 600,
    env: dict[str, str] | None = None,
) -> ProbeOutcome:
    environment = dict(os.environ)
    if env:
        environment.update(env)

    if not probes_enabled(environment):
        return ProbeOutcome(
            status="SKIP",
            summary="Optional agent probes are disabled",
        )

    driver = probe_driver_command(environment)
    if not driver:
        return ProbeOutcome(
            status="SKIP",
            summary="SKILL_E2E_AGENT_DRIVER is not configured",
        )

    request_payload = {
        "probe_name": probe_name,
        "prompt": prompt,
        "payload": payload or {},
        "workspace_root": str(workspace_root),
    }

    artifact_dir = workspace_root / "data" / "skill_e2e" / "probe_payloads"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    payload_path = artifact_dir / f"{probe_name}.json"
    payload_path.write_text(
        json.dumps(request_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    command_parts = shlex.split(driver, posix=os.name != "nt")
    if any("{payload}" in part for part in command_parts):
        command = [part.replace("{payload}", str(payload_path)) for part in command_parts]
    else:
        command = [*command_parts, str(payload_path)]

    try:
        completed = subprocess.run(
            command,
            cwd=workspace_root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except OSError as error:
        return ProbeOutcome(
            status="FAIL",
            summary=f"Probe driver failed to start: {error}",
            artifacts=[payload_path],
        )
    except subprocess.TimeoutExpired:
        return ProbeOutcome(
            status="FAIL",
            summary=f"Probe timed out after {timeout}s",
            artifacts=[payload_path],
        )

    details: list[str] = []
    if completed.stdout.strip():
        details.append(f"stdout: {completed.stdout.strip()}")
    if completed.stderr.strip():
        details.append(f"stderr: {completed.stderr.strip()}")

    if completed.returncode != 0:
        return ProbeOutcome(
            status="FAIL",
            summary=f"Probe driver exited with code {completed.returncode}",
            details=details,
            artifacts=[payload_path],
        )

    summary = completed.stdout.strip() or f"Probe `{probe_name}` completed"
    return ProbeOutcome(
        status="PASS",
        summary=summary,
        details=details,
        artifacts=[payload_path],
    )
