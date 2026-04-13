# Gemma Windows 评估报告

> **分支**: `gemma-windows-eval`
> **评估日期**: 2026-04-13
> **模型**: gemma3:4b @ http://127.0.0.1:11434
> **状态**: 🔄 待运行

---

## 摘要

| 指标 | 值 |
|------|-----|
| 模型 | gemma3:4b |
| 评估框架 | hospital-claw Skill E2E Harness |
| 评估用例数 | 6 |
| 运行命令 | `python scripts/run_gemma_skill_e2e.py --allow-live` |

---

## 评估用例

### 用例 1：tcm_treatment_plan_prereqs
- **技能**: tcm-treatment-plan
- **类型**: 前置条件检查
- **通过标准**: qmd 可用或静态回退资产存在
- **状态**: 🔄 待运行

### 用例 2：sh_yb_policy_monitor_live
- **技能**: sh-yb-policy-monitor
- **类型**: 在线/实时
- **通过标准**: 成功抓取医保政策页面，保存 Markdown 文件
- **状态**: 🔄 待运行

### 用例 3：knowledge_base_docs_live
- **技能**: knowledge-base-update
- **类型**: 在线/实时
- **通过标准**: qmd 集合创建成功，manifest 包含注入的文档
- **状态**: 🔄 待运行

### 用例 4：knowledge_base_rules_live
- **技能**: knowledge-base-update
- **类型**: 在线/实时
- **通过标准**: manual-rules 集合创建成功
- **状态**: 🔄 待运行

### 用例 5：wechat_daily_monitor_manual_url
- **技能**: wechat-daily-monitor
- **类型**: 在线/实时
- **通过标准**: 微信公众号文章抓取成功，KB manifest 刷新成功
- **状态**: 🔄 待运行

### 用例 6：tcm_treatment_review_agent_probe
- **技能**: tcm-treatment-review
- **类型**: Agent Probe（可选）
- **通过标准**: Gemma 产生包含"合格"、"不合格"、"七大维度"关键词的响应
- **状态**: 🔄 待运行

---

## 运行结果

（模型下载完成后运行以下命令填充本节）

```powershell
cd "E:\QClaw file\hospital-claw"
python scripts/run_gemma_skill_e2e.py --allow-live --json-out data/skill_e2e/gemma-eval-results.json
```

---

## 结论

（待评估完成后填写）
