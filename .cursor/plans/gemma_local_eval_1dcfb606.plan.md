---
name: gemma 本地评估
overview: 制定一份分阶段评估计划，在 macOS 上部署本地 Gemma 多模态模型，将 OpenClaw 面向模型的调用重定向到该 localhost 端点，并结合现有 skill E2E harness 与 Gemma 驱动的 probe driver 对仓库内 skills 做端到端验证。
todos:
  - id: discover-openclaw-config
    content: 定位并记录 Mac 主机上 OpenClaw 实际使用的模型提供方和 base URL 配置路径，并明确 localhost Gemma 的调用契约。
    status: pending
  - id: plan-gemma-macos-serve
    content: 基于 OpenAI 兼容 localhost API 的假设，编写 macOS 上 Gemma 的部署运行手册，并包含 smoke check 与回滚说明。
    status: pending
  - id: plan-openclaw-redirect
    content: 扩展部署与模板计划，使 OpenClaw 运行时产物能够表达本地 Gemma 端点设置，同时不自动改写线上运行配置。
    status: pending
  - id: plan-gemma-e2e-driver
    content: 设计一个 Gemma 驱动的 skill E2E driver，复用 SKILL_E2E_AGENT_DRIVER、probe payload 以及 evals/evals.json 中的期望。
    status: pending
  - id: plan-scenario-and-test-coverage
    content: 明确哪些 harness 场景与测试需要新增或更新，以覆盖 Gemma probe 和跨 skill 协作评估。
    status: pending
  - id: plan-final-reporting
    content: 定义产物目录结构和带日期的 Markdown 报告格式，用于记录部署结果、各 skill 结论以及模型短板。
    status: pending
isProject: false
---

# 本地 Gemma OpenClaw 评估计划

**目标：** 在 Mac 主机上部署本地 Gemma 多模态模型，将 OpenClaw 运行时指向该 localhost 模型端点，并产出可重复验证的证据，说明仓库内各项 skill 在 Gemma 驱动下哪些可以正确执行、哪些仍然失败。

**工作假设：**
- 主要目标环境是 Mac 主机上的 `OpenClaw`。
- Gemma 通过兼容 OpenAI 的 localhost API 暴露，默认服务方案假设为 `Ollama`。
- 计划文件继续放在现有项目的 `.cursor/plans` 目录下。

## 当前可复用基础
- 主机部署引导已经存在于 [config/agent_deploy.macos.local.json](config/agent_deploy.macos.local.json) 和 [scripts/deploy_agent_skills.py](scripts/deploy_agent_skills.py) 中。它已经能够准备 macOS 上的 skill/runtime 目录结构，并生成 `agent-runtime-config.template.json`，但目前还没有承载 LLM 端点或模型设置。
- Skill 验证能力已经存在于 [scripts/run_skill_e2e.py](scripts/run_skill_e2e.py)、[scripts/skill_e2e_matrix.py](scripts/skill_e2e_matrix.py) 和 [scripts/skill_e2e_probes.py](scripts/skill_e2e_probes.py) 中。最清晰的扩展点是由 `SKILL_E2E_ENABLE_PROBES` 和 `SKILL_E2E_AGENT_DRIVER` 驱动的外部 probe driver 契约。
- 范围边界已经在 [docs/superpowers/specs/2026-04-11-agent-skill-deploy.md](docs/superpowers/specs/2026-04-11-agent-skill-deploy.md) 和 [docs/superpowers/specs/2026-04-11-local-skill-e2e-harness.md](docs/superpowers/specs/2026-04-11-local-skill-e2e-harness.md) 中说明：本地 harness 覆盖并不能替代最终的 Mac/OpenClaw 主机验证。
- 跨 skill 的评估提示已经存在于 [evals/evals.json](evals/evals.json) 中，但目前还没有接入可执行的 E2E harness。

## 推荐方案
建议采用分阶段计划，而不是一次性同时解决部署、主机重定向和语义级 skill 评估。

1. **阶段 1：让 Mac 主机能够调用 Gemma**
   - 定义清晰的本地服务契约：`localhost` base URL、model id、超时预算、多模态能力预期，以及图片/文件 payload 的约束。
   - 扩展部署与配置生成路径，让 Mac/OpenClaw 模板能够携带 Gemma 相关运行时元数据，但不要自动改写真实的 OpenClaw 配置。
   - 先保持主机侧接线方式为“可由操作者审阅后手动应用”，与当前偏保守的部署风格保持一致。

2. **阶段 2：增加 Gemma 驱动的 skill 评估 driver**
   - 复用 [scripts/skill_e2e_probes.py](scripts/skill_e2e_probes.py) 中的 probe 机制，而不是另起一套评估框架。
   - 新增一个 driver，读取现有 probe payload 和 [evals/evals.json](evals/evals.json)，调用本地 Gemma 端点，并基于明确的 rubric 判断 pass/fail。
   - 保持确定性的非 LLM 场景不变，只在确实需要语义判断的地方叠加 Gemma 检查。

3. **阶段 3：产出主机级验证证据**
   - 在 macOS 上运行部署流程，将生成的模板合并进真实 OpenClaw 运行时，并验证同一个本地 Gemma 端点确实可以响应 OpenClaw 请求。
   - 通过仓库内 harness 执行选定 skills，再把最终结果、质量缺口和暂不支持的情况记录到带日期的 Markdown 报告中。

## 文件映射
- 修改 [config/agent_deploy.macos.local.json](config/agent_deploy.macos.local.json)：如果项目决定将本地模型端点信息持久化到配置中，就在这里加入默认占位字段。
- 修改 [scripts/deploy_agent_skills.py](scripts/deploy_agent_skills.py)：扩展运行时模板输出，让操作者能在生成结果中看到 OpenClaw 预期使用的 Gemma/OpenAI 兼容主机设置。
- 修改 [docs/superpowers/specs/2026-04-11-agent-skill-deploy.md](docs/superpowers/specs/2026-04-11-agent-skill-deploy.md)：补充 Mac 上 Gemma 服务的前置要求，以及 OpenClaw 配置手动合并步骤。
- 仅在 probe payload 契约确实需要结构化 rubric 字段时修改 [scripts/skill_e2e_probes.py](scripts/skill_e2e_probes.py)；否则保持该契约稳定，并将逻辑放到独立 driver 中。
- 修改 [scripts/skill_e2e_matrix.py](scripts/skill_e2e_matrix.py)：注册需要升格为一等 harness 场景的新增 Gemma probe。
- 新增一个专用 driver 脚本，位置大概率靠近 [scripts/run_skill_e2e.py](scripts/run_skill_e2e.py)，用于把 probe payload 与 `evals/evals.json` 期望转成 Gemma 调用和结构化 pass/fail 结果。
- 在 [tests/test_run_skill_e2e.py](tests/test_run_skill_e2e.py)、[tests/test_skill_e2e_matrix.py](tests/test_skill_e2e_matrix.py) 和 [tests/test_skill_e2e_probes.py](tests/test_skill_e2e_probes.py) 附近新增聚焦测试，覆盖新的 driver 契约与场景注册。
- 在实时验证完成后，于现有 results/docs 目录体系下新增一份带日期的评估报告。

## 交付阶段
### 阶段 A：基线与契约摸底
- 确认 Mac 主机上的真实 OpenClaw 运行时当前把模型提供方和 base URL 配置存放在哪里，因为本仓库目前只负责生成模板。
- 明确 Gemma 为满足 OpenClaw 所需的最小契约：聊天接口形态、鉴权预期、流式或非流式模式、图像输入支持方式以及失败时行为。
- 将首轮评估范围固定在当前 harness 已覆盖的 repo-owned skills：治疗审核、治疗方案、上海医保政策监控、知识库更新和公众号每日监控。

### 阶段 B：Mac 上 Gemma 部署方案
- 在 macOS 上按选定的 OpenAI 兼容服务路径安装并 smoke-test 本地 Gemma 服务。
- 记录操作者需要执行的步骤，包括模型下载、启动命令、健康检查以及一个小型多模态探测用例。
- 如果本地模型不可用，定义清晰的回滚与降级行为，避免 OpenClaw 验证过程在不知情的情况下落回远程模型。

### 阶段 C：OpenClaw 重定向方案
- 扩展模板生成能力，让部署产物中明确展示目标本地模型端点和 model id。
- 与当前 `agent-runtime-config.template.json` 工作流保持一致，最终合并进真实 OpenClaw 运行时的步骤仍然保持手动且显式。
- 增加一份简短的验证清单，用来证明 OpenClaw 实际命中了 `localhost`，而不是云端端点。

### 阶段 D：Gemma 驱动的 Skill 评估方案
- 复用 `SKILL_E2E_ENABLE_PROBES=1` 和 `SKILL_E2E_AGENT_DRIVER` 来驱动 Gemma 支持的语义检查。
- 将 [evals/evals.json](evals/evals.json) 接入为可执行测试用例，使跨 skill 协作预期能够自动检查，而不只是人工审阅。
- 保持现有 harness 里的确定性检查作为前置门禁，只有在本地前置条件通过后才运行 Gemma probe。

### 阶段 E：证据与报告
- 将原始 probe payload、模型输出以及各 skill 的判定结果保存到现有已忽略的 `data/skill_e2e/` 产物结构下。
- 生成一份带日期的 Markdown 报告，汇总部署状态、OpenClaw 重定向状态、各 skill 的 pass/fail、显著质量问题，以及如幻觉、工具路由错误或多模态理解较弱等缺口。
- 将仓库内本地 harness 证据与最终 Mac/OpenClaw 主机证据分开呈现，确保报告清楚说明每一部分是在什么环境下验证的。

## 需要重点控制的风险
- 当前仓库并不直接拥有 OpenClaw 的真实运行配置，因此主机侧配置摸底很可能成为前置阻塞项。
- `Ollama` 的兼容性仍可能需要对 prompt 或 payload 做适配，尤其是当 OpenClaw 期望的 OpenAI schema 比本地服务支持得更严格时。
- 当前 probe 契约以退出码为主；如果新的 driver 不承担足够严格的语义评分职责，评估深度会依然偏浅。
- 一些 skills 本身依赖实时外部资源，因此即使接入 Gemma 之后，仍可能出现 `SKIP` 或部分通过；最终报告需要清楚区分基础设施跳过和模型质量失败。

## 完成定义
- 已有一份可执行的 Mac 运行手册，用于启动本地 Gemma 并验证其 localhost API。
- OpenClaw 可以通过一条明确且经过审阅的配置路径指向本地 Gemma 端点。
- 仓库内 harness 可以通过现有 probe 机制运行 Gemma 驱动的语义探测。
- 已生成一份带日期的报告，按 skill 记录验证结果、产物和后续需要跟进的具体短板。
