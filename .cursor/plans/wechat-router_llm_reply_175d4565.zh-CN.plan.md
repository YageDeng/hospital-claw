---
name: wechat-router llm reply zh-cn
overview: 为 `wechat-router` 制定一份聚焦的实施计划：提升基于 OCR 的聊天目标定位能力，将固定关键字回复替换为本地持久化的 LLM 任务队列加轮询 worker，并增加一个 `ChatGPT-on-WeChat` 机器人回退方案。
todos:
  - id: improve-chat-lookup
    content: 提升导航器和平台适配层中的 OCR 聊天定位可靠性，包括校准、候选排序和回退 OCR 识别
    status: in_progress
  - id: add-queue-callback
    content: 为匹配到的关键字事件增加持久化队列回调与任务存储模型
    status: pending
  - id: build-llm-worker
    content: 实现本地 LLM 提交与轮询 worker，并通过现有回复发送链路把结果返回给原始聊天对象
    status: pending
  - id: wire-config-and-rules
    content: 更新触发器与配置联动，使规则改为提交队列任务而不是固定文本回复，同时保留调试回退能力
    status: pending
  - id: verify-flow
    content: 为入队、轮询、去重以及回复到正确聊天对象增加聚焦测试和人工验证
    status: pending
  - id: chatgpt-on-wechat-fallback
    content: 在 `sub-repo/ChatGPT-on-WeChat` 中增加一个支持非 OpenAI 模型端点和本地自动化机器人部署验证的回退方案
    status: pending
isProject: false
---

# 微信路由 OCR 与 LLM 队列计划

**目标：** 提升 `wechat-router` 中回复目标聊天的匹配能力，将命中关键字的消息路由到一个本地持久化的 LLM 任务队列中，由该队列轮询外部 LLM 服务并在结果完成后回复到原始微信聊天，同时增加一个基于 `sub-repo/ChatGPT-on-WeChat` 的并行回退路径。

## 当前可复用点
- 保留 [`wechat-router/src/trigger.py`](wechat-router/src/trigger.py) 中现有的 SSE 触发入口；它已经能够监听消息事件并分发 `reply_callback` 处理器。
- 复用 [`wechat-router/src/reply_plugins/echo.py`](wechat-router/src/reply_plugins/echo.py) 和 [`wechat-router/src/navigator.py`](wechat-router/src/navigator.py) 中现有的回复发送链路，而不是再发明第二套 UI 自动化发送路径。
- 保留 [`wechat-router/config.yaml`](wechat-router/config.yaml) 中的规则配置方式，但把命中规则后的行为从固定文本回复改成队列提交。
- 将 [`sub-repo/ChatGPT-on-WeChat/src/main.ts`](sub-repo/ChatGPT-on-WeChat/src/main.ts) 和 [`sub-repo/ChatGPT-on-WeChat/src/chatgpt.ts`](sub-repo/ChatGPT-on-WeChat/src/chatgpt.ts) 视为独立的回退机器人路径，而不是直接把它的运行时混入 `wechat-router`。

## 文件映射
- 修改 [`wechat-router/src/navigator.py`](wechat-router/src/navigator.py)：通过对所有 OCR 候选项打分、确定性重试，以及在宣告失败前增加回退 OCR 识别，提升聊天查找可靠性。
- 修改 [`wechat-router/src/platform_adapter.py`](wechat-router/src/platform_adapter.py)：在存在已保存校准矩形时优先生效，使 OCR 真正作用于实际侧边栏区域，而不是只依赖比例裁剪。
- 修改 [`wechat-router/src/trigger.py`](wechat-router/src/trigger.py)：保留 SSE 与规则匹配逻辑，但确保回调只负责把工作持久化入队，而不会因为长时间 LLM 调用阻塞主循环。
- 修改 [`wechat-router/config.yaml`](wechat-router/config.yaml)：添加 `llm` 与队列设置，并把规则回调切换到新的队列插件。
- 新增 [`wechat-router/src/reply_plugins/llm_queue.py`](wechat-router/src/reply_plugins/llm_queue.py)：根据命中的消息构建任务载荷并持久化队列项。
- 新增 [`wechat-router/src/task_store.py`](wechat-router/src/task_store.py) 或扩展 [`wechat-router/src/storage.py`](wechat-router/src/storage.py)：保存任务状态、外部任务 ID、重试次数、时间戳、原始聊天元数据、最终响应与最后错误。
- 新增 [`wechat-router/src/llm_worker.py`](wechat-router/src/llm_worker.py)：提交待处理任务到外部 LLM 服务，轮询结果，并把完成的输出交给现有回复发送链路。
- 在 [`wechat-router/tests`](wechat-router/tests) 下新增或更新聚焦测试，覆盖队列状态流转、触发入队行为以及聊天查找的排序/回退逻辑。
- 修改 [`sub-repo/ChatGPT-on-WeChat/src/interface.ts`](sub-repo/ChatGPT-on-WeChat/src/interface.ts) 和 [`sub-repo/ChatGPT-on-WeChat/src/config.ts`](sub-repo/ChatGPT-on-WeChat/src/config.ts)：把配置扩展为不仅支持 OpenAI 密钥，还能提供模型端点、基础 URL 与提供方相关设置。
- 修改 [`sub-repo/ChatGPT-on-WeChat/src/chatgpt.ts`](sub-repo/ChatGPT-on-WeChat/src/chatgpt.ts)：隔离模型客户端初始化逻辑，使 OpenAI 兼容端点或其他替代提供方端点在部署时无需重复改源码。
- 修改 [`sub-repo/ChatGPT-on-WeChat/config.yaml.example`](sub-repo/ChatGPT-on-WeChat/config.yaml.example)、[`sub-repo/ChatGPT-on-WeChat/.env.example`](sub-repo/ChatGPT-on-WeChat/.env.example) 和 [`sub-repo/ChatGPT-on-WeChat/README.md`](sub-repo/ChatGPT-on-WeChat/README.md)：补充新的端点配置方式以及本地回退机器人启动/验证流程文档。

## 工作流
### 1. 稳定基于 OCR 的聊天目标定位
- 让校准数据真正影响侧边栏裁剪区域，使 OCR 区域与用户的实际微信窗口布局一致。
- 在 `find_chat_in_sidebar` 中，不再返回第一个满足阈值的模糊匹配结果，而是按分数、OCR 置信度与行质量对候选项排序后选择最佳目标点击。
- 在快速 OCR 识别失败时增加第二轮回退识别，例如使用全分辨率 OCR 或合并后的整行文本，再决定是否失败。
- 强化滚动逻辑，让“滚动到顶部”和“已经到达底部”的判断基于图像稳定性，而不是固定少量滚动次数。
- 保留现有 OCR-first 策略，但通过调试图像和日志明确记录候选分数，便于分析未命中的原因。

### 2. 用持久化队列提交替换固定回复
- 引入一个队列回调插件，把命中的 SSE 消息转换成持久化任务记录，而不是在回调里直接回复。
- 保存足够的元数据以支持后续回复，不依赖猜测：规则名、聊天名、发送者、原始消息内容、去重键、创建时间、外部任务 ID、当前状态、重试次数与最终输出。
- 让入队具备幂等性，避免 SSE 重连或重复事件导致重复创建任务和重复回复。
- 保留 `trigger.py` 中的冷却时间逻辑，但把任务存储视为“消息是否已处理”的持久化事实来源。

### 3. 增加本地 LLM 轮询 Worker
- 构建一个 worker 循环，扫描待处理任务，提交到外部 LLM 服务，记录返回的远端任务 ID，并持续轮询直到任务完成或失败。
- 第一版保持为单机、本地进程：不引入 webhook 服务、不做多进程编排，也不引入分布式队列。
- 当任务完成时，把最终文本通过现有 `navigator` 回复链路发回原始微信聊天，从而复用已有 UI 自动化发送流程。
- 对失败任务持久化保存重试信息和最后错误，避免任务静默丢失。

### 4. 验证与安全
- 增加聚焦测试，覆盖队列记录创建、状态流转（`pending -> submitted -> completed/failed`）以及触发去重行为。
- 增加针对 `navigator` 的目标测试，验证最佳候选排序与 OCR 未命中时的回退逻辑。
- 对集成链路做人工验证：SSE 事件被接收、任务被写入、worker 完成处理、最终回复正确发送到目标聊天。
- 第一轮发布保留显式配置开关，以便在调试阶段仍可切回原有 echo 风格的回复路径。

### 5. 增加 `ChatGPT-on-WeChat` 回退机器人路径
- 扩展 [`sub-repo/ChatGPT-on-WeChat/src/interface.ts`](sub-repo/ChatGPT-on-WeChat/src/interface.ts) 和 [`sub-repo/ChatGPT-on-WeChat/src/config.ts`](sub-repo/ChatGPT-on-WeChat/src/config.ts)，让机器人可以读取提供方无关的设置，例如 API 基础 URL、模型名以及其他替代端点元数据，而不再只假定存在 `openaiApiKey` 和 `openaiOrganizationID`。
- 重构 [`sub-repo/ChatGPT-on-WeChat/src/chatgpt.ts`](sub-repo/ChatGPT-on-WeChat/src/chatgpt.ts)，优先支持 OpenAI 兼容的替代端点，同时为后续真正非兼容提供方保留清晰的扩展接口。
- 更新 [`sub-repo/ChatGPT-on-WeChat/config.yaml.example`](sub-repo/ChatGPT-on-WeChat/config.yaml.example)、[`sub-repo/ChatGPT-on-WeChat/.env.example`](sub-repo/ChatGPT-on-WeChat/.env.example) 和 [`sub-repo/ChatGPT-on-WeChat/README.md`](sub-repo/ChatGPT-on-WeChat/README.md)，补充新的提供方/基础 URL 设置以及使用 `npm run dev`、Docker 或 Compose 的本地启动说明。
- 验证该回退机器人是否能在当前环境中本地部署并完成登录，并记录结果：要么给出一条可成功启动自动机器人的本地路径，要么明确写出受二维码登录、账号限制、依赖问题或运行时限制影响而无法完成的具体阻塞点。
- 保持该回退方案与 OCR 和 GUI 自动发送路径并行推进，以便在 UI 自动化在生产中仍不稳定时可直接切换为备用方案。

## 验收标准
- 命中关键字后不再发送硬编码的即时回复，而是创建一个持久化的本地任务。
- 本地 worker 可以在不阻塞 SSE 触发循环的情况下提交并轮询 LLM 任务。
- LLM 完成后的输出可以通过现有发送链路回复到原始微信聊天。
- 基于 OCR 的聊天定位可靠性得到可观提升，因为校准、候选排序与回退逻辑都已落地。
- 重复消息在重连或重启后不会产生重复的 LLM 任务或重复回复。
- `sub-repo/ChatGPT-on-WeChat` 至少可以针对一种非默认模型端点完成无源码修改的部署配置。
- 回退机器人路径必须有一份本地验证结论：要么成功完成本地部署/登录流程，要么明确记录环境检查中发现的阻塞因素。
