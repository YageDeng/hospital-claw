# 知识库实施计划

> **给智能代理工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 来逐任务执行本计划。步骤使用复选框（`- [ ]`）语法进行跟踪。

**目标：** 使用 MinerU Document Explorer 处理 26 份中医培训文档，构建互链 Wiki 知识库，配置 MCP 供代理运行时查询，并重构 3 个现有技能以知识库作为唯一数据源。

**架构：** 三源数据摄取（手动文档、在线政策获取、手动规则）→ MinerU Document Explorer（索引 + Wiki + 混合搜索）→ `docs/knowledge-base/`（Wiki 页面 + 搜索索引）→ MCP 服务 + 版本化技能（v2 = 知识库驱动，v1 = 归档原始版本）。

**技术栈：** MinerU Document Explorer (Node.js >= 22)、Python 3.10+（pymupdf、python-docx、python-pptx、openpyxl）、MCP 协议（HTTP 守护进程运行在端口 8181）

**设计规范：** `docs/superpowers/specs/2026-04-07-knowledge-base-design.md`

---

## 文件结构

### 需要创建的新文件

| 文件 | 职责 |
|------|------|
| `scripts/xlsx_to_markdown.py` | 将 XLSX 文件转换为 Markdown 表格以供 MinerU 摄取 |
| `docs/knowledge-base/.staging/` | 存放 XLSX → MD 转换文件的目录 |
| `docs/knowledge-base/.manual-rules/` | 存放手动编写规则文件的目录 |
| `docs/knowledge-base/wiki/` | MinerU 生成的互链 Wiki 页面 |
| `docs/knowledge-base/index/` | MinerU 搜索索引 |
| `.cursor/mcp.json` | MinerU MCP 服务配置 |
| `skills/knowledge-base-update/v1/SKILL.md` | 新的统一知识库更新技能 |
| `skills/knowledge-base-update/SKILL.md` | 最新版本的副本 |
| `skills/tcm-treatment-plan/v1/SKILL.md` | 归档原始版本 |
| `skills/tcm-treatment-plan/v1/方案参考.md` | 归档原始版本 |
| `skills/tcm-treatment-plan/v2/SKILL.md` | 知识库驱动的重构版本 |
| `skills/tcm-treatment-plan/v2/方案参考.md` | 保持原样（技能专属） |
| `skills/tcm-treatment-review/v1/SKILL.md` | 归档原始版本 |
| `skills/tcm-treatment-review/v1/standards.md` | 归档原始版本 |
| `skills/tcm-treatment-review/v1/examples.md` | 归档原始版本 |
| `skills/tcm-treatment-review/v2/SKILL.md` | 知识库驱动的重构版本 |
| `skills/tcm-treatment-review/v2/examples.md` | 保持原样（技能专属） |
| `skills/sh-yb-policy-monitor/v1/SKILL.md` | 归档原始版本 |
| `skills/sh-yb-policy-monitor/v1/scripts/fetch_policies.py` | 归档原始版本 |
| `skills/sh-yb-policy-monitor/v2/SKILL.md` | 增强版，带知识库触发 |
| `skills/sh-yb-policy-monitor/v2/scripts/fetch_policies.py` | 增强版，带知识库触发 |

---

## 任务 1：安装 Node.js

MinerU Document Explorer 需要 Node.js >= 22。当前机器**尚未安装**。

**文件：** 无（系统级安装）

- [ ] **步骤 1：下载并安装 Node.js**

前往 https://nodejs.org/ 下载 Windows 安装程序（Node.js LTS v22+）。使用默认设置运行安装程序。

或者使用 winget：

```powershell
winget install OpenJS.NodeJS.LTS
```

- [ ] **步骤 2：验证 Node.js 安装**

关闭并重新打开终端，然后运行：

```powershell
node --version
```

预期输出：`v22.x.x` 或更高版本

```powershell
npm --version
```

预期输出：`10.x.x` 或更高版本

- [ ] **步骤 3：提交**

无需提交文件 — 系统级安装。

---

## 任务 2：安装 MinerU Document Explorer

**文件：** 无（全局 npm 包）

- [ ] **步骤 1：全局安装 MinerU Document Explorer**

```powershell
npm install -g mineru-document-explorer
```

- [ ] **步骤 2：验证安装**

```powershell
qmd --version
```

预期输出：打印版本号（如 `1.x.x`）

- [ ] **步骤 3：安装文档处理所需的 Python 依赖**

先激活项目虚拟环境，然后安装：

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
.\.venv\Scripts\Activate.ps1
pip install pymupdf python-docx python-pptx openpyxl
```

- [ ] **步骤 4：验证 Python 依赖**

```powershell
python -c "import pymupdf; import docx; import pptx; import openpyxl; print('All dependencies OK')"
```

预期输出：`All dependencies OK`

- [ ] **步骤 5：提交**

无需提交文件 — 依赖安装。

---

## 任务 3：创建 XLSX 转 Markdown 转换脚本

`docs/医院材料学习/` 中的 3 个 XLSX 文件不被 MinerU 原生支持。此脚本将每个工作表转换为 Markdown 表格。

**文件：**
- 创建：`scripts/xlsx_to_markdown.py`

- [ ] **步骤 1：创建 scripts 目录和转换脚本**

创建 `scripts/xlsx_to_markdown.py`：

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

- [ ] **步骤 2：运行转换脚本**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
.\.venv\Scripts\Activate.ps1
python scripts/xlsx_to_markdown.py
```

预期输出：3 个 XLSX 文件转换完成，Markdown 文件出现在 `docs/knowledge-base/.staging/`

- [ ] **步骤 3：验证输出**

```powershell
Get-ChildItem "docs\knowledge-base\.staging" | Format-Table Name, Length
```

预期输出：多个 `.md` 文件（每个 XLSX 中的每个工作表对应一个）

- [ ] **步骤 4：抽查一个转换后的文件**

打开其中一个生成的 `.md` 文件并验证：
- 表头与原始 XLSX 列名匹配
- 数据行完整
- 中文字符正确显示

- [ ] **步骤 5：提交**

```powershell
git add scripts/xlsx_to_markdown.py docs/knowledge-base/.staging/
git commit -m "feat: add XLSX-to-markdown conversion script and initial staging files"
```

---

## 任务 4：使用 MinerU 索引所有文档

索引 23 个原生支持的文件（PDF/DOCX/PPTX）以及转换后的 XLSX Markdown 文件。

**文件：** 无（MinerU 在内部生成索引）

- [ ] **步骤 1：创建知识库目录结构**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
mkdir -p docs\knowledge-base\wiki
mkdir -p docs\knowledge-base\index
mkdir -p docs\knowledge-base\.manual-rules
```

- [ ] **步骤 2：索引培训文档（PDF、DOCX、PPTX）**

```powershell
qmd index "docs\医院材料学习"
```

此操作将处理 23 个文件（17 个 PDF + 4 个 DOCX + 2 个 PPTX）。XLSX 文件被跳过——它们已经预先转换。首次运行时，MinerU 会自动下载约 2GB 的模型（embeddinggemma-300M、qwen3-reranker、query-expansion）。根据网速，这可能需要 10-30 分钟。

预期输出：每个文件被分块、向量化并添加到搜索索引中。终端打印进度信息。

- [ ] **步骤 3：索引转换后的 XLSX Markdown 文件**

```powershell
qmd index "docs\knowledge-base\.staging"
```

预期输出：暂存区的 Markdown 文件与培训文档一起被索引。

- [ ] **步骤 4：通过测试搜索验证索引**

```powershell
qmd search "针法价格"
```

预期输出：搜索结果显示来自已索引文档的针法价格信息。

```powershell
qmd search "推拿 一级"
```

预期输出：关于一级推拿定价的结果。

- [ ] **步骤 5：通过语义查询验证**

```powershell
qmd query "常规针法和特殊针具针法能不能同时收费"
```

预期输出：结果引用针法互斥规则。

- [ ] **步骤 6：提交**

```powershell
git add docs/knowledge-base/
git commit -m "feat: index 26 training documents into MinerU knowledge base"
```

---

## 任务 5：生成 Wiki

使用 MinerU 的 LLM Wiki 功能生成互链知识页面，以 5 个领域分类作为种子。

**文件：**
- 创建：`docs/knowledge-base/wiki/`（由 MinerU 自动生成）

- [ ] **步骤 1：创建种子分类文件**

创建 `docs/knowledge-base/wiki-seed.yml` 以引导 Wiki 生成：

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

- [ ] **步骤 2：运行 Wiki 生成**

```powershell
qmd wiki ingest
```

MinerU 读取所有已索引的文档，发现主题，并生成 Wiki 页面。种子分类引导初始分类；MinerU 会为跨越或超出这些分类的内容自动创建额外页面。

预期输出：Wiki 页面按主题组织创建在 `docs/knowledge-base/wiki/` 下。

**注意：** 如果 `qmd wiki ingest` 不直接支持种子文件，则不使用种子运行，然后手动将输出重新组织到 5 个分类文件夹中。请查看 `qmd wiki --help` 获取确切语法。

- [ ] **步骤 3：审查生成的 Wiki 页面**

```powershell
Get-ChildItem -Recurse "docs\knowledge-base\wiki" -Filter "*.md" | Select-Object FullName
```

打开若干页面并验证：
- 内容准确且来源于正确的文档
- 相关页面之间存在交叉链接
- 包含来源引用
- 无虚构或错误信息

- [ ] **步骤 4：如需要则重新组织**

如果 MinerU 的自动组织与 5 个分类体系不匹配，手动移动文件：

```powershell
# Example: if a file about pricing ended up at the root
Move-Item "docs\knowledge-base\wiki\针法价格.md" "docs\knowledge-base\wiki\医保价格政策\"
```

- [ ] **步骤 5：提交**

```powershell
git add docs/knowledge-base/wiki/ docs/knowledge-base/wiki-seed.yml
git commit -m "feat: generate interlinked wiki from 26 training documents"
```

---

## 任务 6：配置 MCP 服务

设置 MinerU 作为 MCP 服务，使 Cursor 代理技能可以在运行时查询知识库。

**文件：**
- 创建：`.cursor/mcp.json`

- [ ] **步骤 1：创建 .cursor 目录**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
mkdir -p .cursor
```

- [ ] **步骤 2：创建 mcp.json**

创建 `.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "qmd": {
      "url": "http://localhost:8181/mcp"
    }
  }
}
```

- [ ] **步骤 3：启动 MCP 守护进程**

```powershell
qmd mcp --http --daemon
```

预期输出：服务启动并打印 `Listening on http://localhost:8181`

- [ ] **步骤 4：验证服务运行状态**

```powershell
curl http://localhost:8181/health
```

预期输出：健康检查响应（200 OK 或 JSON 状态）。

- [ ] **步骤 5：通过 MCP 测试查询**

在 Cursor 中打开一个新的代理聊天并输入："Use the qmd tools to search for 针法互斥规则"

预期输出：代理使用 MCP 的 `search` 或 `query` 工具并返回来自已索引文档的结果。

- [ ] **步骤 6：提交**

```powershell
git add .cursor/mcp.json
git commit -m "feat: configure MinerU MCP server for agent runtime queries"
```

---

## 任务 7：将现有技能归档为 v1

在进行任何修改之前，将所有当前技能文件复制到 `v1/` 子目录中。

**文件：**
- 创建：`skills/tcm-treatment-plan/v1/SKILL.md`
- 创建：`skills/tcm-treatment-plan/v1/方案参考.md`
- 创建：`skills/tcm-treatment-review/v1/SKILL.md`
- 创建：`skills/tcm-treatment-review/v1/standards.md`
- 创建：`skills/tcm-treatment-review/v1/examples.md`
- 创建：`skills/sh-yb-policy-monitor/v1/SKILL.md`
- 创建：`skills/sh-yb-policy-monitor/v1/scripts/fetch_policies.py`

- [ ] **步骤 1：归档 tcm-treatment-plan**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
mkdir -p skills\tcm-treatment-plan\v1
Copy-Item "skills\tcm-treatment-plan\SKILL.md" "skills\tcm-treatment-plan\v1\SKILL.md"
Copy-Item "skills\tcm-treatment-plan\方案参考.md" "skills\tcm-treatment-plan\v1\方案参考.md"
```

- [ ] **步骤 2：归档 tcm-treatment-review**

```powershell
mkdir -p skills\tcm-treatment-review\v1
Copy-Item "skills\tcm-treatment-review\SKILL.md" "skills\tcm-treatment-review\v1\SKILL.md"
Copy-Item "skills\tcm-treatment-review\standards.md" "skills\tcm-treatment-review\v1\standards.md"
Copy-Item "skills\tcm-treatment-review\examples.md" "skills\tcm-treatment-review\v1\examples.md"
```

- [ ] **步骤 3：归档 sh-yb-policy-monitor**

```powershell
mkdir -p skills\sh-yb-policy-monitor\v1\scripts
Copy-Item "skills\sh-yb-policy-monitor\SKILL.md" "skills\sh-yb-policy-monitor\v1\SKILL.md"
Copy-Item "skills\sh-yb-policy-monitor\scripts\fetch_policies.py" "skills\sh-yb-policy-monitor\v1\scripts\fetch_policies.py"
```

- [ ] **步骤 4：验证所有归档**

```powershell
Get-ChildItem -Recurse skills\*\v1 | Select-Object FullName
```

预期输出：3 个技能 v1 目录中共列出 7 个文件。

- [ ] **步骤 5：提交**

```powershell
git add skills/tcm-treatment-plan/v1/ skills/tcm-treatment-review/v1/ skills/sh-yb-policy-monitor/v1/
git commit -m "feat: archive existing skills as v1 before KB refactoring"
```

---

## 任务 8：创建 knowledge-base-update 技能（v1）

一个统一三种数据摄取路径的新技能：手动文档、在线政策获取和手动规则。

**文件：**
- 创建：`skills/knowledge-base-update/v1/SKILL.md`
- 创建：`skills/knowledge-base-update/SKILL.md`

- [ ] **步骤 1：创建目录结构**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
mkdir -p skills\knowledge-base-update\v1
```

- [ ] **步骤 2：编写技能文件**

创建 `skills/knowledge-base-update/v1/SKILL.md`：

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

- [ ] **步骤 3：复制到根目录 SKILL.md**

```powershell
Copy-Item "skills\knowledge-base-update\v1\SKILL.md" "skills\knowledge-base-update\SKILL.md"
```

- [ ] **步骤 4：验证文件内容**

```powershell
Get-ChildItem -Recurse skills\knowledge-base-update | Select-Object FullName
```

预期输出：
```
skills\knowledge-base-update\v1\SKILL.md
skills\knowledge-base-update\SKILL.md
```

- [ ] **步骤 5：提交**

```powershell
git add skills/knowledge-base-update/
git commit -m "feat: add knowledge-base-update skill (v1) with 3 ingestion modes"
```

---

## 任务 9：将 tcm-treatment-plan 重构为 v2（知识库驱动）

将硬编码的价格表和规则替换为通过 MCP 查询知识库的指令。

**文件：**
- 创建：`skills/tcm-treatment-plan/v2/SKILL.md`
- 创建：`skills/tcm-treatment-plan/v2/方案参考.md`
- 修改：`skills/tcm-treatment-plan/SKILL.md`（用 v2 覆盖）

- [ ] **步骤 1：创建 v2 目录**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
mkdir -p skills\tcm-treatment-plan\v2
```

- [ ] **步骤 2：编写 v2 SKILL.md**

创建 `skills/tcm-treatment-plan/v2/SKILL.md`：

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

- [ ] **步骤 3：将 方案参考.md 复制到 v2**

参考文档为技能专属内容，保持原样：

```powershell
Copy-Item "skills\tcm-treatment-plan\方案参考.md" "skills\tcm-treatment-plan\v2\方案参考.md"
```

- [ ] **步骤 4：更新根目录 SKILL.md 指向 v2**

```powershell
Copy-Item "skills\tcm-treatment-plan\v2\SKILL.md" "skills\tcm-treatment-plan\SKILL.md" -Force
```

- [ ] **步骤 5：验证文件结构**

```powershell
Get-ChildItem -Recurse skills\tcm-treatment-plan | Select-Object FullName
```

预期输出：
```
skills\tcm-treatment-plan\v1\SKILL.md
skills\tcm-treatment-plan\v1\方案参考.md
skills\tcm-treatment-plan\v2\SKILL.md
skills\tcm-treatment-plan\v2\方案参考.md
skills\tcm-treatment-plan\SKILL.md          ← v2 的副本
skills\tcm-treatment-plan\方案参考.md        ← 原始版本（未更改）
```

- [ ] **步骤 6：提交**

```powershell
git add skills/tcm-treatment-plan/
git commit -m "feat: refactor tcm-treatment-plan to v2 with KB-powered pricing queries"
```

---

## 任务 10：将 tcm-treatment-review 重构为 v2（知识库驱动 + 流水线）

> **交叉引用：** `tcm-treatment-review` 的完整 v2 SKILL.md 定义在
> **审查流水线计划**（`docs/superpowers/plans/2026-04-07-review-pipeline.md`，任务 5）中。
> 该计划创建并发流水线（每张图片一个子代理、多表单检测、SQLite 存储）
> **并**集成知识库驱动的价格查询。**请执行流水线计划的任务 1-5，而非以下步骤。**
>
> 本任务仅处理 v1 归档（已在任务 7 中完成）和 v2 目录设置。

v2 技能结合了两个特性：
1. **知识库集成** — 通过 MCP 查询价格，替代硬编码的 `standards.md`
2. **并发流水线** — 每张图片一个子代理、多表单检测、SQLite 结果存储

**文件：**
- 创建：`skills/tcm-treatment-review/v2/SKILL.md`（来自流水线计划任务 5）
- 创建：`skills/tcm-treatment-review/v2/examples.md`
- 修改：`skills/tcm-treatment-review/SKILL.md`（用 v2 覆盖）

- [ ] **步骤 1：创建 v2 目录**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
mkdir -p skills\tcm-treatment-review\v2
```

- [ ] **步骤 2：执行流水线计划任务 1-5**

按照 `docs/superpowers/plans/2026-04-07-review-pipeline.md` 的任务 1 至任务 5 执行。这将创建：
- `.gitignore`（任务 1）
- `tests/test_review_db.py`（任务 2）
- `scripts/review_db.py`（任务 3）
- CLI 验证（任务 4）
- `skills/tcm-treatment-review/SKILL.md` — 包含流水线和知识库功能的统一 v2 版本（任务 5）

- [ ] **步骤 3：将流水线 SKILL.md 复制到 v2 文件夹**

```powershell
Copy-Item "skills\tcm-treatment-review\SKILL.md" "skills\tcm-treatment-review\v2\SKILL.md"
```

- [ ] **步骤 4：将 examples.md 复制到 v2**

示例文件为技能专属内容，保持原样：

```powershell
Copy-Item "skills\tcm-treatment-review\examples.md" "skills\tcm-treatment-review\v2\examples.md"
```

- [ ] **步骤 5：验证文件结构**

```powershell
Get-ChildItem -Recurse skills\tcm-treatment-review | Select-Object FullName
```

预期输出：
```
skills\tcm-treatment-review\v1\SKILL.md
skills\tcm-treatment-review\v1\standards.md
skills\tcm-treatment-review\v1\examples.md
skills\tcm-treatment-review\v2\SKILL.md          ← 流水线 + 知识库版本
skills\tcm-treatment-review\v2\examples.md
skills\tcm-treatment-review\SKILL.md             ← v2 的副本（流水线 + 知识库）
skills\tcm-treatment-review\examples.md          ← 原始版本（未更改）
skills\tcm-treatment-review\standards.md         ← 原始版本（保留供参考，v2 改用知识库）
```

- [ ] **步骤 6：提交**

```powershell
git add skills/tcm-treatment-review/
git commit -m "feat: refactor tcm-treatment-review to v2 with KB pricing + concurrent pipeline"
```

---

## 任务 11：将 sh-yb-policy-monitor 重构为 v2（知识库集成）

增强政策监控功能，在获取新政策后自动触发知识库更新。

**文件：**
- 创建：`skills/sh-yb-policy-monitor/v2/SKILL.md`
- 创建：`skills/sh-yb-policy-monitor/v2/scripts/fetch_policies.py`
- 修改：`skills/sh-yb-policy-monitor/SKILL.md`（用 v2 覆盖）

- [ ] **步骤 1：创建 v2 目录**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
mkdir -p skills\sh-yb-policy-monitor\v2\scripts
```

- [ ] **步骤 2：编写 v2 SKILL.md**

创建 `skills/sh-yb-policy-monitor/v2/SKILL.md`：

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

- [ ] **步骤 3：将 fetch_policies.py 复制到 v2**

脚本本身无需更改 — 知识库更新步骤由技能指令处理，而非脚本：

```powershell
Copy-Item "skills\sh-yb-policy-monitor\scripts\fetch_policies.py" "skills\sh-yb-policy-monitor\v2\scripts\fetch_policies.py"
```

- [ ] **步骤 4：将根目录 SKILL.md 更新为 v2**

```powershell
Copy-Item "skills\sh-yb-policy-monitor\v2\SKILL.md" "skills\sh-yb-policy-monitor\SKILL.md" -Force
```

- [ ] **步骤 5：验证文件结构**

```powershell
Get-ChildItem -Recurse skills\sh-yb-policy-monitor | Select-Object FullName
```

预期输出：
```
skills\sh-yb-policy-monitor\v1\SKILL.md
skills\sh-yb-policy-monitor\v1\scripts\fetch_policies.py
skills\sh-yb-policy-monitor\v2\SKILL.md
skills\sh-yb-policy-monitor\v2\scripts\fetch_policies.py
skills\sh-yb-policy-monitor\SKILL.md          ← v2 的副本
skills\sh-yb-policy-monitor\scripts\fetch_policies.py  ← 原始版本
```

- [ ] **步骤 6：提交**

```powershell
git add skills/sh-yb-policy-monitor/
git commit -m "feat: refactor sh-yb-policy-monitor to v2 with automatic KB update after fetch"
```

---

## 任务 12：测试 knowledge-base-update 技能 — docs 模式

验证 docs 数据摄取模式的端到端工作流程。

**文件：** 无（仅测试）

- [ ] **步骤 1：确保 MCP 服务正在运行**

```powershell
qmd mcp --http --daemon
```

- [ ] **步骤 2：手动测试 docs 模式**

在 Cursor 代理聊天中输入："更新知识库，扫描新文档"

预期行为：
1. 代理识别 `knowledge-base-update` 技能
2. 将 `docs/医院材料学习/` 与清单进行对比
3. 报告哪些文件是新增或已更改的
4. 对任何新文件执行索引
5. 报告完成情况

- [ ] **步骤 3：验证搜索查询返回更新后的结果**

在同一聊天中输入："搜索知识库：推拿按部位收费规则"

预期输出：返回引用推拿定价文档的结果。

---

## 任务 13：测试 tcm-treatment-plan v2

验证知识库驱动的治疗方案技能是否正常工作。

**文件：** 无（仅测试）

- [ ] **步骤 1：确保 MCP 服务正在运行**

```powershell
qmd mcp --http --daemon
```

- [ ] **步骤 2：使用示例患者案例进行测试**

在 Cursor 代理聊天中输入：

"请根据以下患者信息制定治疗方案：男性，45岁，75kg，主诉颈部酸痛3个月，伴肩部僵硬，久坐办公。"

预期行为：
1. 代理使用 `tcm-treatment-plan` v2 技能
2. 代理通过 MCP 查询价格数据（输出中应能看到 MCP 工具调用）
3. 代理生成包含正确价格的多阶段治疗方案
4. 价格与知识库数据一致

- [ ] **步骤 3：验证价格准确性**

将生成方案的价格与 `skills/tcm-treatment-review/v1/standards.md`（归档的基准数据）进行交叉核对：
- 常规针法应为 50元
- 颈部推拿应为 36元（一级）
- 脊柱推拿应为 70元

---

## 任务 14：测试 tcm-treatment-review v2

验证知识库驱动的审查技能及并发流水线是否正常工作。

> **注意：** 如需完整的流水线测试（批量图片、多表单检测、SQLite 存储），
> 还需运行流水线计划（`docs/superpowers/plans/2026-04-07-review-pipeline.md`）中的任务 6-8。

**文件：** 无（仅测试）

- [ ] **步骤 1：确保 MCP 服务正在运行**

```powershell
qmd mcp --http --daemon
```

- [ ] **步骤 2：测试带知识库查询的单图模式**

"请审查以下治疗信息：患者张三，男，50岁，诊断腰痹（气滞血瘀证），治疗项目：常规针法50元、特殊针具针法60元、腰部疾病推拿80元。"

预期行为：
1. 代理使用 `tcm-treatment-review` v2 技能（单图模式）
2. 代理通过 MCP 查询价格验证（输出中应能看到 MCP 工具调用）
3. 代理正确识别针法叠加违规（常规针法 + 特殊针具针法互斥）
4. 代理输出包含数据来源标注的七维审查表

---

## 任务 15：测试降级行为（MCP 停止运行时）

验证当知识库不可用时，技能能否优雅降级。

**文件：** 无（仅测试）

- [ ] **步骤 1：停止 MCP 服务**

```powershell
qmd mcp stop
```

- [ ] **步骤 2：在无 MCP 情况下测试 tcm-treatment-plan v2**

在 Cursor 代理聊天中请求制定一个治疗方案。

预期输出：技能生成方案但包含警告信息："⚠️ 知识库未连接，价格数据可能非最新，请人工核实。"

- [ ] **步骤 3：在无 MCP 情况下测试 tcm-treatment-review v2**

在 Cursor 代理聊天中请求审查一份治疗单。

预期输出：技能完成审查，但维度 5（收费合规性）显示："⚠️ 知识库未连接，无法核实最新价格"

- [ ] **步骤 4：重启 MCP 服务**

```powershell
qmd mcp --http --daemon
```

---

## 任务 16：测试增量索引

验证向知识库添加新文档是否能正确工作。

**文件：** 无（仅测试）

- [ ] **步骤 1：创建测试文档**

在 `docs/knowledge-base/.manual-rules/` 中创建一个测试 Markdown 文件：

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

- [ ] **步骤 2：索引新文件**

```powershell
qmd index "docs\knowledge-base\.manual-rules"
```

- [ ] **步骤 3：验证新内容可被搜索**

```powershell
qmd search "增量索引测试"
```

预期输出：测试文档出现在搜索结果中。

- [ ] **步骤 4：清理测试文件**

```powershell
Remove-Item "docs\knowledge-base\.manual-rules\*增量索引测试*"
```

- [ ] **步骤 5：最终提交**

```powershell
git add -A
git commit -m "chore: complete KB implementation — all tasks verified"
```
