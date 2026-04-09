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

