# Eval 2: WeChat Handoff To KB Update

## Prompt

我刚发来一篇公众号文章，需要你抓取正文、按监测规则分类，并把它纳入共享知识库。文章落盘后，如果还需要刷新 manifest、集合或 wiki，请走标准技能协作，不要重复实现两套知识库逻辑。

## Expected Cooperation Chain

1. `wechat-daily-monitor` 负责抓取、分类与落盘。
2. 完整知识库刷新交给 `knowledge-base-update` 的 `docs` 模式。
3. 如果只做最小刷新，需要明确说明范围仅限 `source_md`。

## Assertions

- 响应明确先由 `wechat-daily-monitor` 完成文章抓取与分类。
- 响应明确将完整知识库刷新交给 `knowledge-base-update` 的 `docs` 模式。
- 如果提到 `--refresh-kb`，响应明确说明它只覆盖最小 `source_md` 刷新。
- 响应避免在公众号技能里重复实现 manifest、wiki 或全量集合维护逻辑。

## Review Focus

- 这条用例是否能稳定检查“最小刷新”和“完整刷新”之间的边界。
- 断言是否能发现错误的双重实现。
