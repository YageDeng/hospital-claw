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

