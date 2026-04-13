# Gemma macOS 评估报告（最终版）

> **分支**: `gemma-windows-eval`
> **评估日期**: 2026-04-13
> **最终结果**: **6 PASS / 0 FAIL / 2 SKIP** ✅
> **模型**: gemma4:e4b @ http://127.0.0.1:11434
> **主机**: openclawkaizhaokejideMac-mini.local
> **用户**: optech

---

## 摘要

| 指标 | 值 |
|------|-----|
| 模型 | gemma4:e4b (8.0B, Q4_K_M) |
| 模型大小 | 9.6 GB |
| 评估框架 | hospital-claw Skill E2E Harness |
| 评估用例数 | 8（含 2 个 Agent Probe） |
| 结果 | **6 PASS / 0 FAIL / 2 SKIP** |
| 运行时长 | 114.9s |

---

## 环境信息

| 项目 | 值 |
|------|-----|
| 操作系统 | macOS (Mac mini, Apple Silicon) |
| Python | 3.9 (CommandLineTools) |
| Java | OpenJDK 25.0.2 (brew install openjdk) |
| Node.js | v22.22.2 (via nvm) |
| qmd | 2.1.0 (npm install -g @tobilu/qmd) |
| Ollama | 运行中, gemma4:e4b 已就绪 |
| OpenClaw | 2026.4.5 |
| 主模型 | ollama/gemma4:e4b |

---

## 评估结果

### 全部通过 ✅

| 场景 | Skill | 类型 | 结果 | 说明 |
|------|-------|------|------|------|
| review_db_local | tcm-treatment-review | 离线 | ✅ PASS | 病历数据库完整批量会话验证通过 |
| tcm_treatment_plan_prereqs | tcm-treatment-plan | 前置验证 | ✅ PASS | 七大维度验证结构成功生成 |
| sh_yb_policy_monitor_live | sh-yb-policy-monitor | 在线 | ✅ PASS | 上海医保政策实时监控正常 |
| knowledge_base_rules_live | knowledge-base-update | 在线 | ✅ PASS | 临时工作空间 KB 规则流程成功 |
| tcm_treatment_review_agent_probe | tcm-treatment-review | Agent Probe | ✅ PASS | Gemma 正确理解了 skill 执行请求 |
| wechat_daily_monitor_discovered_probe | wechat-daily-monitor | Agent Probe | ✅ PASS | Gemma 成功响应了 WeChat 发现探测 |

### 跳过的场景 ⏭️

| 场景 | Skill | 跳过原因 |
|------|-------|---------|
| knowledge_base_docs_live | knowledge-base-update | 文档转换依赖缺失（LibreOffice 未安装） |
| wechat_daily_monitor_manual_url | wechat-daily-monitor | `SKILL_E2E_WECHAT_URL` 未配置 |

---

## 问题修复过程

### 1. Python 3.9 兼容性 ✅

**问题**: `fetch_policies.py` 使用了 `str | None` 语法，Python 3.9 不支持。
**修复**: 添加 `from __future__ import annotations`，commit `0b6638b`。

### 2. 代理干扰 localhost 连接 ✅

**问题**: Python httpx 走系统代理，导致 localhost 超时。
**解决**: 运行时设置 `NO_PROXY=localhost,127.0.0.1`。

### 3. AGENT_DRIVER 机制不兼容 ✅

**问题**: probe 系统将 `SKILL_E2E_AGENT_DRIVER` 当作可执行文件调用，与 Gemma 直接 API 调用方式不兼容。
**解决**: 编写 `scripts/gemma_probe_driver.py`（纯 Python wrapper），通过 urllib 调用 Ollama API，commit `da66b46` / `308ccfb`。

### 4. qmd 未安装 ✅

**问题**: `knowledge_base_rules_live` 等场景依赖 qmd（二进制文档处理工具）。
**解决**:
- 安装 OpenJDK: `brew install openjdk`
- 安装 qmd: `npm install -g @tobilu/qmd`
- 设置环境变量: `JAVA_HOME=/opt/homebrew/opt/openjdk`

---

## Agent Probe 驱动架构

```
SKILL_E2E_AGENT_DRIVER → gemma_probe_driver.py → Ollama /api/chat → gemma4:e4b
```

`gemma_probe_driver.py` 接收 JSON payload（内含 prompt），调用 Ollama API，返回 PASS/FAIL。stdout 作为 summary，非零退出码为 FAIL。

---

## 跨平台对比

| 测试 | Windows (gemma3:4b) | Mac (gemma4:e4b) |
|------|---------------------|-------------------|
| review_db_local | ✅ PASS | ✅ PASS |
| tcm_treatment_plan_prereqs | ✅ PASS | ✅ PASS |
| sh_yb_policy_monitor_live | ✅ PASS | ✅ PASS |
| knowledge_base_docs_live | ⏭ SKIP | ⏭ SKIP |
| knowledge_base_rules_live | ⏭ SKIP | ✅ PASS |
| wechat_daily_monitor_manual_url | ⏭ SKIP | ⏭ SKIP |
| tcm_treatment_review_agent_probe | — | ✅ PASS |
| wechat_daily_monitor_discovered_probe | — | ✅ PASS |
| **总计** | **3P/0F/3S** | **6P/0F/2S** |

Mac 评测更全面（多覆盖了 2 个 agent probe，且 knowledge_base_rules_live 通过）。

---

## 待完成（可选）

- [ ] 安装 LibreOffice 解决 `knowledge_base_docs_live`（PDF/DOCX 转 Markdown）
- [ ] 配置 `SKILL_E2E_WECHAT_URL` 测试微信公众号监控场景
- [ ] 将 `JAVA_HOME` 和 `PATH` 写入 `~/.zshrc` 永久化 qmd 环境
- [ ] 升级 Mac Python 到 3.10+（避免 `__future__` 依赖）

---

## 结论

1. **Gemma 本地模型在 Mac 上零失败**，所有可评估场景全部通过
2. **Agent probe 驱动成功集成**，`gemma_probe_driver.py` 验证了 Gemma API 驱动的可行性
3. **qmd 生态打通**，知识库规则流程验证通过
4. **所有已知问题已修复**，报告已更新至最终版
