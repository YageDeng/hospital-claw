---
name: sh-yb-policy-monitor
version: v2
description: 当用户要求检查上海医保局最新动态、最新政策、公示公告，或抓取政策后同步共享知识库时使用。
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

- **主存储路径**：优先使用 `--save-dir` 或环境变量 `SH_YB_POLICY_SAVE_DIR`
- **默认回退路径**：部署根目录下的 `<KB_POLICY_ROOT>/`
- **知识库副本**：获取后自动复制到 `<KB_SOURCE_ROOT>/` 以便知识库索引
- **文件命名**：`{YYYY-MM-DD}_{栏目代号}_{标题简称}.md`

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

- 本技能只负责抓取与保存政策原文，不负责共享知识库的完整重建。
- 用户要求“同步到知识库 / 更新 manifest / 重建 wiki / 全量刷新”时，优先交给 `knowledge-base-update`。
- `tcm-treatment-plan` 或 `tcm-treatment-review` 如需最新政策，先执行本技能抓取，再交由 `knowledge-base-update` 刷新后再消费。

## 执行流程

### 方式一：Python 脚本（推荐）

```powershell
cd <repo-root>
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

## 获取后：与共享知识库协作

默认流程分两层：

1. **本技能负责抓取与落盘**：把新政策保存到 `SH_YB_POLICY_SAVE_DIR` 或 `<KB_POLICY_ROOT>/`
2. **`knowledge-base-update` 负责标准入库**：当用户要求同步知识库、刷新 manifest、重建 wiki、或统一处理多来源内容时，直接交给 `knowledge-base-update` 的 `policy` 模式

仅当当前会话必须立刻让新政策 Markdown 可搜索、且不准备切换到 `knowledge-base-update` 时，才执行最小同步：

```powershell
$policyDir = if ($env:SH_YB_POLICY_SAVE_DIR) { $env:SH_YB_POLICY_SAVE_DIR } else { "<KB_POLICY_ROOT>" }
$newFiles = Get-ChildItem (Join-Path $policyDir "*.md") | Where-Object { $_.LastWriteTime -gt (Get-Date).AddDays(-7) }
foreach ($f in $newFiles) {
    Copy-Item $f.FullName "<KB_SOURCE_ROOT>" -ErrorAction SilentlyContinue
}

qmd collection remove source_md 2>$null
qmd collection add "<KB_SOURCE_ROOT>" --name source_md --mask "**/*.md"
python scripts/update_kb_manifest.py
```

注意：

- 上面的最小同步只覆盖本次新增政策 Markdown
- 如需 wiki 重建、二进制转换、规则合并或全量一致性修复，仍由 `knowledge-base-update` 负责
- 如 MinerU 未安装、MCP 服务未运行，或 `qmd query` 首次运行卡在模型下载，跳过最小同步并说明需稍后运行 `knowledge-base-update`

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
本次共获取 {N} 篇新文件，已保存至 {策略文件目录（SH_YB_POLICY_SAVE_DIR 或 <KB_POLICY_ROOT>/）}

### 知识库更新状态
- ✅ 已将 {N} 个新文件纳入知识库检索层
- ℹ️ Wiki 页面按当前 CLI 能力决定是否重建
```

如所有栏目均无目标日期的新文章，回复：
> 已检查上海市医保局三个栏目（医保动态/最新政策/公示公告），{目标日期}无新发布内容。知识库无需更新。

