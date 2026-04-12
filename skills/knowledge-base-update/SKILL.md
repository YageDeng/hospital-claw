---
name: knowledge-base-update
version: v2
description: 当用户要求刷新共享知识库、把新文档/新政策/新规则/公众号监测内容纳入知识库，或重建检索层与 wiki 时使用。它是共享知识库的标准更新入口。
---

# 知识库更新（v2 — qmd 1.0.5 兼容）

**重要：所有输出必须全部使用中文。**

## 概述

本技能管理 `<KB_ROOT>/` 知识库的更新，支持三种数据来源：

| 模式 | 触发语 | 说明 |
|------|--------|------|
| **docs** | "更新知识库" / "添加新文档到知识库" / "同步公众号监测文章到知识库" / "刷新公众号每日监测知识库" | 扫描 `<KB_SOURCE_ROOT>/` 中的新文档与原生 Markdown（包括 `<KB_SOURCE_ROOT>/公众号每日监测/`），转换后更新检索集合 |
| **policy** | "获取最新政策并更新知识库" | 调用 `sh-yb-policy-monitor` 获取新政策，然后执行 docs 流程 |
| **rules** | "添加新规则到知识库" | 接收用户手动输入的规则内容，保存并索引 |

## 已知 CLI 差异

当前仓库按 `qmd 1.0.5` 的实际行为工作，执行时必须遵守以下规则：

1. `qmd` **没有** `index` 子命令，不能使用 `qmd index`
2. 二进制文档（PDF/DOCX/PPTX）在本机环境下不能稳定直接索引，必须先转成 Markdown
3. `qmd wiki ingest` 不是“自动全量重建 wiki”，它是**按单个 source 文档**执行分析；要真正写出页面，还需要 `qmd wiki write`
4. `qmd query` 首次运行可能触发模型下载；如长时间停留在 `Gathering information`，优先退回 `qmd search` / MCP `search` / `wiki_read`

## 前置条件

1. MinerU Document Explorer 已安装（`qmd --version` 可用）
2. MCP 服务已启动（`qmd mcp --http --daemon`）
3. Python 环境已安装：
   - `openpyxl`（XLSX 转换）
   - `pymupdf`、`python-docx`、`python-pptx`（二进制文档转 Markdown）

## 共享知识库路径

优先读取 `_shared_runtime/knowledge-base-paths.json`：

- `<KB_ROOT>` = `knowledgeBase.rootDir`
- `<KB_SOURCE_ROOT>` = `knowledgeBase.sourceDocsDir`
- `<KB_POLICY_ROOT>` = `knowledgeBase.policySaveDir`

共享文件缺失时回退到：

- `<KB_ROOT>` = `docs/knowledge-base`
- `<KB_SOURCE_ROOT>` = `docs/医院材料学习`
- `<KB_POLICY_ROOT>` = `data/sh-yb-policies`

## 跨技能协作约定

- 本技能是共享知识库的唯一完整更新入口；涉及集合刷新、manifest、wiki 重写时以本技能为准。
- `sh-yb-policy-monitor` 负责抓取政策文件；抓取完成后由本技能接管入库。
- `wechat-daily-monitor` 负责抓取公众号文章；如需统一刷新检索层、manifest 或 wiki，由本技能接管。
- `tcm-treatment-plan` 与 `tcm-treatment-review` 只读知识库，不直接修改集合、manifest 或源目录结构。

## 执行流程

### 第一步：确定更新模式

询问用户或从上下文判断使用哪种模式（docs / policy / rules）。

补充约定：

- `公众号每日监测` 产物如果已经落在 `<KB_SOURCE_ROOT>/公众号每日监测/`，默认复用 `docs` 模式，不新增独立 `wechat` 模式
- 当 `wechat-daily-monitor` 技能刚保存完文章 Markdown 后，应立即执行本技能的 `docs` 最小刷新流程，至少刷新 `source_md` 与 manifest

### 第二步：按模式执行数据获取

#### 模式一：docs（文档扫描）

1. 列出 `<KB_SOURCE_ROOT>/` 中所有文件
2. 运行转换脚本，生成仓库内可索引的 Markdown 输入：

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/xlsx_to_markdown.py --input "<KB_SOURCE_ROOT>" --output "<KB_ROOT>/.staging"
python scripts/binary_docs_to_markdown.py --input "<KB_SOURCE_ROOT>" --output "<KB_ROOT>/.staging-binary-md"
```

3. 如果 `<KB_SOURCE_ROOT>/` 中存在原生 Markdown 文件，也将其纳入 `source_md` 刷新范围；这包括 `<KB_SOURCE_ROOT>/公众号每日监测/` 下新抓取的文章 Markdown
4. 继续到第三步

#### 模式二：policy（政策获取）

1. 运行 `sh-yb-policy-monitor` 技能的获取脚本：

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python skills/sh-yb-policy-monitor/scripts/fetch_policies.py --days 7
```

2. 将新获取的政策文件从 `SH_YB_POLICY_SAVE_DIR` 指定目录，或默认 `<KB_POLICY_ROOT>/`，复制到 `<KB_SOURCE_ROOT>/`
3. 再按 docs 模式继续执行转换与集合刷新

#### 模式三：rules（手动规则）

1. 请用户提供规则内容（文字描述或结构化数据）
2. 将内容保存为 Markdown 文件到 `<KB_ROOT>/.manual-rules/`
3. 文件命名格式：`{YYYY-MM-DD}_{规则主题简称}.md`
4. 文件格式：

```markdown
# {规则标题}

- **添加日期**：{YYYY-MM-DD}
- **来源**：手动添加
- **类别**：{对应的 wiki 分类}

---

{规则内容}
```

5. 继续到第三步

### 第三步：刷新检索集合

不要使用 `qmd index`。改为刷新以下 Markdown 集合：

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1

qmd collection remove source_md 2>$null
qmd collection remove yycailiao_md 2>$null
qmd collection remove xlsxmd 2>$null
qmd collection remove manual_rules 2>$null

qmd collection add "<KB_SOURCE_ROOT>" --name source_md --mask "**/*.md"
qmd collection add "<KB_ROOT>/.staging-binary-md" --name yycailiao_md --mask "**/*.md"
qmd collection add "<KB_ROOT>/.staging" --name xlsxmd --mask "**/*.md"
qmd collection add "<KB_ROOT>/.manual-rules" --name manual_rules --mask "**/*.md"
```

说明：
- `source_md`：源目录里本来就是 Markdown 的文件（例如政策抓取结果、`公众号每日监测` 抓取结果）
- `yycailiao_md`：由 PDF/DOCX/PPTX 转换得到的 Markdown
- `xlsxmd`：由 XLSX 转换得到的 Markdown
- `manual_rules`：手动新增规则

### 第四步：按需更新 Wiki

默认目标是**确保知识库可搜索**。如果用户没有明确要求“重建 wiki 页面”，可跳过全量 wiki 重写。

如果用户明确要求刷新 wiki，使用当前 CLI 兼容流程：

1. 确保 `.wiki-ingest-src/` 已存在并包含 `src-*.md`
2. 把该目录加入 collection
3. 对单个 source 执行 `qmd wiki ingest`
4. 再用 `qmd wiki write` 把页面写回 `<KB_ROOT>/wiki/`

注意：
- 不要声称 `qmd wiki ingest` 单独执行后 wiki 已完成更新
- 如果当前仓库里的 `<KB_ROOT>/wiki/` 已存在且本次只是刷新检索集合，可在输出中明确说明“检索层已更新，wiki 页面沿用现有版本”

### 第五步：更新清单文件

使用辅助脚本更新 `<KB_ROOT>/.manifest.json`：

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/update_kb_manifest.py
```

该清单用于记录当前仓库内知识库输入文件的哈希，便于后续判断哪些文件发生了变化。

### 第六步：输出报告

向用户汇报更新结果：

```
## 知识库更新报告

- **更新模式**：{docs/policy/rules}
- **刷新集合**：source_md / yycailiao_md / xlsxmd / manual_rules
- **新增或变更文件**：{N} 个
- **Manifest**：已更新 / 跳过
- **Wiki**：已重建 / 沿用现有页面 / 未执行
- **错误**：{如有}

### 关键说明
- 当前环境使用 `qmd collection add`，不使用 `qmd index`
- 如 `qmd query` 首次模型下载未完成，本次验证可退回 `qmd search`
```

## 知识库目录结构

```
<KB_ROOT>/
├── wiki/                          # Wiki 页面
├── index/                         # 现有索引辅助文件
├── .staging/                      # XLSX -> MD 暂存
├── .staging-binary-md/            # PDF/DOCX/PPTX -> MD 暂存
├── .manual-rules/                 # 手动添加的规则
├── .wiki-ingest-src/              # wiki ingest 输入源
├── .manifest.json                 # KB 输入文件清单
└── wiki-seed.yml                  # Wiki taxonomy seed
```

