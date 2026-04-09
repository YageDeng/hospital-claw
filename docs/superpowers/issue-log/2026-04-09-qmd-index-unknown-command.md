## 背景

todo：`docs/superpowers/todos/2026-04-07-knowledge-base-and-review-pipeline-zh.md`

当前执行到 **阶段 B2：索引全部 26 份文档**，todo 指令为：

- `qmd index docs/医院材料学习/`
- `qmd index docs/knowledge-base/.staging/`

## 问题描述

在本机运行 `qmd index` 失败，报错如下：

```
Unknown command: index
Run 'qmd --help' for usage.
```

因此 B2 的索引步骤无法继续。

## 已验证的环境信息

- Node.js 可用：`node --version` → `v24.14.1`
- npm 可用：`npm --version` → `11.11.0`
- `qmd` 可用：`qmd --version` → `qmd 1.0.5`
- `mineru-document-explorer` 已全局安装：`npm list -g mineru-document-explorer --depth=0` → `mineru-document-explorer@1.0.5`

## 已尝试的命令与结果

1) 创建目录结构（成功）：

- `docs/knowledge-base/`
- `docs/knowledge-base/wiki/`
- `docs/knowledge-base/index/`
- `docs/knowledge-base/.manual-rules/`

2) 执行索引（失败）：

```
qmd index "docs/医院材料学习"
qmd index "docs/knowledge-base/.staging"
```

输出：

```
Unknown command: index
Run 'qmd --help' for usage.
```

## 进一步排查结果（新增）

- 已确认：`qmd` 1.0.5 不包含 `index` 子命令，需改用 `qmd collection add` + `qmd query/search/embed` 流程。
- `collection add` 的文件匹配参数是 `--mask`（不是 `--pattern`）。
- `docs/knowledge-base/.staging` 的 `**/*.md` 索引可用（可列出 8 个文件）。
- `docs/医院材料学习` 的 `pdf/docx/pptx` 索引反复失败（Files=0）。
- 即使改用英文目录 + 英文文件名副本，`qmd collection add --mask "**/*.pdf"` 仍返回 0。
- 直接调用 MinerU 自带提取器（`extract_pdf_pages.py`）可正常抽取 PDF 文本，说明文件本身与 Python 依赖不是根因。
- 结论：当前版本在本机环境下对二进制文档的 `collection add` 索引链路不可用（根因待上游修复），但 Markdown 索引链路可用。

## 最终解决方案（已执行）

- 新增脚本：`scripts/binary_docs_to_markdown.py`
- 将 `docs/医院材料学习/` 中的 23 个 `pdf/docx/pptx` 全量转换为 Markdown，输出至：
  - `docs/knowledge-base/.staging-binary-md/`
- 使用可用的 Markdown 索引链路：
  - `qmd collection add "docs/knowledge-base/.staging-binary-md" --name yycailiao_md --mask "**/*.md"`
  - `qmd collection add "docs/knowledge-base/.staging" --name xlsxmd --mask "**/*.md"`
- 验证检索：
  - `qmd search "针法价格"` 命中 `yycailiao_md` / `xlsxmd` 内容
  - `qmd search "推拿 一级"` 命中 `yycailiao_md` / 规则文档内容

## 解决结果

- 当前：**已解决（采用转换为 Markdown 后索引的规避方案）**，B2 的“文档可搜索”目标达成。

## B3 追加记录（Wiki 生成）

- `qmd wiki ingest` 在当前版本中不是“自动全量生成 wiki”，而是“对单个 source 做分析建议”。
- 传本地绝对路径（如 `D:\...\src-001.md`）会报 `Source document not found`。
- 可行方式：先把 source 目录加入 collection，再用 collection 路径调用：
  - `qmd wiki ingest "wiki_ingest_src/src-001.md" --wiki kb_wiki`
- 要真正生成页面，需执行 `qmd wiki write` 写入页面。
- 本次已通过批量 `qmd wiki write` 生成：
  - `docs/knowledge-base/wiki/index.md`
  - `docs/knowledge-base/wiki/sources/src-001.md` ... `src-030.md`
  - 5 个分类 `index.md`
- `qmd wiki index kb_wiki` 显示 `Auto-generated index of 36 pages`。

## F 阶段追加记录（query 首次运行）

- 在 F2 验证中执行 `qmd query` 时，CLI 提示首次需下载 3 个模型（约 300MB + 1.1GB + 640MB）。
- 当前环境下该过程长时间停留在 `Gathering information`，未在合理时间内返回结果，已中止该进程。
- 临时处理：改用 `qmd search` 完成价格与规则关键词检索验证，确保知识库基础检索链路可用。
- 建议：后续在网络稳定且允许长时下载时，单独完成 `qmd query` 首次模型拉取，再复测 F2 的 MCP/query 全链路。

## F3 追加记录（单图测试：文本替代）

- 按计划的“无图片替代方案”执行文本用例，完成单图等价验证。
- 已通过 `qmd search` 检索到关键依据：
  - 常规针法 50；
  - 特殊针具针法 60；
  - 腰部疾病推拿 80；
  - 针法互斥规则。
- 本轮未出现新的命令级错误或环境阻塞问题。
- 输出记录文件：`docs/superpowers/test-results/2026-04-09-f3-single-image-text-fallback-zh.md`。

## F4-F8 追加记录

- F4（批量流水线）已用计划提供的“多图文本模拟”跑通：3 图 -> 4 条结果，SQLite 会话完成。
- F5（多表单检测）已按复杂场景文本完成：识别 2 张治疗单，忽略 2 项无关内容，发现针法叠加风险。
- F6（MCP 停机）已验证：
  - `qmd mcp stop` 后 endpoint 不可达；
  - `qmd mcp --http --daemon` 可恢复服务。
- F7（增量索引）已验证新增规则可检索，并执行清理回滚。
- F8（最终验证）中 `pytest` 10 项全部通过。

### 本轮问题记录：PowerShell 链式命令兼容

- 现象：在当前环境中使用 `&&` 连接命令会报 `InvalidEndOfLine`。
- 尝试：将链式命令改为分号 `;` 顺序执行。
- 结果：命令执行恢复正常，后续流程不受影响。

