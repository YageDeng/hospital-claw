# Eval 4: Treatment Review Refresh If Stale

## Prompt

我准备审查一张中医治疗申请单，里面有常规针法、药物罐加收、腰部推拿。请先确认共享知识库是否需要因最近政策变动而刷新；如果需要，按标准协作链先刷新，再用更新后的知识库给我正式审查结论，不要直接手改知识库。

## Expected Cooperation Chain

1. `tcm-treatment-review` 保持只读。
2. 如果知识库需要刷新，先走生产者技能。
3. 再由 `knowledge-base-update` 做标准刷新。
4. 刷新后再用共享知识库做价格核验与规则审查。

## Assertions

- 响应把 `tcm-treatment-review` 表述为共享知识库的只读消费者，而不是知识库维护者。
- 当知识库需要刷新时，响应明确先走生产者技能再走 `knowledge-base-update`。
- 刷新后，响应明确使用共享知识库进行价格核验和规则审查。
- 最终结果明确说明是否发生刷新以及审查依据。

## Review Focus

- 这条用例是否能测试“审查技能只消费，不维护”。
- 断言是否足够检出越权修改知识库或跳过刷新链路的情况。
