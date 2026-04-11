"""CLI runner for the local skill E2E harness."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from skill_e2e_matrix import (
    ScenarioResult,
    build_default_context,
    list_scenarios,
    run_selected_scenarios,
)


def _escape_markdown_cell(value: str) -> str:
    return value.replace("\n", " ").replace("|", "\\|").strip()


def summarize_results(results: Sequence[ScenarioResult]) -> dict[str, int]:
    summary = {"PASS": 0, "FAIL": 0, "SKIP": 0, "total": len(results)}
    for result in results:
        summary[result.status] += 1
    return summary


def exit_code_from_results(results: Sequence[ScenarioResult]) -> int:
    return 1 if any(result.status == "FAIL" for result in results) else 0


def render_markdown_report(results: Sequence[ScenarioResult]) -> str:
    summary = summarize_results(results)
    lines = [
        "# Skill E2E Report",
        "",
        f"- **Generated at**: {datetime.now(tz=timezone.utc).isoformat()}",
        f"- **Total scenarios**: {summary['total']}",
        "",
        "## Summary",
        "",
        "| Status | Count |",
        "|--------|-------|",
        f"| PASS | {summary['PASS']} |",
        f"| FAIL | {summary['FAIL']} |",
        f"| SKIP | {summary['SKIP']} |",
        "",
        "## Scenarios",
        "",
        "| Scenario | Skill | Status | Summary |",
        "|----------|-------|--------|---------|",
    ]
    for result in results:
        lines.append(
            "| {scenario} | {skill} | {status} | {summary} |".format(
                scenario=_escape_markdown_cell(result.scenario_id),
                skill=_escape_markdown_cell(result.skill_id),
                status=_escape_markdown_cell(result.status),
                summary=_escape_markdown_cell(result.summary),
            )
        )
    return "\n".join(lines) + "\n"


def write_json_report(path: Path, results: Sequence[ScenarioResult]) -> None:
    payload = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "summary": summarize_results(results),
        "results": [result.to_dict() for result in results],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(path: Path, results: Sequence[ScenarioResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown_report(results), encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local skill E2E scenarios.")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available scenarios and exit.",
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
        "--json-out",
        type=Path,
        default=None,
        help="Optional JSON report output path.",
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=None,
        help="Optional Markdown report output path.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    include_probes = os.environ.get("SKILL_E2E_ENABLE_PROBES", "").strip() == "1"

    if args.list:
        for scenario in list_scenarios(include_probes=include_probes):
            live_marker = " [live]" if scenario.live else ""
            probe_marker = " [probe]" if scenario.optional_probe else ""
            print(f"{scenario.scenario_id}: {scenario.skill_id}{live_marker}{probe_marker}")
            print(f"  {scenario.description}")
        return 0

    context = build_default_context(allow_live=args.allow_live)
    try:
        results = run_selected_scenarios(
            context,
            requested_ids=args.scenario or None,
            include_probes=include_probes,
        )
    except ValueError as error:
        print(f"Unknown scenario selection: {error}", file=sys.stderr)
        return 1

    for result in results:
        print(f"{result.status} {result.scenario_id}: {result.summary}")

    summary = summarize_results(results)
    print(
        f"Summary: PASS={summary['PASS']} FAIL={summary['FAIL']} "
        f"SKIP={summary['SKIP']} TOTAL={summary['total']}"
    )

    if args.json_out:
        write_json_report(args.json_out, results)
    if args.markdown_out:
        write_markdown_report(args.markdown_out, results)

    return exit_code_from_results(results)


if __name__ == "__main__":
    raise SystemExit(main())
