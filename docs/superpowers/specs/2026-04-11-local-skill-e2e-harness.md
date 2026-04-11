# Local Skill E2E Harness

**Date:** 2026-04-11  
**Status:** Implemented

## Purpose

This repo now includes a local-live-with-skips E2E harness for all repo-owned root skills:

- `skills/tcm-treatment-review/SKILL.md`
- `skills/tcm-treatment-plan/SKILL.md`
- `skills/sh-yb-policy-monitor/SKILL.md`
- `skills/knowledge-base-update/SKILL.md`
- `skills/wechat-daily-monitor/SKILL.md`

The harness is designed for this machine and this repository checkout. It does **not** replace the mac mini / OpenClaw host validation flow from the OpenClaw checklist. Host-only validation remains a separate manual step.

## Entry Points

- Runner CLI: `scripts/run_skill_e2e.py`
- Bootstrap CLI: `scripts/bootstrap_skill_e2e.py`
- Windows wrapper: `scripts/bootstrap_skill_e2e.ps1`
- Scenario registry: `scripts/skill_e2e_matrix.py`
- Optional probe adapter: `scripts/skill_e2e_probes.py`

Default runtime artifacts are written under ignored paths:

- `data/skill_e2e/`

Optional reports can be written anywhere, including:

- `docs/superpowers/test-results/`

When you run the bootstrap entry point, it supplies default JSON and Markdown report paths automatically unless you override them.

## Commands

### Direct harness commands

```powershell
cd c:\Users\roger\Documents\Pyproject\Personal-git\hospital-claw
.\.venv\Scripts\Activate.ps1

python scripts/run_skill_e2e.py --list
python scripts/run_skill_e2e.py --scenario review_db_local
python scripts/run_skill_e2e.py --allow-live
python scripts/run_skill_e2e.py --allow-live --markdown-out "docs/superpowers/test-results/2026-04-11-local-all-skills-e2e.md"
```

### Bootstrap commands

Preferred Python-core entry:

```powershell
cd c:\Users\roger\Documents\Pyproject\Personal-git\hospital-claw
python scripts/bootstrap_skill_e2e.py --allow-live --scenario review_db_local
python scripts/bootstrap_skill_e2e.py --allow-live --wechat-url "<mp.weixin url>"
```

Windows wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap_skill_e2e.ps1 --allow-live
```

If `.ps1` execution policy blocks direct wrapper startup, use the Python command above instead.

The PowerShell wrapper forwards raw CLI arguments to the Python core, so use the same GNU-style flags as the Python command, for example:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap_skill_e2e.ps1 --allow-live --scenario knowledge_base_rules_live
```

## Bootstrap Behavior

By default, the bootstrap path is **project-level setup**:

- create or reuse `.venv`
- install the known Python package set needed by the harness and local skill flows
- reuse existing `qmd` if already installed
- start or reuse `qmd mcp --http --daemon`
- invoke `scripts/run_skill_e2e.py`

Optional machine-level install mode:

- use `--install-machine-tools` to let the bootstrap attempt qmd installation when `qmd` is missing
- this path is intentionally opt-in
- if machine installation cannot be completed, the bootstrap should stop with a clear message instead of guessing

Useful bootstrap flags:

- `--allow-live`
- `--scenario <id>` (repeatable)
- `--wechat-url <url>`
- `--restart-mcp`
- `--skip-python-install`
- `--install-machine-tools`

## Scenario Matrix

| Scenario ID | Skill | Type | Notes |
|------------|-------|------|------|
| `review_db_local` | `tcm-treatment-review` | Always-on local | Exercises the real `review_db.py` CLI with committed fixtures |
| `tcm_treatment_plan_prereqs` | `tcm-treatment-plan` | Always-on local | Verifies KB prerequisites or documented static fallback assets |
| `sh_yb_policy_monitor_live` | `sh-yb-policy-monitor` | Live-with-skips | Uses `fetch_policies.py` with a harness-owned output dir |
| `knowledge_base_docs_live` | `knowledge-base-update` | Live-with-skips | Runs docs-mode conversion + manifest + `qmd collection add` in a temp workspace |
| `knowledge_base_rules_live` | `knowledge-base-update` | Live-with-skips | Injects a temporary manual rule and verifies manifest + `qmd collection add` |
| `wechat_daily_monitor_manual_url` | `wechat-daily-monitor` | Live-with-skips | Fetches a live WeChat article into a temp workspace and verifies KB side effects |
| `tcm_treatment_review_agent_probe` | `tcm-treatment-review` | Optional probe | Only enabled when external probe driver support is configured |
| `tcm_treatment_plan_agent_probe` | `tcm-treatment-plan` | Optional probe | Only enabled when external probe driver support is configured |
| `wechat_daily_monitor_discovered_probe` | `wechat-daily-monitor` | Optional probe, live-with-skips | Intended for discovered-link validation when local WeChat discovery is available; still requires `--allow-live` |

## Live Dependency Rules

The harness reports:

- `PASS` when the scenario completes and all assertions succeed
- `FAIL` when the scenario ran and the actual behavior did not match expectations
- `SKIP` when a live dependency is missing

Typical skip reasons:

- `qmd` is not installed
- required Python packages are missing
- a live site is unreachable
- `SKILL_E2E_WECHAT_URL` is not configured
- optional probe driver support is not configured

## Optional Environment Variables

| Variable | Purpose |
|---------|---------|
| `SKILL_E2E_WECHAT_URL` | Required for the live manual-URL WeChat scenario |
| `SKILL_E2E_ENABLE_PROBES=1` | Enables probe scenarios in the runner |
| `SKILL_E2E_AGENT_DRIVER` | External command used by optional probe scenarios |
| `SKILL_E2E_WECHAT_DISCOVERY_HINT` | Optional input for discovered-link probe mode |
| `SH_YB_POLICY_SAVE_DIR` | Optional policy-monitor save dir override used by the bootstrap or direct runs |

## Probe Contract

Optional probe scenarios rely on an external driver. The harness provides the prompt and fixture payload, but the external driver is responsible for checking semantic expectations and returning a non-zero exit code when the probe result is unacceptable.

In other words:

- the harness verifies probe execution and records stable payload artifacts
- the external driver verifies prompt-output correctness

## Mapping To The Existing Checklist

### Phase F4 Mapping

From `docs/superpowers/todos/2026-04-10-openclaw-review-and-wechat-daily-monitor.md`:

- `tcm-treatment-review`: covered locally by `review_db_local`; host image-review orchestration still requires separate OpenClaw validation
- `tcm-treatment-plan`: covered locally by `tcm_treatment_plan_prereqs`; full narrative plan generation is covered by the optional agent probe path
- `sh-yb-policy-monitor`: covered locally by `sh_yb_policy_monitor_live`
- `knowledge-base-update`: covered locally by `knowledge_base_docs_live` and `knowledge_base_rules_live`
- `wechat-daily-monitor`: covered locally by `wechat_daily_monitor_manual_url`; discovered-link path is covered by the optional probe scenario

### Phase G Mapping

- `G1 Smoke-test the article pipeline` -> `wechat_daily_monitor_manual_url`
- `G2 Validate priority classification` -> existing unit tests in `tests/test_wechat_article_pipeline.py`
- `G3 Validate KB searchability` -> partial local coverage through manifest + `qmd collection add`; full KB query/search verification remains a live environment follow-up
- `G4 Validate both operator paths` -> manual URL path via `wechat_daily_monitor_manual_url`; discovered-link path via optional probe

## Scope Boundary

This harness intentionally does **not** do the following:

- validate the OpenClaw/mac mini host deployment path
- pretend that missing live dependencies are passing scenarios
- mutate tracked repo content as part of normal local runs

For host validation and final deployment evidence, continue to use the OpenClaw-specific checklist and dated test-results documents.
