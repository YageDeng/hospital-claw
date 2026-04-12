# Eval 3: Treatment Plan Refresh If Stale

## Prompt

请根据这位患者的信息制定治疗方案：女，52岁，66kg，颈肩痛伴腰痛 4 个月，睡眠差，久坐办公。我担心当前共享知识库里的收费政策不是最新的，所以如果你判断需要补抓政策并刷新知识库，就先完成那条链路，再给我正式方案。

## Expected Cooperation Chain

1. `tcm-treatment-plan` 保持只读。
2. 如需最新政策，先走 `sh-yb-policy-monitor` 抓取。
3. 再由 `knowledge-base-update` 刷新共享知识库。
4. 最后才基于共享知识库生成正式方案。

## Assertions

- 响应把 `tcm-treatment-plan` 表述为共享知识库的只读消费者，而不是知识库维护者。
- 当知识库可能过期时，响应明确先走 `sh-yb-policy-monitor` 加 `knowledge-base-update` 的刷新链路。
- 刷新完成后，响应明确通过共享知识库查询价格和规则，再生成方案。
- 最终方案明确说明价格/规则的数据来源。

## Review Focus

- 这条用例是否能测试“消费技能先判断 freshness，再决定是否走 producer/update 链路”。
- 断言是否足够防止 `tcm-treatment-plan` 越权修改知识库。
