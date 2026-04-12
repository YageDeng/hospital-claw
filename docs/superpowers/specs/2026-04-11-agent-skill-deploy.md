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

Local machine samples are also available for each desktop/server target:

- `config/agent_deploy.win.local.json`
- `config/agent_deploy.linux.local.json`
- `config/agent_deploy.macos.local.json`

The config defines:

- repo checkout location
- target skill directory
- template output directory
- optional `deploy_root_dir` for deriving `clone_dir`, `agent_skill_dir`, and `template_output_dir`
- local `repo_url` values may be written as relative paths and are resolved relative to the config file location
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

It now also writes a generated shared-path file for the deployed skills:

- `_shared_runtime/knowledge-base-paths.json`

That file is the shared source of truth for KB-related paths on each target machine, including:

- KB root: `<clone_dir>/docs/knowledge-base`
- source docs: `<clone_dir>/docs/医院材料学习`
- policy mirror: `<clone_dir>/data/sh-yb-policies`

The relative layout is identical on Windows, macOS, and Linux; only the absolute prefix and native path separators differ.

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

`agent-runtime-config.template.json` now includes a `knowledgeBase` object with the resolved per-machine KB paths and the location of `_shared_runtime/knowledge-base-paths.json`, so every deployed skill can read the same path contract instead of hardcoding a single workstation layout.

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

It also creates the KB directory layout inside the repo clone on first deploy:

- `docs/knowledge-base/`
- `docs/knowledge-base/wiki/`
- `docs/knowledge-base/index/`
- `docs/knowledge-base/.staging/`
- `docs/knowledge-base/.staging-binary-md/`
- `docs/knowledge-base/.manual-rules/`
- `docs/knowledge-base/.wiki-ingest-src/`
- `docs/医院材料学习/`
- `data/sh-yb-policies/`

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
