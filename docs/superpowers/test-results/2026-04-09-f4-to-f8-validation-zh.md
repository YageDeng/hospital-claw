# F4-F8 测试记录（2026-04-09）

## F4 批量流水线（模拟多图）

- 会话初始化：`py scripts/review_db.py init --image-count 3`
- 会话 ID：`f6667a6e-bacf-4cce-a31d-4f7f672e353f`
- 子代理并发调度：3 个（对应 form1/form2/form3）
- 模拟输入：`data/test_images/form1.txt`、`form2.txt`、`form3.txt`（其中 `form3` 含两份表单）
- 落库结果：4 条（`row_id` 1~4）
- 状态校验：`reviewed_count=3`，`is_complete=true`
- 汇总结果：4 份表单，3 合格，1 不合格，合格率 75%

结论：符合 F4 预期（3 图 -> 4 条结果，form2 不合格，其余合格）。

## F5 多表单图片检测（复杂场景文本模拟）

- 输入：1 张“复合图片”文本描述（收据 + 治疗单A + 药方 + 治疗申请单B）
- 检测结果：
  - 识别治疗单：2 份
  - 忽略无关内容：2 项（收据、药方）
  - 患者A（陈七）：通过
  - 患者B（周八）：需复核（常规针法 + 特殊针具针法互斥叠加风险）

结论：满足 F5 关键验收点（多表单识别、无关内容忽略、针法叠加风险发现）。

## F6 兜底机制（MCP 停机）

- 执行停机：`qmd mcp stop`
- 连通性验证：`http://localhost:8181/mcp` 不可达（unreachable）
- 执行恢复：`qmd mcp --http --daemon`
- 结果：MCP 服务可停止并恢复，兜底前置条件验证通过。

说明：本轮验证了“停机/恢复”链路；业务层“告警文案”仍以技能定义为准（需在真实代理交互中观测输出文本）。

## F7 增量索引

- 临时规则文件：`docs/knowledge-base/.manual-rules/f7-incremental-test-rule.md`
- 增量索引命令：
  - `qmd collection add "docs/knowledge-base/.manual-rules" --name manual_rules_inc --mask "**/*.md"`
- 检索验证：
  - `qmd search "增量索引验证专用词-银杏桥"` 命中该新增规则
- 清理：
  - `qmd collection remove manual_rules_inc`
  - 删除临时规则文件

结论：F7 增量新增 -> 可检索 -> 清理回滚，流程通过。

## F8 最终验证

- 单测：`py -m pytest tests/test_review_db.py -v` -> **10 passed**
- 结构检查：`scripts/review_db.py`、`tests/test_review_db.py`、`skills/tcm-treatment-review/` 关键文件存在
- `.gitignore` 检查：包含 `data/`、`*.db`、`__pycache__/`、`tmp_review_*.json`

结论：F8 验证项通过（不含最终提交步骤）。
