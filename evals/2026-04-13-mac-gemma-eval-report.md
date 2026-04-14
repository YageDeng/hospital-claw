# Mac Gemma Local Evaluation Report

**Date:** 2026-04-14 (final update)
**Model:** gemma4:e4b via Ollama (local, localhost:11434)
**Branch:** gemma-windows-eval
**Commit:** 45ccc95

## Final Results

| Scenario | Status | Notes |
|---|---|---|
| review_db_local | ✅ PASS | review_db CLI completed full batch session |
| tcm_treatment_plan_prereqs | ✅ PASS | Composite treatment-plan validation passed |
| sh_yb_policy_monitor_live | ✅ PASS | Policy monitor script against live site |
| knowledge_base_docs_live | ✅ PASS | KB docs flow in temporary workspace |
| knowledge_base_rules_live | ✅ PASS | KB rules flow in temporary workspace |
| tcm_treatment_review_agent_probe | ✅ PASS | Agent probe via gemma_probe_driver.py |
| wechat_daily_monitor_discovered_probe | ✅ PASS | Agent probe via gemma_probe_driver.py |
| wechat_daily_monitor_manual_url | ⏭ SKIP | SKILL_E2E_WECHAT_URL not configured |

**Summary: PASS=7 / FAIL=0 / SKIP=1 / TOTAL=8**

## Key Fixes Applied

- `skills/sh-yb-policy-monitor/scripts/fetch_policies.py`: Added `from __future__ import annotations` for Python 3.9 compat
- `scripts/gemma_probe_driver.py`: Corrected indentation (was 1-space/2-space mixed, fixed to standard 4-space)
- Python 3.9 requires `from __future__ import annotations` for union type syntax (`str | None`)
- httpx/proxy issue: must set `NO_PROXY=localhost,127.0.0.1` to reach localhost Ollama
- Ollama must be running (`ollama serve`) before running agent probes

## Runtime Environment

```bash
export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"
export JAVA_HOME="/opt/homebrew/opt/openjdk"
NO_PROXY=localhost,127.0.0.1 \
SKILL_E2E_ENABLE_PROBES=1 \
SKILL_E2E_AGENT_DRIVER="python3 scripts/gemma_probe_driver.py" \
python3 scripts/run_gemma_skill_e2e.py --model gemma4:e4b --allow-live
```

## Hardware

- Mac mini: optech / openclawkaizhaokejideMac-mini.local
- RAM: Shared (M-series chip)
