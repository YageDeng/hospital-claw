# Knowledge Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Process 26 TCM training documents with MinerU Document Explorer, build an interlinked wiki knowledge base, configure MCP for agent runtime queries, and refactor 3 existing skills to use the KB as single source of truth.

**Architecture:** Three-source ingestion (manual docs, online policy fetch, manual rules) → MinerU Document Explorer (indexing + wiki + hybrid search) → `docs/knowledge-base/` (wiki pages + search index) → MCP server + versioned skills (v2 = KB-powered, v1 = archived originals).

**Tech Stack:** MinerU Document Explorer (Node.js >= 22), Python 3.10+ (pymupdf, python-docx, python-pptx, openpyxl), MCP protocol (HTTP daemon on port 8181)

**Spec:** `docs/superpowers/specs/2026-04-07-knowledge-base-design.md`

---

> **2026-04-09 compatibility update:** On this machine, `qmd 1.0.5` does **not** provide `qmd index`. Follow the compatibility flow from `docs/superpowers/issue-log/2026-04-09-qmd-index-unknown-command.md`: convert binary docs to Markdown, use `qmd collection add --mask "**/*.md"` for searchable inputs, and treat wiki refresh as a collection-relative `qmd wiki ingest` + `qmd wiki write` flow rather than bare `qmd wiki ingest`.

## File Structure

### New files to create

| File | Responsibility |
|------|---------------|
| `scripts/xlsx_to_markdown.py` | Convert XLSX files to markdown tables for MinerU ingestion |
| `docs/knowledge-base/.staging/` | Directory for converted XLSX → MD files |
| `docs/knowledge-base/.manual-rules/` | Directory for manually authored rule files |
| `docs/knowledge-base/wiki/` | MinerU-generated interlinked wiki pages |
| `docs/knowledge-base/index/` | MinerU search index |
| `.cursor/mcp.json` | MinerU MCP server configuration |
| `skills/knowledge-base-update/v1/SKILL.md` | Archived original KB update skill |
| `skills/knowledge-base-update/v2/SKILL.md` | qmd 1.0.5-compatible KB update skill |
| `skills/knowledge-base-update/SKILL.md` | Copy of latest version |
| `skills/tcm-treatment-plan/v1/SKILL.md` | Archived original |
| `skills/tcm-treatment-plan/v1/方案参考.md` | Archived original |
| `skills/tcm-treatment-plan/v2/SKILL.md` | KB-powered refactor |
| `skills/tcm-treatment-plan/v2/方案参考.md` | Kept as-is (skill-specific) |
| `skills/tcm-treatment-review/v1/SKILL.md` | Archived original |
| `skills/tcm-treatment-review/v1/standards.md` | Archived original |
| `skills/tcm-treatment-review/v1/examples.md` | Archived original |
| `skills/tcm-treatment-review/v2/SKILL.md` | KB-powered refactor |
| `skills/tcm-treatment-review/v2/examples.md` | Kept as-is (skill-specific) |
| `skills/sh-yb-policy-monitor/v1/SKILL.md` | Archived original |
| `skills/sh-yb-policy-monitor/v1/scripts/fetch_policies.py` | Archived original |
| `skills/sh-yb-policy-monitor/v2/SKILL.md` | Enhanced with KB trigger |
| `skills/sh-yb-policy-monitor/v2/scripts/fetch_policies.py` | Enhanced with KB trigger |

---

## Task 1: Install Node.js

MinerU Document Explorer requires Node.js >= 22. It is **not currently installed** on this machine.

**Files:** None (system-level install)

- [ ] **Step 1: Download and install Node.js**

Go to https://nodejs.org/ and download the Windows installer for Node.js LTS (v22+). Run the installer with default settings.

Alternatively, use winget:

```powershell
winget install OpenJS.NodeJS.LTS
```

- [ ] **Step 2: Verify Node.js installation**

Close and reopen the terminal, then run:

```powershell
node --version
```

Expected: `v22.x.x` or higher

```powershell
npm --version
```

Expected: `10.x.x` or higher

- [ ] **Step 3: Commit**

No files to commit — system-level install.

---

## Task 2: Install MinerU Document Explorer

**Files:** None (global npm package)

- [ ] **Step 1: Install MinerU Document Explorer globally**

```powershell
npm install -g mineru-document-explorer
```

- [ ] **Step 2: Verify installation**

```powershell
qmd --version
```

Expected: version number printed (e.g., `1.x.x`)

- [ ] **Step 3: Install Python dependencies for document processing**

Activate the project venv first, then install:

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
.\.venv\Scripts\Activate.ps1
pip install pymupdf python-docx python-pptx openpyxl
```

- [ ] **Step 4: Verify Python dependencies**

```powershell
python -c "import pymupdf; import docx; import pptx; import openpyxl; print('All dependencies OK')"
```

Expected: `All dependencies OK`

- [ ] **Step 5: Commit**

No files to commit — dependency installs.

---

## Task 3: Create XLSX-to-Markdown Conversion Script

The 3 XLSX files in `docs/医院材料学习/` are not natively supported by MinerU. This script converts each sheet to a markdown table.

**Files:**
- Create: `scripts/xlsx_to_markdown.py`

- [ ] **Step 1: Create the scripts directory and conversion script**

Create `scripts/xlsx_to_markdown.py`:

```python
"""Convert XLSX files to Markdown tables for MinerU ingestion.

Usage:
    python scripts/xlsx_to_markdown.py
    python scripts/xlsx_to_markdown.py --input "docs/医院材料学习" --output "docs/knowledge-base/.staging"
"""

import argparse
import hashlib
import json
from pathlib import Path

from openpyxl import load_workbook


def sheet_to_markdown(ws) -> str:
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return ""

    headers = [str(cell) if cell is not None else "" for cell in rows[0]]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows[1:]:
        cells = [str(cell) if cell is not None else "" for cell in row]
        if all(c == "" for c in cells):
            continue
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)


def convert_xlsx(xlsx_path: Path, output_dir: Path) -> list[Path]:
    wb = load_workbook(xlsx_path, data_only=True)
    created = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        md_table = sheet_to_markdown(ws)
        if not md_table:
            continue

        safe_name = xlsx_path.stem
        if len(wb.sheetnames) > 1:
            safe_name += f"_{sheet_name}"

        output_path = output_dir / f"{safe_name}.md"
        content = (
            f"# {xlsx_path.stem}\n\n"
            f"**Sheet:** {sheet_name}\n\n"
            f"**Source:** `{xlsx_path.name}`\n\n"
            f"{md_table}\n"
        )
        output_path.write_text(content, encoding="utf-8")
        created.append(output_path)
        print(f"  Converted: {xlsx_path.name} / {sheet_name} -> {output_path.name}")

    return created


def main():
    parser = argparse.ArgumentParser(description="Convert XLSX to Markdown for MinerU")
    parser.add_argument(
        "--input",
        default=r"docs\医院材料学习",
        help="Directory containing XLSX files",
    )
    parser.add_argument(
        "--output",
        default=r"docs\knowledge-base\.staging",
        help="Output directory for markdown files",
    )
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    xlsx_files = list(input_dir.glob("*.xlsx"))
    if not xlsx_files:
        print(f"No XLSX files found in {input_dir}")
        return

    print(f"Found {len(xlsx_files)} XLSX file(s) in {input_dir}")
    print(f"Output directory: {output_dir}\n")

    all_created = []
    for xlsx_path in xlsx_files:
        print(f"Processing: {xlsx_path.name}")
        created = convert_xlsx(xlsx_path, output_dir)
        all_created.extend(created)

    print(f"\nDone. Created {len(all_created)} markdown file(s).")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the conversion script**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
.\.venv\Scripts\Activate.ps1
python scripts/xlsx_to_markdown.py
```

Expected output: 3 XLSX files converted, markdown files appear in `docs/knowledge-base/.staging/`

- [ ] **Step 3: Verify the output**

```powershell
Get-ChildItem "docs\knowledge-base\.staging" | Format-Table Name, Length
```

Expected: Multiple `.md` files (one per sheet in each XLSX)

- [ ] **Step 4: Spot-check one converted file**

Open one of the generated `.md` files and verify that:
- Headers match the original XLSX column names
- Data rows are complete
- Chinese characters display correctly

- [ ] **Step 5: Commit**

```powershell
git add scripts/xlsx_to_markdown.py docs/knowledge-base/.staging/
git commit -m "feat: add XLSX-to-markdown conversion script and initial staging files"
```

---

## Task 4: Index All Documents with MinerU

Index the 23 natively-supported files (PDF/DOCX/PPTX) plus the converted XLSX markdown files.

**Files:** None (MinerU generates index internally)

- [ ] **Step 1: Create the knowledge-base directory structure**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
mkdir -p docs\knowledge-base\wiki
mkdir -p docs\knowledge-base\index
mkdir -p docs\knowledge-base\.manual-rules
```

- [ ] **Step 2: Index training documents (PDFs, DOCX, PPTX)**

```powershell
qmd index "docs\医院材料学习"
```

This will process 23 files (17 PDF + 4 DOCX + 2 PPTX). XLSX files are skipped — they were pre-converted. On first run, MinerU auto-downloads ~2GB of models (embeddinggemma-300M, qwen3-reranker, query-expansion). This may take 10-30 minutes depending on internet speed.

Expected: Each file is chunked, embedded, and added to the search index. Progress printed to terminal.

- [ ] **Step 3: Index the converted XLSX markdown files**

```powershell
qmd index "docs\knowledge-base\.staging"
```

Expected: The staging markdown files are indexed alongside the training documents.

- [ ] **Step 4: Verify the index with a test search**

```powershell
qmd search "针法价格"
```

Expected: Search results showing needle therapy pricing information from the indexed documents.

```powershell
qmd search "推拿 一级"
```

Expected: Results about Level 1 massage pricing.

- [ ] **Step 5: Verify with a semantic query**

```powershell
qmd query "常规针法和特殊针具针法能不能同时收费"
```

Expected: Results referencing the mutual exclusion (互斥) rule for needle methods.

- [ ] **Step 6: Commit**

```powershell
git add docs/knowledge-base/
git commit -m "feat: index 26 training documents into MinerU knowledge base"
```

---

## Task 5: Generate the Wiki

Use MinerU's LLM Wiki feature to generate interlinked knowledge pages, seeded with the 5 domain categories.

**Files:**
- Create: `docs/knowledge-base/wiki/` (auto-generated by MinerU)

- [ ] **Step 1: Create a seed taxonomy file**

Create `docs/knowledge-base/wiki-seed.yml` to guide wiki generation:

```yaml
# Wiki seed taxonomy for hospital training knowledge base
categories:
  - name: 医保价格政策
    description: 上海市中医类医疗服务价格项目政策、各级别机构定价标准、加收项规则
    keywords:
      - 价格
      - 定价
      - 收费标准
      - 一级
      - 二级
      - 三级
      - 指导价

  - name: 治疗方法规则
    description: 针法、灸法、推拿、拔罐、外治等治疗方法的操作规范、叠加限制、互斥规则
    keywords:
      - 针法
      - 灸法
      - 推拿
      - 拔罐
      - 互斥
      - 叠加

  - name: 合规检查标准
    description: 医保监督检查、表单完整性、诊治一致性、治疗记录规范等审查维度
    keywords:
      - 合规
      - 检查
      - 审查
      - 监督
      - 表单
      - 签名

  - name: 信息化建设
    description: 医疗信息化建设、信息安全、数字化管理系统
    keywords:
      - 信息化
      - 数字化
      - 信息安全
      - 系统

  - name: 医院运营管理
    description: 医院运营策略、降本增效、履约考核、监管应对体系
    keywords:
      - 运营
      - 管理
      - 降本增效
      - 考核
      - 监管
```

- [ ] **Step 2: Run wiki generation**

```powershell
qmd wiki ingest
```

MinerU reads across all indexed documents, discovers topics, and generates wiki pages. The seed taxonomy guides initial categorization; MinerU auto-creates additional pages for content that spans or falls outside these categories.

Expected: Wiki pages created under `docs/knowledge-base/wiki/` organized by topic.

**Note:** If `qmd wiki ingest` does not support a seed file directly, run it without seed and then manually reorganize the output into the 5 category folders afterward. Check `qmd wiki --help` for exact syntax.

- [ ] **Step 3: Review generated wiki pages**

```powershell
Get-ChildItem -Recurse "docs\knowledge-base\wiki" -Filter "*.md" | Select-Object FullName
```

Open several pages and verify:
- Content is accurate and sourced from the correct documents
- Cross-links between related pages exist
- Source citations are present
- No hallucinated or incorrect information

- [ ] **Step 4: Reorganize if needed**

If MinerU's auto-organization doesn't match the 5-category taxonomy, manually move files:

```powershell
# Example: if a file about pricing ended up at the root
Move-Item "docs\knowledge-base\wiki\针法价格.md" "docs\knowledge-base\wiki\医保价格政策\"
```

- [ ] **Step 5: Commit**

```powershell
git add docs/knowledge-base/wiki/ docs/knowledge-base/wiki-seed.yml
git commit -m "feat: generate interlinked wiki from 26 training documents"
```

---

## Task 6: Configure MCP Server

Set up MinerU as an MCP server so Cursor agent skills can query the knowledge base at runtime.

**Files:**
- Create: `.cursor/mcp.json`

- [ ] **Step 1: Create the .cursor directory**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
mkdir -p .cursor
```

- [ ] **Step 2: Create mcp.json**

Create `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "qmd": {
      "url": "http://localhost:8181/mcp"
    }
  }
}
```

- [ ] **Step 3: Start the MCP daemon**

```powershell
qmd mcp --http --daemon
```

Expected: Server starts and prints `Listening on http://localhost:8181`

- [ ] **Step 4: Verify the server is running**

```powershell
curl http://localhost:8181/health
```

Expected: A health check response (200 OK or JSON status).

- [ ] **Step 5: Test a query via MCP**

In Cursor, open a new agent chat and ask: "Use the qmd tools to search for 针法互斥规则"

Expected: The agent uses the MCP `search` or `query` tool and returns results from the indexed documents.

- [ ] **Step 6: Commit**

```powershell
git add .cursor/mcp.json
git commit -m "feat: configure MinerU MCP server for agent runtime queries"
```

---

## Task 7: Archive Existing Skills as v1

Copy all current skill files into `v1/` subdirectories before any modifications.

**Files:**
- Create: `skills/tcm-treatment-plan/v1/SKILL.md`
- Create: `skills/tcm-treatment-plan/v1/方案参考.md`
- Create: `skills/tcm-treatment-review/v1/SKILL.md`
- Create: `skills/tcm-treatment-review/v1/standards.md`
- Create: `skills/tcm-treatment-review/v1/examples.md`
- Create: `skills/sh-yb-policy-monitor/v1/SKILL.md`
- Create: `skills/sh-yb-policy-monitor/v1/scripts/fetch_policies.py`

- [ ] **Step 1: Archive tcm-treatment-plan**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
mkdir -p skills\tcm-treatment-plan\v1
Copy-Item "skills\tcm-treatment-plan\SKILL.md" "skills\tcm-treatment-plan\v1\SKILL.md"
Copy-Item "skills\tcm-treatment-plan\方案参考.md" "skills\tcm-treatment-plan\v1\方案参考.md"
```

- [ ] **Step 2: Archive tcm-treatment-review**

```powershell
mkdir -p skills\tcm-treatment-review\v1
Copy-Item "skills\tcm-treatment-review\SKILL.md" "skills\tcm-treatment-review\v1\SKILL.md"
Copy-Item "skills\tcm-treatment-review\standards.md" "skills\tcm-treatment-review\v1\standards.md"
Copy-Item "skills\tcm-treatment-review\examples.md" "skills\tcm-treatment-review\v1\examples.md"
```

- [ ] **Step 3: Archive sh-yb-policy-monitor**

```powershell
mkdir -p skills\sh-yb-policy-monitor\v1\scripts
Copy-Item "skills\sh-yb-policy-monitor\SKILL.md" "skills\sh-yb-policy-monitor\v1\SKILL.md"
Copy-Item "skills\sh-yb-policy-monitor\scripts\fetch_policies.py" "skills\sh-yb-policy-monitor\v1\scripts\fetch_policies.py"
```

- [ ] **Step 4: Verify all archives**

```powershell
Get-ChildItem -Recurse skills\*\v1 | Select-Object FullName
```

Expected: 7 files listed across the 3 skill v1 directories.

- [ ] **Step 5: Commit**

```powershell
git add skills/tcm-treatment-plan/v1/ skills/tcm-treatment-review/v1/ skills/sh-yb-policy-monitor/v1/
git commit -m "feat: archive existing skills as v1 before KB refactoring"
```

---

## Task 8: Create knowledge-base-update Skill (v1)

A new skill that unifies all 3 ingestion paths: manual docs, online policy fetch, and manual rules.

**Files:**
- Create: `skills/knowledge-base-update/v1/SKILL.md`
- Create: `skills/knowledge-base-update/SKILL.md`

- [ ] **Step 1: Create directory structure**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
mkdir -p skills\knowledge-base-update\v1
```

- [ ] **Step 2: Write the skill file**

Create `skills/knowledge-base-update/v1/SKILL.md`:

```markdown
---
name: knowledge-base-update
description: 更新本地知识库。支持三种模式：docs（扫描新文档）、policy（从上海医保局网站获取最新政策）、rules（添加手动规则）。当用户要求更新知识库、添加新文档到知识库、获取最新政策并更新知识库、或添加新规则时使用。
---

# 知识库更新

**重要：所有输出必须全部使用中文。**

## 概述

本技能管理 `docs/knowledge-base/` 知识库的更新，支持三种数据来源：

| 模式 | 触发语 | 说明 |
|------|--------|------|
| **docs** | "更新知识库" / "添加新文档到知识库" | 扫描 `docs/医院材料学习/` 中尚未索引的文件 |
| **policy** | "获取最新政策并更新知识库" | 调用 sh-yb-policy-monitor 获取新政策，然后执行 docs 流程 |
| **rules** | "添加新规则到知识库" | 接收用户手动输入的规则内容，保存并索引 |

## 前置条件

1. MinerU Document Explorer 已安装（`qmd --version` 可用）
2. MCP 服务已启动（`qmd mcp --http --daemon`）
3. Python 环境已安装 openpyxl（XLSX 转换用）

## 执行流程

### 第一步：确定更新模式

询问用户或从上下文判断使用哪种模式（docs / policy / rules）。

### 第二步：按模式执行数据获取

#### 模式一：docs（文档扫描）

1. 列出 `docs/医院材料学习/` 中所有文件
2. 对比 `docs/knowledge-base/.manifest.json`（如果存在），找出新增或修改的文件
3. 如有 XLSX 文件，运行转换脚本：

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
.\.venv\Scripts\Activate.ps1
python scripts/xlsx_to_markdown.py
```

4. 继续到第三步

#### 模式二：policy（政策获取）

1. 运行 sh-yb-policy-monitor 技能的获取脚本：

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
.\.venv\Scripts\Activate.ps1
python skills/sh-yb-policy-monitor/scripts/fetch_policies.py --days 7
```

2. 将新获取的政策文件从 `C:\Users\roger\Documents\sh-yb-policies\` 复制到 `docs/医院材料学习/`
3. 继续到第三步

#### 模式三：rules（手动规则）

1. 请用户提供规则内容（文字描述或结构化数据）
2. 将内容保存为 markdown 文件到 `docs/knowledge-base/.manual-rules/`
3. 文件命名格式：`{YYYY-MM-DD}_{规则主题简称}.md`
4. 文件格式：

```markdown
# {规则标题}

- **添加日期**：{YYYY-MM-DD}
- **来源**：手动添加
- **类别**：{对应的wiki分类}

---

{规则内容}
```

5. 继续到第三步

### 第三步：索引新文件

对新增的文件执行 MinerU 索引：

```powershell
qmd index <新文件路径>
```

如果有多个新文件，逐个索引或批量索引整个目录。

### 第四步：更新 Wiki

运行 wiki 重新生成，更新受影响的页面：

```powershell
qmd wiki ingest
```

### 第五步：更新清单文件

更新 `docs/knowledge-base/.manifest.json`，记录：
- 文件路径
- 文件内容哈希（用于检测修改）
- 索引时间戳

清单格式：

```json
{
  "last_updated": "2026-04-07T12:00:00",
  "files": [
    {
      "path": "docs/医院材料学习/example.pdf",
      "hash": "sha256:abc123...",
      "indexed_at": "2026-04-07T12:00:00"
    }
  ]
}
```

使用 Python 计算文件哈希：

```python
import hashlib
from pathlib import Path

def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"
```

### 第六步：输出报告

向用户汇报更新结果：

```
## 知识库更新报告

- **更新模式**：{docs/policy/rules}
- **新增文件**：{N} 个
- **更新Wiki页面**：{M} 个
- **错误**：{如有}

### 新增文件列表
1. {文件名} — {大小}
2. ...

### 更新的Wiki页面
1. {页面路径} — {新建/更新}
2. ...
```

## 知识库目录结构

```
docs/knowledge-base/
├── wiki/                          # Wiki 页面（5大分类）
│   ├── 医保价格政策/
│   ├── 治疗方法规则/
│   ├── 合规检查标准/
│   ├── 信息化建设/
│   └── 医院运营管理/
├── index/                         # MinerU 搜索索引
├── .staging/                      # XLSX 转 MD 暂存
├── .manual-rules/                 # 手动添加的规则
└── .manifest.json                 # 索引跟踪清单
```
```

- [ ] **Step 3: Copy to root SKILL.md**

```powershell
Copy-Item "skills\knowledge-base-update\v1\SKILL.md" "skills\knowledge-base-update\SKILL.md"
```

- [ ] **Step 4: Verify file contents**

```powershell
Get-ChildItem -Recurse skills\knowledge-base-update | Select-Object FullName
```

Expected:
```
skills\knowledge-base-update\v1\SKILL.md
skills\knowledge-base-update\SKILL.md
```

- [ ] **Step 5: Commit**

```powershell
git add skills/knowledge-base-update/
git commit -m "feat: add knowledge-base-update skill (v1) with 3 ingestion modes"
```

---

## Task 9: Refactor tcm-treatment-plan to v2 (KB-Powered)

Replace hardcoded pricing tables and rules with instructions to query the knowledge base via MCP.

**Files:**
- Create: `skills/tcm-treatment-plan/v2/SKILL.md`
- Create: `skills/tcm-treatment-plan/v2/方案参考.md`
- Modify: `skills/tcm-treatment-plan/SKILL.md` (overwrite with v2)

- [ ] **Step 1: Create v2 directory**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
mkdir -p skills\tcm-treatment-plan\v2
```

- [ ] **Step 2: Write v2 SKILL.md**

Create `skills/tcm-treatment-plan/v2/SKILL.md`:

```markdown
---
name: tcm-treatment-plan
version: v2
description: 作为经验丰富的中医师，根据患者的体重、年龄、性别及症状，制定分阶段中医治疗方案，给出治疗周期，并通过知识库查询最新上海医保价格政策优化客单价。当用户提供患者症状信息并请求制定中医治疗方案时使用。
---

# 中医治疗方案制定（v2 — 知识库驱动）

**重要：所有输出必须全部使用中文。**

**版本说明：** v2 通过 MinerU 知识库动态查询最新价格和规则，替代 v1 中的硬编码数据。如知识库不可用，方案仍可生成但可能不反映最新政策，请在输出中注明。

## 前置条件

- MinerU MCP 服务应已启动（`qmd mcp --http --daemon`）
- 如 MCP 不可用，在方案底部注明："⚠️ 知识库未连接，价格数据可能非最新，请人工核实。"

## 角色定位

你是一位经验丰富的中医师，擅长辨证论治，熟悉上海市医保中医项目定价体系。你的目标是：
1. 根据患者信息进行辨证分型
2. 制定科学合理的分阶段治疗方案
3. 在保证治疗合理性的前提下，最大化每次治疗的客单价

## 问诊流程

### 第一步：采集患者信息

必需信息：
- 性别、年龄、体重
- 主诉症状（部位、性质、持续时间、加重/缓解因素）

可选信息（如患者提供）：
- 既往病史、过敏史
- 舌象、脉象描述
- 生活习惯（久坐、运动量等）

### 第二步：辨证论治

根据症状进行中医辨证分型，给出：
- 中医诊断（病名 + 证型），如：项痹（气滞血瘀证）
- 对应西医诊断参考，如：颈椎病
- 病机分析（简要）

**提高客单价要点**：诊断应尽量覆盖多个相关部位/病症，为多部位治疗提供依据。例如颈椎病患者常伴有肩部不适、头痛、腰部问题，应完整纳入诊断。

### 第三步：查询知识库获取最新数据

在制定方案前，**必须**通过 MCP 工具查询以下信息：

1. **查询价格标准**：使用 `query` 或 `wiki_read` 查询一级机构各项目最新价格

   查询示例：
   - "一级机构 针法 价格"
   - "一级机构 推拿 各部位 价格"
   - "灸法 拔罐 价格 一级"

2. **查询叠加规则**：使用 `wiki_read` 阅读治疗方法规则

   查询示例：
   - "针法互斥与叠加规则"
   - "加收项配对规则"

3. **查询组套方案参考**：使用 `search` 搜索推荐治疗组合

   查询示例：
   - "推荐治疗组套方案"
   - "客单价优化策略"

### 第四步：制定分阶段治疗方案（初稿）

将治疗分为2-3个阶段，每个阶段给出：
- 治疗目标
- 治疗项目组合（使用知识库查询到的最新价格）
- 治疗频次与周期
- 单次费用及阶段总费用

**默认治疗频次**：除特殊情况外，所有阶段均保持**每周3次**的治疗频次。仅在以下情况可调整：
- 患者明确表示时间受限，无法每周3次
- 病情极轻微，每周3次临床上不合理
- 维护阶段患者症状已基本消除，可酌情降至每周1-2次

### 第五步：医保合规自审（输出前必须执行）

**在将方案呈现给患者之前，必须先对初稿进行医保合规自审。** 通过知识库查询最新审查标准：

使用 MCP 查询：
- "wiki_read 合规检查标准/七大审查维度"
- "query 加收项必须搭配基础项"

#### 自审维度（逐项检查）

| 维度 | 检查内容 | 方案场景适配说明 |
|-----|---------|---------------|
| 1. 方案完整性 | 患者信息（性别/年龄/体重）、诊断、项目明细、费用是否齐全 | 替代表单完整性检查 |
| 2. 诊治一致性 | 每个治疗项目是否都有对应诊断支持；推拿部位是否与诊断病症部位匹配；穴位是否与病症解剖学对应 | 重点：多部位推拿时，每个部位必须有独立诊断依据 |
| 3. 针法不叠加 | 常规针法/特殊针具针法/特殊手法针法三者互斥，同次治疗仅取最高价一项；特殊穴位（部位）针法、体表针法、仪器针法可叠加 | 如发现叠加违规，保留最高价项，删除低价项 |
| 4. 加收项配对 | 药物罐（加收）必须搭配中医拔罐；中药烫熨特大加收必须搭配中药烫熨；职称加收项不可叠加（取其一） | 检查每个加收项是否都有基础项 |
| 5. 收费合规性 | 所有单价是否符合一级机构官方价格表 — **通过知识库查询验证** | 逐项核对单价，不得高于政府指导价 |
| 6. 部位/穴位标注 | 推拿须标明部位，针法须标明取穴，穴位埋入须标明穴位名称 | 确保方案中每个项目的说明栏都有明确的部位或穴位 |
| 7. 客单价合理性 | 单次费用是否在合理区间（一般300-550元/次）；阶段间是否体现递减趋势 | 过高则删减项目，过低则补充合规项目 |

#### 自审流程

1. **逐维度检查**：对初稿方案的每个阶段逐一检查以上7个维度
2. **发现问题立即修正**：
   - 针法叠加违规 → 保留最高价项，删除其余互斥项
   - 加收项缺配对 → 补上基础项或删除加收项
   - 单价错误 → 更正为知识库中的官方价格
   - 诊治不一致 → 调整诊断覆盖或删除无诊断支持的项目
   - 部位/穴位缺失 → 补充标注
3. **优化客单价**：在合规前提下，检查是否遗漏了可合理叠加的项目
4. **生成审查摘要**：在最终方案之前，内部完成审查（不向患者展示审查过程），确认所有维度通过后再输出

## 客单价优化策略

在保证治疗合理性的前提下，通过知识库查询最新可叠加项目清单，按以下优先级叠加：

1. **推拿**：开满3个部位（核心高价项）— 通过 KB 查询各部位最新价格
2. **针法**：选高价+可叠加项 — 通过 KB 查询互斥规则
3. **叠加独立计费项目**：穴位埋入、耳穴疗法、中药烫熨、针刀疗法 — 通过 KB 查询最新单价
4. **灸法**：选高价项（铺灸/督灸优先）
5. **拔罐**：用加收项（中医拔罐+药物罐）
6. **职称加收**：主任医师/副主任医师加收

## 治疗方案模板

### 输出格式

```
# 治疗方案

## 患者信息
- 姓名/编号：xxx
- 性别：x  年龄：xx岁  体重：xxkg

## 辨证分析
- **中医诊断**：[病名]（[证型]）
- **西医参考**：[西医诊断]
- **病机**：[简要病机分析]

## 治疗方案

### 第一阶段：[阶段名称]（第1-N次，约X周）

**治疗目标**：[目标描述]

| 序号 | 项目 | 单价（元） | 说明 |
|-----|------|----------|------|
| 1 | xxx | xx | 部位/穴位 |
| ... | ... | ... | ... |

**单次费用**：xxx元
**本阶段费用**：xxx元（N次）
**治疗频次**：每周X次

### 第二阶段：[阶段名称]（第N+1-M次，约X周）
[同上格式]

### 第三阶段（如需）：[阶段名称]
[同上格式]

## 费用汇总

| 阶段 | 次数 | 单次费用 | 小计 |
|-----|------|---------|------|
| 第一阶段 | N | xxx | xxx |
| 第二阶段 | M | xxx | xxx |
| **合计** | | | **xxx元** |

## 注意事项
- [饮食/生活建议]
- [复诊/调整时机]

## 数据来源
- 价格数据来自知识库查询（最后更新：[日期]）
- 如价格与实际收费有出入，以医院最新公示为准
```

## 常见病症方案参考

详见 [方案参考.md](方案参考.md)。
```

- [ ] **Step 3: Copy 方案参考.md to v2**

The reference doc is skill-specific and stays as-is:

```powershell
Copy-Item "skills\tcm-treatment-plan\方案参考.md" "skills\tcm-treatment-plan\v2\方案参考.md"
```

- [ ] **Step 4: Update root SKILL.md to point to v2**

```powershell
Copy-Item "skills\tcm-treatment-plan\v2\SKILL.md" "skills\tcm-treatment-plan\SKILL.md" -Force
```

- [ ] **Step 5: Verify file structure**

```powershell
Get-ChildItem -Recurse skills\tcm-treatment-plan | Select-Object FullName
```

Expected:
```
skills\tcm-treatment-plan\v1\SKILL.md
skills\tcm-treatment-plan\v1\方案参考.md
skills\tcm-treatment-plan\v2\SKILL.md
skills\tcm-treatment-plan\v2\方案参考.md
skills\tcm-treatment-plan\SKILL.md          ← copy of v2
skills\tcm-treatment-plan\方案参考.md        ← original (unchanged)
```

- [ ] **Step 6: Commit**

```powershell
git add skills/tcm-treatment-plan/
git commit -m "feat: refactor tcm-treatment-plan to v2 with KB-powered pricing queries"
```

---

## Task 10: Refactor tcm-treatment-review to v2 (KB-Powered + Pipeline)

> **CROSS-REFERENCE:** The complete v2 SKILL.md for `tcm-treatment-review` is defined in the
> **Review Pipeline Plan** (`docs/superpowers/plans/2026-04-07-review-pipeline.md`, Task 5).
> That plan creates the concurrent pipeline (subagent-per-image, multi-form detection, SQLite storage)
> AND integrates KB-powered pricing. **Execute the pipeline plan's Tasks 1-5 instead of the steps below.**
>
> This task only handles v1 archiving (already done in Task 7) and the v2 directory setup.

The v2 skill combines two features:
1. **KB integration** — pricing lookups via MCP instead of hardcoded `standards.md`
2. **Concurrent pipeline** — one subagent per image, multi-form detection, SQLite result storage

**Files:**
- Create: `skills/tcm-treatment-review/v2/SKILL.md` (from pipeline plan Task 5)
- Create: `skills/tcm-treatment-review/v2/examples.md`
- Modify: `skills/tcm-treatment-review/SKILL.md` (overwrite with v2)

- [ ] **Step 1: Create v2 directory**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
mkdir -p skills\tcm-treatment-review\v2
```

- [ ] **Step 2: Execute pipeline plan Tasks 1-5**

Follow `docs/superpowers/plans/2026-04-07-review-pipeline.md` Tasks 1 through 5. This creates:
- `.gitignore` (Task 1)
- `tests/test_review_db.py` (Task 2)
- `scripts/review_db.py` (Task 3)
- CLI verification (Task 4)
- `skills/tcm-treatment-review/SKILL.md` — the unified v2 with both pipeline and KB features (Task 5)

- [ ] **Step 3: Copy the pipeline SKILL.md into v2 folder**

```powershell
Copy-Item "skills\tcm-treatment-review\SKILL.md" "skills\tcm-treatment-review\v2\SKILL.md"
```

- [ ] **Step 4: Copy examples.md to v2**

Examples are skill-specific and stay as-is:

```powershell
Copy-Item "skills\tcm-treatment-review\examples.md" "skills\tcm-treatment-review\v2\examples.md"
```

- [ ] **Step 5: Verify file structure**

```powershell
Get-ChildItem -Recurse skills\tcm-treatment-review | Select-Object FullName
```

Expected:
```
skills\tcm-treatment-review\v1\SKILL.md
skills\tcm-treatment-review\v1\standards.md
skills\tcm-treatment-review\v1\examples.md
skills\tcm-treatment-review\v2\SKILL.md          ← pipeline + KB version
skills\tcm-treatment-review\v2\examples.md
skills\tcm-treatment-review\SKILL.md             ← copy of v2 (pipeline + KB)
skills\tcm-treatment-review\examples.md          ← original (unchanged)
skills\tcm-treatment-review\standards.md         ← original (kept for reference, v2 uses KB instead)
```

- [ ] **Step 6: Commit**

```powershell
git add skills/tcm-treatment-review/
git commit -m "feat: refactor tcm-treatment-review to v2 with KB pricing + concurrent pipeline"
```

---

## Task 11: Refactor sh-yb-policy-monitor to v2 (KB Integration)

Enhance the policy monitor to trigger a knowledge base update after fetching new policies.

**Files:**
- Create: `skills/sh-yb-policy-monitor/v2/SKILL.md`
- Create: `skills/sh-yb-policy-monitor/v2/scripts/fetch_policies.py`
- Modify: `skills/sh-yb-policy-monitor/SKILL.md` (overwrite with v2)

- [ ] **Step 1: Create v2 directory**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
mkdir -p skills\sh-yb-policy-monitor\v2\scripts
```

- [ ] **Step 2: Write v2 SKILL.md**

Create `skills/sh-yb-policy-monitor/v2/SKILL.md`:

```markdown
---
name: sh-yb-policy-monitor
version: v2
description: 监控上海市医疗保障局官网（ybj.sh.gov.cn），获取最新医保政策、动态和公告。下载保存至本地并自动更新知识库。当用户询问上海医保最新政策、最新公告、医保动态，或需要检查医保局网站是否有新文件发布时使用。
---

# 上海医保局政策监控（v2 — 知识库联动）

**版本说明：** v2 在获取政策后自动触发知识库更新，将新政策文件索引到 MinerU 知识库并更新 Wiki 页面。

## 监控范围

| 栏目 | URL | 代号 |
|------|-----|------|
| 医保动态 | https://ybj.sh.gov.cn/ybdt/index.html | ybdt |
| 最新政策 | https://ybj.sh.gov.cn/zxzc/index.html | zxzc |
| 公示公告 | https://ybj.sh.gov.cn/gsgg/index.html | gsgg |

## 文件存储

- **主存储路径**：`C:\Users\roger\Documents\sh-yb-policies\`
- **知识库副本**：获取后自动复制到 `docs/医院材料学习/` 以便知识库索引
- **文件命名**：`{YYYY-MM-DD}_{栏目代号}_{标题简称}.md`

## 执行流程

### 方式一：Python 脚本（推荐）

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
.\.venv\Scripts\Activate.ps1
python skills/sh-yb-policy-monitor/scripts/fetch_policies.py
```

可选参数：
- `--date YYYY-MM-DD`：指定检查日期，默认为昨天
- `--days N`：检查最近 N 天，默认为 1

### 方式二：WebFetch 手动流程

如脚本不可用，按以下步骤手动执行：

1. **确定检查日期**：获取今天日期，默认检查昨天
2. **逐栏目访问**：用 WebFetch 访问三个列表页 URL
3. **筛选文章**：从返回内容中找出目标日期发布的文章，提取标题和链接
4. **获取详情**：用 WebFetch 访问每篇文章的详情链接
5. **保存文件**：用 Write 工具保存到指定路径（格式见下方"文件格式"）
6. **生成摘要**：汇总所有新文章，按"输出格式"呈现

## 获取后：知识库更新（v2 新增）

脚本运行完毕后，**必须执行以下步骤**将新政策纳入知识库：

1. **复制到知识库源目录**：将新获取的文件从 `C:\Users\roger\Documents\sh-yb-policies\` 复制到 `docs/医院材料学习/`

```powershell
$newFiles = Get-ChildItem "C:\Users\roger\Documents\sh-yb-policies\*.md" | Where-Object { $_.LastWriteTime -gt (Get-Date).AddDays(-7) }
foreach ($f in $newFiles) {
    Copy-Item $f.FullName "docs\医院材料学习\" -ErrorAction SilentlyContinue
}
```

2. **索引新文件**：

```powershell
qmd index "docs\医院材料学习"
```

3. **更新 Wiki**：

```powershell
qmd wiki ingest
```

4. **在输出中注明**：在摘要末尾添加知识库更新状态

如 MinerU 未安装或 MCP 服务未运行，跳过知识库更新步骤并在输出中注明："⚠️ 知识库未更新（MinerU 不可用），请手动运行 knowledge-base-update 技能。"

## 文件格式

每篇文章保存为：

```markdown
# {文章标题}

- **来源**：上海市医疗保障局
- **栏目**：{栏目名称}
- **发布日期**：{YYYY-MM-DD}
- **原文链接**：{URL}

---

{正文内容}
```

## 输出格式

```
## 上海医保局最新文件摘要（{检查日期}）

### 一、医保动态
#### 1. {文章标题}
- **发布日期**：{日期}
- **要点**：
  - 要点1
  - 要点2
- **已保存至**：{本地文件路径}

### 二、最新政策
[同上格式]

### 三、公示公告
[同上格式]

---
本次共获取 {N} 篇新文件，已保存至 C:\Users\roger\Documents\sh-yb-policies\

### 知识库更新状态
- ✅ 已索引 {N} 个新文件到知识库
- ✅ Wiki 页面已更新
```

如所有栏目均无目标日期的新文章，回复：
> 已检查上海市医保局三个栏目（医保动态/最新政策/公示公告），{目标日期}无新发布内容。知识库无需更新。
```

- [ ] **Step 3: Copy fetch_policies.py to v2**

The script itself doesn't change — the KB update steps are handled by the skill instructions, not the script:

```powershell
Copy-Item "skills\sh-yb-policy-monitor\scripts\fetch_policies.py" "skills\sh-yb-policy-monitor\v2\scripts\fetch_policies.py"
```

- [ ] **Step 4: Update root SKILL.md to v2**

```powershell
Copy-Item "skills\sh-yb-policy-monitor\v2\SKILL.md" "skills\sh-yb-policy-monitor\SKILL.md" -Force
```

- [ ] **Step 5: Verify file structure**

```powershell
Get-ChildItem -Recurse skills\sh-yb-policy-monitor | Select-Object FullName
```

Expected:
```
skills\sh-yb-policy-monitor\v1\SKILL.md
skills\sh-yb-policy-monitor\v1\scripts\fetch_policies.py
skills\sh-yb-policy-monitor\v2\SKILL.md
skills\sh-yb-policy-monitor\v2\scripts\fetch_policies.py
skills\sh-yb-policy-monitor\SKILL.md          ← copy of v2
skills\sh-yb-policy-monitor\scripts\fetch_policies.py  ← original
```

- [ ] **Step 6: Commit**

```powershell
git add skills/sh-yb-policy-monitor/
git commit -m "feat: refactor sh-yb-policy-monitor to v2 with automatic KB update after fetch"
```

---

## Task 12: Test knowledge-base-update Skill — docs Mode

Verify the docs ingestion mode works end-to-end.

**Files:** None (testing only)

- [ ] **Step 1: Ensure MCP server is running**

```powershell
qmd mcp --http --daemon
```

- [ ] **Step 2: Test docs mode manually**

In a Cursor agent chat, say: "更新知识库，扫描新文档"

Expected behavior:
1. Agent recognizes `knowledge-base-update` skill
2. Checks `docs/医院材料学习/` against manifest
3. Reports which files are new/changed
4. Runs indexing for any new files
5. Reports completion

- [ ] **Step 3: Verify a search query returns updated results**

In the same chat, ask: "搜索知识库：推拿按部位收费规则"

Expected: Results referencing the massage pricing documents.

---

## Task 13: Test tcm-treatment-plan v2

Verify the KB-powered treatment plan skill works correctly.

**Files:** None (testing only)

- [ ] **Step 1: Ensure MCP server is running**

```powershell
qmd mcp --http --daemon
```

- [ ] **Step 2: Test with a sample patient case**

In a Cursor agent chat, say:

"请根据以下患者信息制定治疗方案：男性，45岁，75kg，主诉颈部酸痛3个月，伴肩部僵硬，久坐办公。"

Expected behavior:
1. Agent uses `tcm-treatment-plan` v2 skill
2. Agent queries MCP for pricing data (you should see MCP tool calls in the output)
3. Agent produces a multi-phase treatment plan with correct pricing
4. Pricing matches the knowledge base data

- [ ] **Step 3: Verify pricing accuracy**

Cross-check the generated plan's pricing against `skills/tcm-treatment-review/v1/standards.md` (the archived ground truth):
- 常规针法 should be 50元
- 颈部推拿 should be 36元 (一级)
- 脊柱推拿 should be 70元

---

## Task 14: Test tcm-treatment-review v2

Verify the KB-powered review skill with concurrent pipeline works correctly.

> **Note:** For full pipeline testing (batch images, multi-form detection, SQLite storage),
> also run Tasks 6-8 from the pipeline plan (`docs/superpowers/plans/2026-04-07-review-pipeline.md`).

**Files:** None (testing only)

- [ ] **Step 1: Ensure MCP server is running**

```powershell
qmd mcp --http --daemon
```

- [ ] **Step 2: Test single-image mode with KB queries**

"请审查以下治疗信息：患者张三，男，50岁，诊断腰痹（气滞血瘀证），治疗项目：常规针法50元、特殊针具针法60元、腰部疾病推拿80元。"

Expected behavior:
1. Agent uses `tcm-treatment-review` v2 skill (single-image mode)
2. Agent queries MCP for pricing verification (you should see MCP tool calls)
3. Agent correctly identifies 针法叠加违规 (常规针法 + 特殊针具针法 are mutually exclusive)
4. Agent outputs the 7-dimension review table with data source noted

---

## Task 15: Test Fallback Behavior (MCP Down)

Verify skills work gracefully when the knowledge base is unavailable.

**Files:** None (testing only)

- [ ] **Step 1: Stop the MCP server**

```powershell
qmd mcp stop
```

- [ ] **Step 2: Test tcm-treatment-plan v2 without MCP**

In a Cursor agent chat, ask for a treatment plan.

Expected: The skill generates a plan but includes the warning: "⚠️ 知识库未连接，价格数据可能非最新，请人工核实。"

- [ ] **Step 3: Test tcm-treatment-review v2 without MCP**

In a Cursor agent chat, ask for a treatment form review.

Expected: The skill produces the review but dimension 5 (收费合规性) shows: "⚠️ 知识库未连接，无法核实最新价格"

- [ ] **Step 4: Restart MCP server**

```powershell
qmd mcp --http --daemon
```

---

## Task 16: Test Incremental Indexing

Verify that adding a new document to the knowledge base works correctly.

**Files:** None (testing only)

- [ ] **Step 1: Create a test document**

Create a test markdown file in `docs/knowledge-base/.manual-rules/`:

```powershell
$content = @"
# 测试规则 — 知识库增量索引验证

- **添加日期**：$(Get-Date -Format yyyy-MM-dd)
- **来源**：手动添加
- **类别**：合规检查标准

---

这是一条测试规则，用于验证知识库增量索引功能。

测试内容：针刀疗法在每个部位最多收取一次费用，不可对同一部位重复计费。
"@
$content | Out-File -FilePath "docs\knowledge-base\.manual-rules\$(Get-Date -Format yyyy-MM-dd)_增量索引测试.md" -Encoding utf8
```

- [ ] **Step 2: Index the new file**

```powershell
qmd index "docs\knowledge-base\.manual-rules"
```

- [ ] **Step 3: Verify the new content is searchable**

```powershell
qmd search "增量索引测试"
```

Expected: The test document appears in search results.

- [ ] **Step 4: Clean up the test file**

```powershell
Remove-Item "docs\knowledge-base\.manual-rules\*增量索引测试*"
```

- [ ] **Step 5: Final commit**

```powershell
git add -A
git commit -m "chore: complete KB implementation — all tasks verified"
```
