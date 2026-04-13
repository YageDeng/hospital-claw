# Gemma macOS 评估报告

> **分支**: `gemma-windows-eval`
> **评估日期**: 2026-04-13
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
| 运行命令 | `NO_PROXY=localhost,127.0.0.1 SKILL_E2E_ENABLE_PROBES=1 python3 scripts/run_gemma_skill_e2e.py --model gemma4:e4b --allow-live` |
| 结果 | **2 PASS / 0 FAIL / 6 SKIP** |

---

## 环境信息

| 项目 | 值 |
|------|-----|
| 操作系统 | macOS (Mac mini) |
| Python | 3.9 (CommandLineTools 自带) |
| Ollama | 运行中, gemma4:e4b 已就绪 |
| OpenClaw | 2026.4.5, 配置文件 ~/.openclaw/openclaw.json |
| 主模型 | ollama/gemma4:e4b (主), kimi/kimi-code (兜底) |

---

## 评估结果

### 通过的场景

| 场景 | Skill | 类型 | 说明 |
|------|-------|------|------|
| review_db_local | tcm-treatment-review | 离线 | 病历数据库完整批量会话验证通过 |
| sh_yb_policy_monitor_live | sh-yb-policy-monitor | 在线 | 上海医保政策实时监控正常，三个栏目均无新发布内容 |

### 跳过的场景

| 场景 | Skill | 跳过原因 |
|------|-------|---------|
| tcm_treatment_plan_prereqs | tcm-treatment-plan | SKILL_E2E_AGENT_DRIVER 未配置 |
| knowledge_base_docs_live | knowledge-base-update | qmd 未安装 |
| knowledge_base_rules_live | knowledge-base-update | qmd 未安装 |
| wechat_daily_monitor_manual_url | wechat-daily-monitor | SKILL_E2E_WECHAT_URL 未配置 |
| tcm_treatment_review_agent_probe | tcm-treatment-review | SKILL_E2E_AGENT_DRIVER 未配置 |
| wechat_daily_monitor_discovered_probe | wechat-daily-monitor | SKILL_E2E_AGENT_DRIVER 未配置 |

---

## 发现的问题

### 1. Python 3.9 兼容性 ❌→✅ 已修复

**问题**: `fetch_policies.py` 使用了 `str | None` 语法，Python 3.9 不支持（需 3.10+）。

```
TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'
```

**修复**: 在文件头部添加 `from __future__ import annotations`，已提交 commit `0b6638b`。

### 2. 代理干扰 localhost 连接 ❌→✅ 已解决

**问题**: Mac 上 Python httpx 走系统代理，导致 localhost 请求超时。

```
httpx.ReadTimeout: timed out
```

**解决**: 运行时设置 `NO_PROXY=localhost,127.0.0.1`。

### 3. urllib3 SSL 警告 ⚠️ 不影响功能

```
NotOpenSSLWarning: urllib3 v2 only supports OpenSSL 1.1.1+, currently the 'ssl' module is compiled with 'LibreSSL 2.8.3'
```

Mac 自带 Python 3.9 的 LibreSSL 版本过低，不影响功能但建议后续升级 Python 版本。

---

## OpenClaw 配置发现

Mac 上的 OpenClaw 配置（`/Users/optech/.openclaw/openclaw.json`）：

```json
{
  "agents": {
    "defaults": {
      "model": {
        "primary": "ollama/gemma4:e4b",
        "fallbacks": ["kimi/kimi-code"]
      }
    }
  },
  "models": {
    "providers": {
      "ollama": {
        "baseUrl": "http://127.0.0.1:11434",
        "api": "ollama",
        "models": [
          { "id": "gemma4:e4b", "contextWindow": 131072, "maxTokens": 8192 },
          { "id": "glm-4.7-flash", "contextWindow": 128000, "maxTokens": 8192 }
        ]
      },
      "kimi": {
        "baseUrl": "https://api.kimi.com/coding/",
        "api": "anthropic-messages",
        "models": [
          { "id": "kimi-code", "contextWindow": 262144, "maxTokens": 32768 }
        ]
      }
    }
  }
}
```

**关键发现：**
- 主模型已配置为 `ollama/gemma4:e4b`
- 兜底模型为云端 `kimi/kimi-code`
- Ollama 端点为 `http://127.0.0.1:11434`
- Gateway 服务未安装（需在 Mac 图形界面下运行 `sudo openclaw gateway install`）

---

## 跨平台对比（Windows vs Mac）

| 测试 | Windows (gemma3:4b) | Mac (gemma4:e4b) |
|------|---------------------|-------------------|
| review_db_local | ✅ PASS | ✅ PASS |
| tcm_treatment_plan_prereqs | ✅ PASS | ⏭ SKIP |
| sh_yb_policy_monitor_live | ✅ PASS | ✅ PASS |
| knowledge_base_docs_live | ⏭ SKIP | ⏭ SKIP |
| knowledge_base_rules_live | ⏭ SKIP | ⏭ SKIP |
| wechat_daily_monitor_manual_url | ⏭ SKIP | ⏭ SKIP |
| **总计** | **3P/0F/3S** | **2P/0F/6S** |

**差异原因**：
- Mac 启用了 `SKILL_E2E_ENABLE_PROBES=1`，多出 2 个 probe 场景（均因 AGENT_DRIVER 未配置而 SKIP）
- Mac 的 `tcm_treatment_plan_prereqs` 因 AGENT_DRIVER 未配置而 SKIP，Windows 未启用 probes 所以只跑前置检查就 PASS

---

## 结论

1. **Gemma 本地模型在 Mac 上可正常运行**，Ollama + gemma4:e4b 连通性已验证
2. **核心 skill（病历审核、医保监控）在 Mac + Gemma 下零失败**
3. **Python 3.9 兼容性问题已修复**并推送到 GitHub
4. **代理环境需注意**：Mac 上运行时必须设置 `NO_PROXY=localhost,127.0.0.1`
5. **待完成**：安装 qmd 插件后可补测知识库场景；配置 AGENT_DRIVER 后可测试语义 probe

---

## 待办事项

- [ ] 在 Mac 图形界面下安装 OpenClaw Gateway 服务
- [ ] 安装 qmd 插件以运行知识库场景
- [ ] 配置 SKILL_E2E_AGENT_DRIVER 以测试语义级 probe
- [ ] 升级 Mac Python 到 3.10+ 以避免兼容性问题
