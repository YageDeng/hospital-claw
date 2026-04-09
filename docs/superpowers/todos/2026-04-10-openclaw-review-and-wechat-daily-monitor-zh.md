# OpenClaw 治疗单审核部署 + 公众号每日监测 — 综合任务清单

**创建日期：** 2026-04-10  
**适用方式：** 按顺序执行，完成后逐项勾选。

> 本清单合并了三个相关工作流：
> - 工作流 1：将 `tcm-treatment-review` 适配并部署到 mac mini 上的 OpenClaw 运行时（“小龙虾”），完成治疗单上传到审核结果返回的端到端验证。
> - 工作流 2：基于 `will-17173/wechat-article-to-markdown-skill` 的文章抓取方法，新建 `wechat-daily-monitor` skill，并把输出接入现有知识库刷新与索引流程。
> - 工作流 3：将仓库内所有现有 skill 部署到 mac mini 上的 OpenClaw 环境，并逐个完成端到端验证，而不是只验证 `tcm-treatment-review`。
>
> 该清单刻意写成“自包含”形式，因为第一阶段必须先摸清 mac mini 上 OpenClaw 的真实运行契约，再锁定具体改造方案。

---

## 阶段 A：确认目标运行时契约

- [ ] **A1. 梳理 mac mini 上的 OpenClaw 运行契约**
  - SSH 登录 mac mini，定位 OpenClaw 工作目录、服务入口、skill 加载路径、上传文件落盘路径，以及子代理/工作任务的调度机制。
  - 记录上传图片最终保存到哪里、结果如何回传到 UI、日志如何查看。
  - 将调研结论写入 `docs/superpowers/specs/2026-04-10-openclaw-review-integration-notes.md`。

- [ ] **A2. 审核当前治疗单 skill 与目标运行时的差异**
  - 检查 `skills/tcm-treatment-review/SKILL.md`、`skills/tcm-treatment-review/v2/SKILL.md`、`scripts/review_db.py`。
  - 输出差异清单，至少覆盖：
    - Cursor/Task 专属措辞与 OpenClaw 原生编排方式的差异
    - 仅适用于 Windows 的命令和路径
    - 临时 JSON 文件处理方式
    - SQLite 文件路径假设
    - 批量 fan-out / fan-in 行为

- [ ] **A3. 锁定迁移路径**
  - 如果当前 v2 skill 需要面向运行时的改造，则新建 `skills/tcm-treatment-review/v3/SKILL.md`。
  - 只有在 mac mini 流程验证通过后，才更新根目录 `skills/tcm-treatment-review/SKILL.md`。
  - 除非 Phase A 审核确认 CLI 契约必须修改，否则优先复用现有 `scripts/review_db.py`。

---

## 阶段 B：将 `tcm-treatment-review` 适配到 OpenClaw

- [ ] **B1. 将编排说明改为 OpenClaw 原生表达**
  - 将 Cursor/Task 相关描述替换为 Phase A 中确认的 OpenClaw worker/subagent 机制。
  - 保留“单图单 worker”规则，避免图片与结论再次错位。
  - 保留当前的单图快速路径，以及多图 + SQLite 聚合路径。

- [ ] **B2. 去除机器绑定假设**
  - 将硬编码的 Windows 路径改为仓库相对路径或环境变量路径。
  - skill 中若保留命令示例，应补齐 mac mini 需要的 macOS 写法。
  - 确认 `data/reviews.db` 与临时 JSON 清理在 Windows/macOS 两侧都成立。

- [ ] **B3. 判断 `review_db.py` 是否需要调整**
  - 如果 OpenClaw 能直接调用现有的 `init`、`save`、`status`、`summary`、`export` 命令，则脚本保持不变。
  - 只有在运行时需要改动路径处理、输出格式或 session 生命周期时才修改。
  - 如有修改，补充或更新 `tests/test_review_db.py` 中的聚焦测试。

- [ ] **B4. 产出可部署版本**
  - 如存在明显运行时适配改造，则创建 `skills/tcm-treatment-review/v3/SKILL.md`。
  - 保留当前 v2 的能力集：
    - 知识库价格查询
    - 静态价格兜底
    - 多表单识别
    - 批量审核结果写入 SQLite
  - 将根目录 `skills/tcm-treatment-review/SKILL.md` 指向已验证版本。

---

## 阶段 C：部署到 mac mini 并完成端到端验证

- [ ] **C1. 将所需文件部署到 OpenClaw 主机**
  - 部署经过验证的 `skills/tcm-treatment-review/` 文件。
  - 包含 `scripts/review_db.py` 及主机需要的辅助文档/配置。
  - 在执行验证命令前，先确认主机端 venv 和依赖状态。

- [ ] **C2. 验证上传 -> 审核 -> 返回结果的完整链路**
  - 跑 1 张图片的端到端上传测试。
  - 跑 3 张图片的批量测试，其中 1 张包含 2 份叠放治疗单。
  - 确认：
    - 上传文件进入了正确的运行时目录
    - OpenClaw 正确 fan-out 到多个 worker/subagent
    - SQLite 收到了预期数量的结果
    - 最终汇总结果能够正确回传到 UI

- [ ] **C3. 留存验证证据与运维说明**
  - 将截图、日志、结论写入 `docs/superpowers/test-results/2026-04-10-openclaw-review-validation.md`。
  - 记录通过/失败状态、已知缺口和回滚说明。

---

## 阶段 D：创建 `wechat-daily-monitor` skill

- [ ] **D1. 将文章抓取流水线纳入本仓库**
  - 复用 `will-17173/wechat-article-to-markdown-skill` 的方法：
    - 请求公众号文章 HTML
    - 修复懒加载图片地址
    - 将文章图片下载到本地
    - 将正文转换为 Markdown
    - 对输出结果做清洗/格式整理
  - 将仓库内脚本落地为 `scripts/wechat_article_pipeline.py`。
  - 依赖尽量保持最小；如果当前项目 venv 中没有 `requests`，则在执行阶段补充安装/说明。

- [ ] **D2. 锁定文章输出目录结构**
  - 将抓取结果保存到 `docs/医院材料学习/公众号每日监测/YYYY-MM-DD/<公众号名>/<NN_文章标题>/`。
  - 每篇文章至少保存：
    - 清洗后的 Markdown
    - 下载的图片资源
    - 如有需要用于排障的清洗后 HTML
    - 文章元数据（来源公众号、发布时间、命中关键词、优先级、本地路径）

- [ ] **D3. 定义文章链接来源**
  - 首选路径：利用 `wechat-router/wechat-decrypt/` 现有能力及其 MCP 能力，从目标公众号来源中发现最近的 `mp.weixin.qq.com` 链接。
  - 兜底路径：允许操作人手动输入一个或多个文章 URL。
  - 两种模式都要在 skill 契约中写清楚，避免运行时行为不确定。

- [ ] **D4. 创建新 skill 文件**
  - 新建 `skills/wechat-daily-monitor/v1/SKILL.md`。
  - 将验证后的版本复制到 `skills/wechat-daily-monitor/SKILL.md`。
  - 将 `docs/superpowers/specs/公众号每日监测.md` 中的优先级规则编码进去：
    - `P0`：立即告警
    - `P1`：当日汇总
    - `P2`：周报汇总
    - `P3/P4`：归档 / 过滤

- [ ] **D5. 定义运行输出**
  - 每次运行应至少产出：
    - 抓取后的文章 Markdown 目录
    - 结构化监测报告
    - `P0` 紧急告警
    - `P1` 日报摘要
    - `P2` 周报候选内容
    - `P3/P4` 的归档痕迹

---

## 阶段 E：更新知识库自动刷新与索引流程

- [ ] **E1. 更新知识库 skill 契约**
  - 修改 `skills/knowledge-base-update/SKILL.md` 和 `skills/knowledge-base-update/v2/SKILL.md`。
  - 明确说明：`docs/医院材料学习/公众号每日监测/` 下新增的原生 Markdown 属于 `source_md` 刷新范围。
  - 增加“同步公众号监测文章到知识库”相关触发语。

- [ ] **E2. 判断是否需要单独的 KB 模式**
  - 若文章落在 `docs/医院材料学习/` 之下，优先复用现有 `docs` 模式。
  - 只有在操作命令、报告形式或局部刷新路径需要区分时，才新增 `wechat` 模式。

- [ ] **E3. 验证 manifest 覆盖范围**
  - 确认 `scripts/update_kb_manifest.py` 的递归扫描已经覆盖新增文章目录。
  - 只有在当前输出路径未被覆盖时才修改脚本。

- [ ] **E4. 增加抓取后的自动索引**
  - 新 monitor skill 在保存文章 Markdown 后，必须自动触发知识库刷新。
  - 最低要求包括：

```powershell
python scripts/update_kb_manifest.py
qmd collection add "docs/医院材料学习" --name source_md --mask "**/*.md"
```

  - 如果最终流程还需要二进制文档转换或 wiki 刷新，优先复用现有 `knowledge-base-update` skill 的流程，不要重复造逻辑。

---

## 阶段 F：将所有 Skill 部署到 mac mini OpenClaw 主机

- [ ] **F1. 建立可部署 skill 清单**
  - 至少包含当前根目录正在使用的 skill：
    - `skills/tcm-treatment-review/SKILL.md`
    - `skills/tcm-treatment-plan/SKILL.md`
    - `skills/sh-yb-policy-monitor/SKILL.md`
    - `skills/knowledge-base-update/SKILL.md`
  - 在阶段 D 完成后，把 `skills/wechat-daily-monitor/SKILL.md` 一并加入部署清单。
  - 为每个 skill 列出主机侧必须存在的配套脚本、文档和数据目录。

- [ ] **F2. 一次性补齐共享运行时依赖**
  - 确保 mac mini 主机具备正确的仓库代码、Python venv、Python 依赖、Node/qmd 工具链，以及知识库目录。
  - 确认主机上具备整个 skill 集合会共用的脚本，包括：
    - `scripts/review_db.py`
    - `scripts/update_kb_manifest.py`
    - `scripts/xlsx_to_markdown.py`
    - `scripts/binary_docs_to_markdown.py`
    - `scripts/wechat_article_pipeline.py`
    - `skills/sh-yb-policy-monitor/scripts/fetch_policies.py`

- [ ] **F3. 部署全部 skill 包**
  - 将每个 skill 目录及其所需配套文件同步到 OpenClaw 主机。
  - 确认 OpenClaw 运行时能够在其 skill 加载路径中发现全部已部署 skill。
  - 只有在主机运行时实际能列出或加载成功后，才算部署完成。

- [ ] **F4. 对每个已部署 skill 做端到端验证**
  - `tcm-treatment-review`：验证单图路径和批量路径
  - `tcm-treatment-plan`：生成一个样例治疗方案，确认知识库价格或兜底逻辑正确
  - `sh-yb-policy-monitor`：抓取最新政策并确认本地输出、知识库复制/更新链路成立
  - `knowledge-base-update`：至少跑通一次 `docs` 流程和一次 `rules` 流程，并确认 manifest 与 collection 刷新
  - `wechat-daily-monitor`：先验证手动 URL 路径；如果主机具备可用的微信数据访问条件，再验证自动发现链接路径

- [ ] **F5. 留存完整主机验证证据**
  - 将证据写入 `docs/superpowers/test-results/2026-04-10-openclaw-all-skills-validation.md`。
  - 按 skill 记录通过、失败、跳过场景，以及主机特有注意事项和回滚说明。

---

## 阶段 G：验证矩阵

- [ ] **G1. 冒烟验证文章抓取流水线**
  - 运行：

```powershell
python scripts/wechat_article_pipeline.py "<mp.weixin.url>" --output-dir "docs/医院材料学习/公众号每日监测"
```

  - 验证标题提取、图片下载、Markdown 清洗、目录命名是否稳定。

- [ ] **G2. 验证优先级分类**
  - 使用应分别落入 `P0`、`P1`、`P2` 的样例文章。
  - 确认生成的告警/日报/周报符合 `docs/superpowers/specs/公众号每日监测.md` 中的规则。

- [ ] **G3. 验证知识库可检索性**
  - 至少导入 1 篇文章后刷新知识库。
  - 确认该文章能够通过现有 KB 的 search/query/wiki_read 流程被检索到。

- [ ] **G4. 验证两条操作路径**
  - 手动链接路径：操作人输入 URL -> skill 抓取文章 -> KB 刷新 -> 文章可搜索。
  - 自动发现路径：skill 从监测来源中发现新文章链接 -> 抓取并分类 -> KB 刷新 -> 产出监测摘要。

- [ ] **G5. 最终收口**
  - 更新清单勾选状态。
  - 记录剩余缺口与后续事项。
  - 选择实施方式：subagent-driven 或 inline execution。

---

## 候选变更文件

```text
hospital-claw/
├── docs/
│   ├── 医院材料学习/
│   │   └── 公众号每日监测/
│   │       └── YYYY-MM-DD/<公众号名>/<NN_文章标题>/
│   └── superpowers/
│       ├── specs/
│       │   └── 2026-04-10-openclaw-review-integration-notes.md
│       └── test-results/
│           ├── 2026-04-10-openclaw-review-validation.md
│           └── 2026-04-10-openclaw-all-skills-validation.md
├── scripts/
│   └── wechat_article_pipeline.py
└── skills/
    ├── knowledge-base-update/
    │   ├── SKILL.md
    │   └── v2/SKILL.md
    ├── tcm-treatment-review/
    │   ├── SKILL.md
    │   └── v3/SKILL.md
    └── wechat-daily-monitor/
        ├── SKILL.md
        └── v1/SKILL.md
```

## 建议执行顺序

1. 先完成阶段 A-C，先把 OpenClaw 运行契约和治疗单审核链路在主机上跑通。
2. 再执行阶段 D-E，锁定文章输出目录和知识库复用路径。
3. 只有在所需脚本、知识库资产和 skill 已全部到位后，再执行阶段 F。
4. 只有在阶段 G 的验证证据完成后，才算真正收尾。

## 预估投入

| 阶段 | 任务数 | 预估时间 |
|------|--------|----------|
| A. 运行时调研 | 3 项 | ~45-60 分钟 |
| B. 审核 skill 适配 | 4 项 | ~60-90 分钟 |
| C. 部署 + 端到端验证 | 3 项 | ~45-75 分钟 |
| D. 新建公众号监测 skill | 5 项 | ~90-120 分钟 |
| E. 知识库刷新/索引集成 | 4 项 | ~30-45 分钟 |
| F. 全量 skill 主机部署 + 验证 | 5 项 | ~60-90 分钟 |
| G. 验证矩阵 | 5 项 | ~45-60 分钟 |
| **合计** | **29 项** | **~6.5-9 小时** |
