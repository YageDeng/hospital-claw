"""Gemma E2E driver for hospital-claw skill evaluation.

Drives skill E2E scenarios using a local Gemma model via Ollama's
OpenAI-Compatible API. This script is the Gemma counterpart to
run_skill_e2e.py -- it uses the same skill_e2e_matrix registry
but routes agent-probe requests to the local Gemma endpoint instead
of an external API.

Usage:
    python scripts/run_gemma_skill_e2e.py --model gemma3:4b --allow-live
    python scripts/run_gemma_skill_e2e.py --list

Environment variables:
    OLLAMA_BASE_URL      Ollama base URL (default: http://127.0.0.1:11434)
    OLLAMA_MODEL         Model name (default: gemma3:4b)
    GEMMA_MAX_TOKENS     Max tokens for generation (default: 2048)
    GEMMA_TEMPERATURE    Temperature (default: 0.0)
    SKILL_E2E_ENABLE_PROBES  Set to 1 to enable agent probes (default: 0)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

# Ensure the repo root is on the path so we can import skill_e2e_matrix etc.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from skill_e2e_matrix import (
    ScenarioResult,
    build_default_context,
    list_scenarios,
    run_selected_scenarios,
)
from skill_e2e_probes import ProbeOutcome, probes_enabled


# ---------------------------------------------------------------------------
# Gemma client (OpenAI-compatible)
# ---------------------------------------------------------------------------

def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "gemma3:4b"


class GemmaClient:
    """Lightweight OpenAI-compatible client for Ollama Gemma."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> None:
        self.base_url = (base_url or _env("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)).rstrip("/")
        self.model = model or _env("OLLAMA_MODEL", DEFAULT_MODEL)
        self.max_tokens = int(_env("GEMMA_MAX_TOKENS", str(max_tokens)))
        self.temperature = float(_env("GEMMA_TEMPERATURE", str(temperature)))

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        """Send a prompt to the local Gemma model and return the response text."""
        try:
            import httpx
        except ImportError:
            raise RuntimeError(
                "httpx is required for Gemma integration. Install with: pip install httpx"
            )

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": False,
        }

        with httpx.Client(timeout=120.0) as client:
            response = client.post(f"{self.base_url}/v1/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def is_available(self) -> bool:
        """Check whether the Ollama API is reachable."""
        try:
            import httpx
        except ImportError:
            return False
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(f"{self.base_url}/v1/models")
                return r.status_code == 200
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Probe runner (overrides skill_e2e_probes for Gemma)
# ---------------------------------------------------------------------------

def run_gemma_probe(
    probe_name: str,
    prompt: str,
    workspace_root: Path,
    payload: dict[str, Any] | None = None,
    timeout: int = 600,
    env: dict[str, str] | None = None,
) -> ProbeOutcome:
    """Run an agent probe using the local Gemma model."""
    environment = dict(os.environ)
    if env:
        environment.update(env)

    if not probes_enabled(environment):
        return ProbeOutcome(
            status="SKIP",
            summary="Optional agent probes are disabled",
        )

    # Build system prompt for medical-domain adaptation
    system_prompt = (
        "You are a helpful AI assistant specialized in Traditional Chinese Medicine (TCM) "
        "hospital operations. You are evaluating the hospital-claw skill system. "
        "Follow the user's instructions precisely and respond in Chinese where appropriate. "
        "Be thorough and accurate."
    )

    gemma_client = GemmaClient(
        base_url=_env("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL),
        model=_env("OLLAMA_MODEL", DEFAULT_MODEL),
    )

    if not gemma_client.is_available():
        return ProbeOutcome(
            status="FAIL",
            summary=f"Ollama is not reachable at {gemma_client.base_url}. Is 'ollama serve' running?",
        )

    artifact_dir = workspace_root / "data" / "skill_e2e" / "probe_payloads"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    payload_path = artifact_dir / f"{probe_name}.json"
    request_payload = {
        "probe_name": probe_name,
        "prompt": prompt,
        "payload": payload or {},
        "workspace_root": str(workspace_root),
        "model": gemma_client.model,
        "base_url": gemma_client.base_url,
    }
    payload_path.write_text(
        json.dumps(request_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    start = time.monotonic()
    try:
        result_text = gemma_client.complete(prompt, system=system_prompt)
    except Exception as exc:
        return ProbeOutcome(
            status="FAIL",
            summary=f"Gemma probe `{probe_name}` failed: {exc}",
            details=[f"timeout={timeout}s"],
            artifacts=[payload_path],
        )
    elapsed = time.monotonic() - start

    result_payload = {
        "probe_name": probe_name,
        "elapsed_seconds": round(elapsed, 1),
        "model": gemma_client.model,
        "result": result_text,
    }
    result_path = artifact_dir / f"{probe_name}_result.json"
    result_path.write_text(
        json.dumps(result_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return ProbeOutcome(
        status="PASS",
        summary=f"Gemma probe `{probe_name}` completed in {elapsed:.1f}s",
        details=[
            f"model={gemma_client.model}",
            f"elapsed={elapsed:.1f}s",
            f"output_chars={len(result_text)}",
        ],
        artifacts=[payload_path, result_path],
    )


# ---------------------------------------------------------------------------
# Result output helpers (mirrors run_skill_e2e.py)
# ---------------------------------------------------------------------------

def _escape_md(value: str) -> str:
    return value.replace("\n", " ").replace("|", "\\|").strip()


def summarize_results(results: Sequence[ScenarioResult]) -> dict[str, int]:
    summary: dict[str, int] = {"PASS": 0, "FAIL": 0, "SKIP": 0, "total": len(results)}
    for result in results:
        summary[result.status] += 1
    return summary


def render_markdown_report(
    results: Sequence[ScenarioResult],
    gemma_client: GemmaClient,
    elapsed_seconds: float,
) -> str:
    summary = summarize_results(results)
    lines = [
        "# Gemma Skill E2E Evaluation Report",
        "",
        f"- **Generated at**: {datetime.now(tz=timezone.utc).isoformat()}",
        f"- **Model**: {gemma_client.model} @ {gemma_client.base_url}",
        f"- **Total scenarios**: {summary['total']}",
        f"- **Elapsed**: {elapsed_seconds:.1f}s",
        "",
        "## Summary",
        "",
        "| Status | Count |",
        "|--------|-------|",
        f"| PASS   | {summary['PASS']} |",
        f"| FAIL   | {summary['FAIL']} |",
        f"| SKIP   | {summary['SKIP']} |",
        "",
        "## Scenarios",
        "",
        "| Scenario | Skill | Status | Summary |",
        "|----------|-------|--------|---------|",
    ]
    for result in results:
        lines.append(
            "| {id} | {skill} | {status} | {summary} |".format(
                id=_escape_md(result.scenario_id),
                skill=_escape_md(result.skill_id),
                status=_escape_md(result.status),
                summary=_escape_md(result.summary),
            )
        )
    lines.append("")
    return "\n".join(lines)


def write_json_report(path: Path, results: Sequence[ScenarioResult], *, model: str) -> None:
    payload = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "model": model,
        "summary": summarize_results(results),
        "results": [result.to_dict() for result in results],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(
    path: Path,
    results: Sequence[ScenarioResult],
    gemma_client: GemmaClient,
    elapsed_seconds: float,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_markdown_report(results, gemma_client, elapsed_seconds),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run skill E2E scenarios with a local Gemma model via Ollama."
    )
    parser.add_argument(
        "--list", action="store_true", help="List available scenarios and exit."
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        help="Run only the named scenario id. May be repeated.",
    )
    parser.add_argument(
        "--allow-live",
        action="store_true",
        help="Allow live scenarios that use qmd, network, or other external dependencies.",
    )
    parser.add_argument(
        "--model",
        default=_env("OLLAMA_MODEL", DEFAULT_MODEL),
        help=f"Model name (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--ollama-url",
        dest="ollama_url",
        default=_env("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL),
        help="Ollama base URL (default: http://127.0.0.1:11434)",
    )
    parser.add_argument(
        "--json-out", type=Path, default=None, help="Optional JSON report output path."
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=None,
        help="Optional Markdown report output path.",
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=None,
        help="Optional artifact root for scenario outputs.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    include_probes = os.environ.get("SKILL_E2E_ENABLE_PROBES", "").strip() == "1"

    gemma_client = GemmaClient(base_url=args.ollama_url, model=args.model)

    # Pre-flight: warn if Ollama is not reachable
    if not gemma_client.is_available():
        print(
            f"[WARN] Ollama is not reachable at {gemma_client.base_url}.",
            file=sys.stderr,
        )
        print(
            f"[WARN] Please start 'ollama serve' and try again.",
            file=sys.stderr,
        )
        print(
            f"[WARN] Agent probes will FAIL until Ollama is available.",
            file=sys.stderr,
        )
        print(
            f"[WARN] Continuing anyway (scenarios will run without Gemma probes)...",
            file=sys.stderr,
        )

    if args.list:
        for scenario in list_scenarios(include_probes=include_probes):
            markers = []
            if scenario.live:
                markers.append(" [live]")
            if scenario.optional_probe:
                markers.append(" [probe]")
            print(f"{scenario.scenario_id}: {scenario.skill_id}{''.join(markers)}")
            print(f"  {scenario.description}")
        return 0

    context = build_default_context(
        allow_live=args.allow_live,
        artifact_root=args.artifact_root,
    )

    start = time.monotonic()
    try:
        results = run_selected_scenarios(
            context,
            requested_ids=args.scenario or None,
            include_probes=include_probes,
        )
    except ValueError as error:
        print(f"Unknown scenario selection: {error}", file=sys.stderr)
        return 1
    elapsed = time.monotonic() - start

    for result in results:
        print(f"{result.status} {result.scenario_id}: {result.summary}")

    summary = summarize_results(results)
    print(
        f"Summary: PASS={summary['PASS']} FAIL={summary['FAIL']} "
        f"SKIP={summary['SKIP']} TOTAL={summary['total']} ({elapsed:.1f}s)"
    )

    if args.json_out:
        write_json_report(args.json_out, results, model=args.model)
        print(f"JSON report written to {args.json_out}")
    if args.markdown_out:
        write_markdown_report(args.markdown_out, results, gemma_client, elapsed)
        print(f"Markdown report written to {args.markdown_out}")

    return 1 if any(r.status == "FAIL" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
