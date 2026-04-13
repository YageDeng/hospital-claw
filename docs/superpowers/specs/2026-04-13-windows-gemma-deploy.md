# Windows Gemma 部署与评估规范

> **分支**: `feature/windows-treatment-app` → `gemma-windows-eval`
> **编写日期**: 2026-04-13
> **维护人**: AI Assistant
> **状态**: 🟡 进行中

## 1. 背景与目标

本任务在 Windows 本地环境上部署 Google Gemma 3 多模态模型（4B 参数版），通过 Ollama 提供 OpenAI-Compatible API 接入 hospital-claw 项目的 skill E2E 评估框架，验证本地模型对诊疗系统的理解能力。

**核心目标：**
- 在 Windows 上通过 Ollama 本地运行 gemma3:4b
- 验证 Gemma 对中医诊疗场景的响应质量
- 产出评估报告，为后续模型选型提供数据支撑

## 2. 环境要求

| 组件    | 最低要求  | 推荐配置      |
|---------|-----------|---------------|
| 操作系统 | Windows 10+ | Windows 11    |
| 内存    | 8 GB      | 16 GB+        |
| 磁盘    | 10 GB 可用 | 20 GB SSD     |
| Ollama  | v0.20+    | 最新版         |
| Python  | 3.12+     | 3.12          |
| Node.js | v22       | v22           |

## 3. 安装步骤

### 3.1 安装 Ollama（Windows）

下载并安装 Ollama for Windows：https://ollama.com/download

或通过命令行安装：
```powershell
winget install Ollama.Ollama
```

### 3.2 下载 Gemma 模型

```powershell
ollama pull gemma3:4b
```

验证模型已就绪：
```powershell
ollama list
```

### 3.3 启动 Ollama 服务

```powershell
# 后台服务（Ollama 默认在 127.0.0.1:11434 监听）
ollama serve

# 验证 API 可用
curl http://127.0.0.1:11434/api/tags
```

## 4. Gemma OpenClaw 集成

### 4.1 OpenClaw 配置

编辑 `~/.openclaw/config.json`，添加 Gemma 模型作为 OpenAI Compatible Provider：

```json
{
  "models": {
    "providers": {
      "gemma-local": {
        "kind": "openai-compatible",
        "baseURL": "http://127.0.0.1:11434/v1",
        "apiKey": "ollama",
        "defaultModel": "gemma3:4b"
      }
    },
    "defaults": {
      "model": "gemma-local/gemma3:4b"
    }
  }
}
```

### 4.2 测试模型

通过 OpenClaw 对话测试：
```
/model gemma-local/gemma3:4b
请解释中医"辨证论治"的基本原则
```

## 5. Skill E2E 评估框架

### 5.1 框架说明

hospital-claw 项目使用 Skill E2E Harness 对 5 个核心技能进行自动化验证：
- `tcm-treatment-review`（治疗单审核）
- `tcm-treatment-plan`（治疗方案生成）
- `sh-yb-policy-monitor`（医保政策监控）
- `knowledge-base-update`（知识库更新）
- `wechat-daily-monitor`（公众号监测）

### 5.2 运行评估

```powershell
# 进入项目目录
cd "E:\QClaw file\hospital-claw"

# 安装依赖
pip install openai httpx

# 运行离线场景（无需 qmd/Ollama）
python scripts/run_skill_e2e.py

# 运行带 Ollama 的评估场景
python scripts/run_gemma_skill_e2e.py --model gemma3:4b --allow-live
```

## 6. Gemma 评估用例

### 6.1 核心评估用例（来自 evals.json）

**评估 1：跨技能协作（医保政策）**
- Prompt：检查上海医保局最近7天有没有和中医收费、医保监管相关的新政策
- 期望：先走 sh-yb-policy-monitor 抓取，再走 knowledge-base-update 入库

**评估 2：公众号文章处理**
- Prompt：抓取一篇公众号文章，按监测规则分类，纳入知识库
- 期望：先走 wechat-daily-monitor，再走 knowledge-base-update docs 模式

**评估 3：治疗方案（知识库回退）**
- Prompt：52岁女性，颈肩痛伴腰痛，制定治疗方案
- 期望：tcm-treatment-plan 只读消费知识库，明确说明数据来源

**评估 4：治疗单审核（知识库回退）**
- Prompt：审核含针法、药物罐加收，腰部推拿的申请单
- 期望：tcm-treatment-review 只读，必要时先刷新知识库

## 7. 已知限制

- **Windows 路径兼容**：`scripts/` 中的路径使用正斜杠，Python 可自动处理
- **Ollama GPU**：Windows 版 Ollama 目前 GPU 支持需要 WSL2 或特定显卡驱动
- **qmd on Windows**：MinerU qmd 在 Windows 上需额外配置 JAVA 环境
- **微信相关**：Windows 环境下微信自动化可能受限

## 8. 时间规划

| 阶段  | 任务                          | 预计时长 |
|-------|-------------------------------|----------|
| Day 1 | 环境搭建 + Ollama + Gemma 下载 | 2-4h     |
| Day 2 | OpenClaw 配置 + Gemma 路由     | 1h       |
| Day 3-4 | 运行 E2E 评估 + 结果分析     | 3-4h     |
| Day 5-6 | 迭代优化 + 报告撰写           | 2-3h     |
| Day 7 | PR Review + 合并               | 1h       |

## 9. 交付物

- `config/agent_deploy.windows.local.json` ✅
- `docs/superpowers/specs/2026-04-13-windows-gemma-deploy.md` ✅
- `scripts/run_gemma_skill_e2e.py`（Gemma E2E Driver）✅
- `docs/superpowers/specs/2026-04-13-windows-gemma-eval-report.md`（评估报告）✅
- 代码提交到 `gemma-windows-eval` 分支
