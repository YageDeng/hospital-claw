# Gemma 本地评估 — 跨平台总结报告

> **项目**: hospital-claw Gemma 本地模型能力评估
> **日期**: 2026-04-13
> **分支**: `gemma-windows-eval`
> **评估人**: YageDeng

---

## 一、项目目标

在本地部署 Gemma 多模态模型，验证仓库内各 skill 的端到端（E2E）执行能力，产出可复现的评估证据。

---

## 二、评估环境

| 项目 | Windows | macOS |
|------|---------|-------|
| 主机 | AMD Ryzen 7 8845HS / 32GB RAM | Mac mini (Apple Silicon) |
| 操作系统 | Windows 11 家庭中文版 | macOS |
| Python | 3.12+ | 3.9 (CommandLineTools) |
| Ollama | ✅ 运行中 | ✅ 运行中 |
| 模型 | gemma3:4b (3.3GB, Q4_K_M) | gemma4:e4b (9.6GB, Q4_K_M) |
| OpenClaw | 未配置 | 2026.4.5 (已配置 ollama/gemma4:e4b) |
| Gateway 服务 | — | ❌ 未安装（需 Mac 图形界面） |

---

## 三、评估结果汇总

| # | 场景 | Skill | 类型 | Windows | Mac |
|---|------|-------|------|---------|-----|
| 1 | review_db_local | tcm-treatment-review | 离线 | ✅ PASS | ✅ PASS |
| 2 | tcm_treatment_plan_prereqs | tcm-treatment-plan | 前置 | ✅ PASS | ✅ PASS |
| 3 | sh_yb_policy_monitor_live | sh-yb-policy-monitor | 在线 | ✅ PASS | ✅ PASS |
| 4 | knowledge_base_docs_live | knowledge-base-update | 在线 | ⏭ SKIP | ⏭ SKIP |
| 5 | knowledge_base_rules_live | knowledge-base-update | 在线 | ⏭ SKIP | ✅ PASS |
| 6 | wechat_daily_monitor_manual_url | wechat-daily-monitor | 在线 | ⏭ SKIP | ⏭ SKIP |
| 7 | tcm_treatment_review_agent_probe | tcm-treatment-review | Probe | — | ✅ PASS |
| 8 | wechat_daily_monitor_discovered_probe | wechat-daily-monitor | Probe | — | ✅ PASS |

> ¹ Mac 启用了 `SKILL_E2E_ENABLE_PROBES=1`，`gemma_probe_driver.py` 已集成

### 总成绩

| 平台 | PASS | FAIL | SKIP | 总计 |
|------|------|------|------|------|
| Windows (gemma3:4b) | 3 | 0 | 3 | 6 |
| Mac (gemma4:e4b) | 6 | 0 | 2 | 8 |

**两个平台均零失败。** Mac 剩余 2 个 SKIP（LibreOffice 缺失、WECHAT_URL 未配置），非模型能力问题。

---

## 四、跨平台发现的问题与修复

| # | 问题 | 影响 | 修复 | Commit |
|---|------|------|------|--------|
| 1 | `run_gemma_skill_e2e.py` import 路径缺失 | 脚本无法运行 | 添加 scripts/ 到 sys.path | `aec876f` |
| 2 | `fetch_policies.py` 使用 `str \| None` | Python 3.9 报错 | 添加 `from __future__ import annotations` | `0b6638b` |
| 3 | Mac 代理干扰 localhost | httpx 连 Ollama 超时 | 运行时设 `NO_PROXY=localhost,127.0.0.1` | 运行时配置 |
| 4 | Mac urllib3 SSL 警告 | 仅警告，不影响功能 | 建议 Python 升级到 3.10+ | 待处理 |

---

## 五、OpenClaw 配置状态

### Mac 配置（已探明）

- **配置文件**: `/Users/optech/.openclaw/openclaw.json`
- **主模型**: `ollama/gemma4:e4b` ✅ 已指向本地
- **兜底模型**: `kimi/kimi-code`（云端）
- **Ollama 端点**: `http://127.0.0.1:11434`
- **Gateway 服务**: ✅ 运行中 (pid 687, port 18789, loopback)
- **Dashboard**: http://127.0.0.1:18789/

### Windows 配置

- **Ollama 端点**: `http://127.0.0.1:11434`
- **OpenClaw**: 未配置（非评估目标主机）

---

## 六、计划完成度

| 计划任务 | 状态 | 说明 |
|----------|------|------|
| discover-openclaw-config | ✅ 完成 | Mac 配置已探明，主模型已指向 ollama/gemma4:e4b |
| plan-gemma-macos-serve | ✅ 完成 | Windows + Mac 均已部署 Ollama + Gemma |
| plan-openclaw-redirect | ✅ 完成 | Mac 已配置本地 Gemma 为主模型，Gateway 已运行 |
| plan-gemma-e2e-driver | ✅ 完成 | run_gemma_skill_e2e.py 已编写并修复 |
| plan-scenario-and-test-coverage | ✅ 完成 | 6P/0F/2S，gemma_probe_driver.py 已集成 probe 场景 |
| plan-final-reporting | ✅ 完成 | Windows 报告 + Mac 报告（最终版）+ 跨平台总结 |

**完成度：约 99%**

---

## 七、待办事项

### 必须在 Mac 图形界面操作

- [x] 安装 OpenClaw Gateway 服务 ✅ 已在 Mac Terminal.app 中安装成功
- [x] 验证 Gateway 运行状态 ✅ running (pid 687, port 18789)

### 代码集成 ✅ 全部完成

- [x] AGENT_DRIVER 机制 ✅ `gemma_probe_driver.py` 已编写并验证（commit `308ccfb`）
- [x] qmd 插件 ✅ `npm install -g @tobilu/qmd`，OpenJDK 25 已装，`knowledge_base_rules_live` 通过

### 可选优化

- [ ] 安装 LibreOffice 解决 `knowledge_base_docs_live`（PDF/DOCX 转 Markdown）
- [ ] 配置 `SKILL_E2E_WECHAT_URL` 测试微信公众号监控场景
- [ ] 将 `JAVA_HOME=/opt/homebrew/opt/openjdk` 写入 `~/.zshrc` 永久化 qmd 环境
- [ ] 升级 Mac Python 到 3.10+（避免 `__future__` 依赖）

---

## 八、结论

1. **Gemma 本地模型在 Windows 和 Mac 上均可正常运行**，Ollama 部署方案可行
2. **核心 skill（病历审核、医保监控）跨平台零失败**
3. **Mac 的 OpenClaw 已预配置本地 Gemma**，仅需安装 Gateway 服务即可完成重定向
4. **跨平台兼容性问题已修复并推送到 GitHub**
5. **评估框架可复用**，安装缺失依赖后即可扩展覆盖更多场景

---

## 九、交付物清单

| 文件 | 说明 |
|------|------|
| `scripts/run_gemma_skill_e2e.py` | Gemma E2E 驱动脚本（含 import 修复） |
| `skills/sh-yb-policy-monitor/scripts/fetch_policies.py` | Python 3.9 兼容修复 |
| `docs/superpowers/specs/2026-04-13-windows-gemma-eval-report.md` | Windows 评估报告 |
| `docs/superpowers/specs/2026-04-13-mac-gemma-eval-report.md` | Mac 评估报告 |
| `docs/superpowers/specs/2026-04-13-cross-platform-summary.md` | 本跨平台总结报告 |
