# Agent Skill Deploy

**Date:** 2026-04-11  
**Status:** Implemented (local-first, from-scratch aware)

## Purpose

This repo now includes a local-first deployment CLI for OpenClaw-like agent systems:

- `scripts/deploy_agent_skills.py`

The first version focuses on **local deployment on the target host**:

- clone or update the repo
- bootstrap machine-level dependencies where practical
- install shared Python dependencies
- install optional WeChat stack dependencies
- start shared services such as `qmd mcp --http --daemon`
- copy the deployable skill bundle into a configured agent skill directory
- generate agent-runtime config templates instead of mutating the live runtime automatically

## Config

Use the checked-in example config as the starting point:

- `config/agent_deploy.example.json`

The config defines:

- repo checkout location
- target skill directory
- template output directory
- `qmd` daemon behavior
- whether machine-level install attempts should be made for Git / Node / qmd (`qmd.install_machine_tools`)
- optional `wechat-router` and `wechat-decrypt` dependency groups
- whether to generate `wechat-decrypt` MCP templates

## Deploy Inventory

The script deploys the current root skill set:

- `skills/tcm-treatment-review/`
- `skills/tcm-treatment-plan/`
- `skills/sh-yb-policy-monitor/`
- `skills/knowledge-base-update/`
- `skills/wechat-daily-monitor/`

It also copies the shared runtime files needed by those skills into `_shared_runtime` under the target skill directory:

- `scripts/review_db.py`
- `scripts/update_kb_manifest.py`
- `scripts/xlsx_to_markdown.py`
- `scripts/binary_docs_to_markdown.py`
- `scripts/wechat_article_pipeline.py`
- `skills/sh-yb-policy-monitor/scripts/fetch_policies.py`

## Commands

### Dry run

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1

python scripts/deploy_agent_skills.py --config config/agent_deploy.example.json --dry-run
```

### Local deploy with overrides

```powershell
python scripts/deploy_agent_skills.py `
  --config config/agent_deploy.example.json `
  --mode local `
  --target-os linux `
  --repo-url "https://github.com/your-org/hospital-claw.git" `
  --clone-dir "/opt/hospital-claw" `
  --skill-dir "/opt/openclaw/skills" `
  --template-output-dir "/opt/openclaw/generated"
```

### Post-deploy verification

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1

python scripts/check_workbuddy_deploy.py --root "C:\Users\roger\.workbuddy"
python scripts/check_workbuddy_deploy.py --root "C:\Users\roger\.workbuddy" --check-qmd --check-wechat-mcp
```

The verification script reports:

- config consistency between `mcp.json`, deploy summary, and generated templates
- deployed skill presence under the target WorkBuddy skill directory
- required shared runtime file presence
- optional live checks for the `qmd` HTTP MCP and `wechat` stdio MCP process startup

## Generated Outputs

The deploy script writes template files under the configured template output directory:

- `agent-runtime-config.template.json`
- `service-commands.sh` or `service-commands.ps1`
- `qmd-mcp.service` on Linux targets
- `qmd-mcp.launchd.plist` on macOS targets
- `deploy-summary.json`

These files are intended for operator review and adaptation. The first version does **not** rewrite the live agent-system config automatically.

The OS-specific startup templates are focused on the shared `qmd` MCP service so host boot/login setup is easier without guessing the agent runtime's internal service manager. `wechat-decrypt` remains a manual/runtime-specific setup step because of GUI, login, and permission requirements.

## Runtime Behavior

The script reuses the shared bootstrap patterns from `scripts/bootstrap_skill_e2e.py` where practical:

- repo `.venv`
- shared Python package installation
- `qmd` detection / install
- `qmd mcp --http --daemon` startup and reuse

For fresh hosts, the deploy path now tries to bootstrap machine tools where practical:

- Git
- Node.js / npm
- `qmd`

Current automation expectations:

- Windows: prefers `winget` for Git and Node, then installs `qmd` with `npm`
- macOS: prefers Homebrew for Node/Git when they are missing
- Linux: prefers `apt-get`, `dnf`, or `yum` when available

The deploy script itself still requires a working Python interpreter in order to run.

Optional dependency groups:

- `wechat-router/requirements.txt`
- `wechat-router/wechat-decrypt/requirements.txt`

Optional WeChat template generation:

- `wechat-router/wechat-decrypt/mcp_server.py`

OS-specific startup helpers:

- Linux: a `systemd` oneshot unit template that starts `qmd mcp --http --daemon` and uses `qmd mcp stop` for shutdown
- macOS: a `launchd` plist template that runs the same `qmd` startup command at load time

## Manual Prerequisites

The script can prepare the deployable files and shared services, but some prerequisites remain manual:

- desktop WeChat login state when using `wechat-decrypt` or `wechat-router`
- Tesseract installation for OCR-based WeChat router flows when no safe installer path is available
- `wechat-decrypt` key extraction and platform-specific permissions
- final agent-runtime config merge / reload on the target host

## Scope Boundary

This first version is **local-first**. SSH-driven remote deployment is intentionally deferred from the verified workflow for now.
