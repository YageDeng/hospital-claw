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

