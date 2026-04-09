# 知识库 + 审核流水线 — 综合任务清单

**创建日期：** 2026-04-07
**适用对象：** 实习生入职 — 按顺序执行任务，完成后逐项勾选。

> **每项任务的完整细节请参阅原始计划文档：**
> - 知识库计划：`docs/superpowers/plans/2026-04-07-knowledge-base-implementation.md`
> - 流水线计划：`docs/superpowers/plans/2026-04-07-review-pipeline.md`
>
> 本清单提供执行顺序和简要说明。
> 如有疑问，请打开对应的计划文档查看完整任务描述。

---

## 阶段 A：环境搭建

- [ ] **A1. 安装 Node.js >= 22** *（知识库计划 → 任务 1）*
  - 通过 https://nodejs.org 或 `winget install OpenJS.NodeJS.LTS` 安装
  - 验证：`node --version` → v22+

- [ ] **A2. 安装 MinerU Document Explorer** *（知识库计划 → 任务 2）*
  - `npm install -g mineru-document-explorer`
  - `pip install pymupdf python-docx python-pptx openpyxl`
  - 验证：`qmd --version`

- [ ] **A3. 创建根目录 .gitignore** *（流水线计划 → 任务 1）*
  - 忽略 `data/`、`*.db`、`__pycache__/`、`tmp_review_*.json`
  - 提交

---

## 阶段 B：文档处理与知识库

- [ ] **B1. 编写 XLSX → Markdown 转换脚本** *（知识库计划 → 任务 3）*
  - 创建 `scripts/xlsx_to_markdown.py`
  - 对 3 个 Excel 文件执行转换 → `docs/knowledge-base/.staging/`
  - 提交

- [ ] **B2. 索引全部 26 份文档** *（知识库计划 → 任务 4）*
  - 创建 `docs/knowledge-base/` 目录结构（wiki/、index/、.manual-rules/）
  - 在本机 **不要使用** `qmd index`（`qmd 1.0.5` 不提供该子命令）
  - 运行 `python scripts/binary_docs_to_markdown.py` → `docs/knowledge-base/.staging-binary-md/`
  - 运行 `python scripts/xlsx_to_markdown.py` → `docs/knowledge-base/.staging/`
  - 使用 `qmd collection add` 刷新 `source_md` / `yycailiao_md` / `xlsxmd` 集合
  - 通过测试搜索验证："针法价格"、"推拿 一级"
  - 提交

- [ ] **B3. 生成 Wiki** *（知识库计划 → 任务 5）*
  - 创建 `docs/knowledge-base/wiki-seed.yml`，包含 5 个分类
  - 使用 collection-relative `qmd wiki ingest` + `qmd wiki write`（不要只运行裸 `qmd wiki ingest`）
  - 检查生成的页面，必要时重新整理
  - 提交

- [ ] **B4. 配置 MCP 服务器** *（知识库计划 → 任务 6）*
  - 创建 `.cursor/mcp.json` → `http://localhost:8181/mcp`
  - 启动守护进程：`qmd mcp --http --daemon`
  - 验证健康检查
  - 提交

---

## 阶段 C：审核流水线基础设施

- [ ] **C1. 为 review_db.py 编写失败测试** *（流水线计划 → 任务 2）*
  - 创建 `tests/test_review_db.py`（10 个测试）
  - 运行测试 → 全部失败（模块未找到）
  - 提交

- [ ] **C2. 实现 review_db.py** *（流水线计划 → 任务 3）*
  - 创建 `scripts/review_db.py`（SQLite 数据库 + CLI：init/save/status/summary/export）
  - 运行测试 → 全部 10 个通过
  - 提交

- [ ] **C3. 验证 review_db.py CLI** *（流水线计划 → 任务 4）*
  - 端到端测试 `init`、`save`、`status`、`summary` 命令
  - 清理测试文件

---

## 阶段 D：技能版本管理（归档 v1）

- [ ] **D1. 将现有 3 个技能全部归档为 v1** *（知识库计划 → 任务 7）*
  - 复制 `tcm-treatment-plan/` 文件 → `tcm-treatment-plan/v1/`
  - 复制 `tcm-treatment-review/` 文件 → `tcm-treatment-review/v1/`
  - 复制 `sh-yb-policy-monitor/` 文件 → `sh-yb-policy-monitor/v1/`
  - 验证 3 个技能共 7 个归档文件
  - 提交

---

## 阶段 E：创建与重构技能至 v2

- [ ] **E1. 创建 knowledge-base-update 技能（v1）** *（知识库计划 → 任务 8）*
  - 创建 `skills/knowledge-base-update/v1/SKILL.md`（3 种导入模式：docs/policy/rules）
  - 复制到根目录 `skills/knowledge-base-update/SKILL.md`
  - 提交

- [ ] **E2. 重构 tcm-treatment-plan 至 v2** *（知识库计划 → 任务 9）*
  - 创建 `skills/tcm-treatment-plan/v2/SKILL.md` — 用知识库查询替代硬编码定价
  - 复制 `方案参考.md` 至 v2/
  - 更新根目录 SKILL.md → v2
  - 提交

- [ ] **E3. 重写 tcm-treatment-review 至 v2（流水线 + 知识库）** *（流水线计划 → 任务 5 + 知识库计划 → 任务 10）*
  - 创建 `skills/tcm-treatment-review/v2/SKILL.md` — 并发流水线 + 知识库定价
  - 复制 `examples.md` 至 v2/
  - 更新根目录 SKILL.md → v2
  - **这是合并后的 v2：** 每个子代理处理一张图片的流水线 + MCP 定价 + SQLite 存储 + 静态价格兜底
  - 提交

- [ ] **E4. 重构 sh-yb-policy-monitor 至 v2** *（知识库计划 → 任务 11）*
  - 创建 `skills/sh-yb-policy-monitor/v2/SKILL.md` — 抓取后新增知识库更新触发
  - 复制 `scripts/fetch_policies.py` 至 v2/
  - 更新根目录 SKILL.md → v2
  - 提交

---

## 阶段 F：测试与验证

- [ ] **F1. 测试知识库更新 — docs 模式** *（知识库计划 → 任务 12）*
  - 向代理提问："更新知识库，扫描新文档"
  - 验证 manifest 刷新 + `qmd collection add` 工作流正常

- [ ] **F2. 测试 tcm-treatment-plan v2** *（知识库计划 → 任务 13）*
  - 要求代理生成方案：男性，45岁，75kg，颈部酸痛3个月
  - 验证出现知识库 search/query 调用 + 定价正确
  - 如 `query` 首次模型下载卡住，可接受退回 `search` / `wiki_read`，但需记录

- [ ] **F3. 测试 tcm-treatment-review v2 — 单张图片** *（流水线计划 → 任务 6）*
  - 提供 1 张图片（或文字描述）
  - 验证知识库定价查询 + 7 维度表格输出

- [ ] **F4. 测试 tcm-treatment-review v2 — 批量流水线** *（流水线计划 → 任务 7）*
  - 提供 3 张图片（其中 1 张包含 2 张叠放的治疗单）
  - 验证：3 个子代理被调度、SQLite 中有 4 条结果、汇总报告正确

- [ ] **F5. 测试多表单图片检测** *（流水线计划 → 任务 8）*
  - 提供 1 张包含 2 张治疗单 + 无关内容的图片
  - 验证：识别出 2 张治疗单、无关内容被忽略、针法叠加被发现

- [ ] **F6. 测试兜底机制 — MCP 停机** *（知识库计划 → 任务 15）*
  - 停止 MCP：`qmd mcp stop`
  - 测试治疗方案 → 出现警告
  - 测试治疗审核 → 使用静态价格，出现警告
  - 重启 MCP：`qmd mcp --http --daemon`

- [ ] **F7. 测试增量索引** *（知识库计划 → 任务 16）*
  - 向 `.manual-rules/` 添加一条测试规则
  - 索引 + 验证可搜索
  - 清理

- [ ] **F8. 最终验证** *（流水线计划 → 任务 9）*
  - 运行 `python -m pytest tests/test_review_db.py -v` → 全部通过
  - 验证完整文件结构
  - 最终提交

---

## 快速参考：最终文件结构

```
hospital-claw/
├── .cursor/mcp.json                           # MinerU MCP 配置
├── .gitignore                                 # 忽略运行时产物
│
├── scripts/
│   ├── xlsx_to_markdown.py                    # XLSX → MD 转换器
│   └── review_db.py                           # 审核流水线 SQLite 数据库 + CLI
│
├── tests/
│   └── test_review_db.py                      # review_db 的 10 个单元测试
│
├── docs/
│   ├── 医院材料学习/                            # 26 份源培训文档
│   └── knowledge-base/
│       ├── wiki/                              # 互链 Wiki（5 个分类）
│       ├── index/                             # MinerU 搜索索引
│       ├── .staging/                          # XLSX → MD 转换结果
│       ├── .manual-rules/                     # 手动添加的规则
│       ├── .manifest.json                     # 索引追踪清单
│       └── wiki-seed.yml                      # Wiki 分类种子文件
│
├── skills/
│   ├── tcm-treatment-plan/    (v1/, v2/, SKILL.md)
│   ├── tcm-treatment-review/  (v1/, v2/, SKILL.md, standards.md, examples.md)
│   ├── sh-yb-policy-monitor/  (v1/, v2/, SKILL.md, scripts/)
│   └── knowledge-base-update/ (v1/, v2/, SKILL.md)
│
├── data/
│   └── reviews.db                             # 运行时产物 — 审核流水线 SQLite
│
└── wechat-router/                             # 现有微信监控（无变更）
```

## 预估总耗时

| 阶段 | 任务数 | 预估时间 |
|------|--------|----------|
| A. 环境搭建 | 3 项任务 | 约 20 分钟 |
| B. 文档处理与知识库 | 4 项任务 | 约 60 分钟（含模型下载） |
| C. 审核流水线基础设施 | 3 项任务 | 约 30 分钟 |
| D. 归档 v1 | 1 项任务 | 约 5 分钟 |
| E. 技能重构 | 4 项任务 | 约 40 分钟 |
| F. 测试 | 8 项任务 | 约 50 分钟 |
| **合计** | **23 项任务** | **约 3.5 小时** |
