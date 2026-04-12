# Eval 1: Policy Fetch Then KB Update

## Prompt

请检查上海医保局最近 7 天有没有和中医收费、医保监管相关的新政策或公告。如果有，先抓取保存，再按标准流程同步到共享知识库。最后告诉我：抓到了什么、知识库是否刷新成功、你用的是共享路径文件还是默认回退路径。

## Expected Cooperation Chain

1. `sh-yb-policy-monitor` 负责抓取并保存政策原文。
2. `knowledge-base-update` 的 `policy` 模式负责标准入库。
3. 最终结果说明抓取结果、刷新状态和路径来源。

## Assertions

- 响应明确先执行 `sh-yb-policy-monitor` 的抓取，再执行 `knowledge-base-update` 的 `policy` 模式。
- 响应没有把共享知识库的完整刷新职责留在 `sh-yb-policy-monitor` 内部单独完成。
- 最终结果明确说明知识库刷新是否成功或为何跳过。
- 最终结果明确说明路径来源是共享路径文件还是默认回退路径。

## Review Focus

- 这条用例是否足够明确地区分“抓取技能”和“知识库更新技能”。
- 断言是否足够验证标准 handoff，而不是只验证有无提到关键词。
