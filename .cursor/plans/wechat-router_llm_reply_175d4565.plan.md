---
name: wechat-router llm reply
overview: Create a focused implementation plan for `wechat-router` that improves OCR-based chat targeting, replaces the fixed keyword reply with a local persisted LLM task queue plus polling worker, and adds a `ChatGPT-on-WeChat` fallback bot track.
todos:
  - id: improve-chat-lookup
    content: Improve OCR-based chat lookup reliability in the navigator and platform adapter using calibration, candidate ranking, and fallback OCR passes
    status: in_progress
  - id: add-queue-callback
    content: Add a durable queue callback and task persistence model for matched keyword events
    status: pending
  - id: build-llm-worker
    content: Implement the local LLM submission/polling worker and route completed outputs back through the existing reply sender
    status: pending
  - id: wire-config-and-rules
    content: Update trigger/config wiring so rules submit queue tasks instead of fixed text replies while preserving debug fallback options
    status: pending
  - id: verify-flow
    content: Add focused tests and manual verification for enqueue, polling, dedupe, and reply-to-correct-chat behavior
    status: pending
  - id: chatgpt-on-wechat-fallback
    content: Add a fallback track in `sub-repo/ChatGPT-on-WeChat` for non-OpenAI model endpoints and local automated bot deployment validation
    status: pending
isProject: false
---

# WeChat Router OCR And LLM Queue Plan

**Goal:** Improve reply-target chat matching in `wechat-router`, route matched keyword messages into a local persisted LLM task queue that polls an external LLM service and replies back to the original WeChat chat when the result is ready, and add a parallel fallback path based on `sub-repo/ChatGPT-on-WeChat`.

## Current Reuse Points
- Keep the existing SSE trigger entrypoint in [`wechat-router/src/trigger.py`](wechat-router/src/trigger.py); it already listens to message events and dispatches `reply_callback` handlers.
- Reuse the current reply send path from [`wechat-router/src/reply_plugins/echo.py`](wechat-router/src/reply_plugins/echo.py) and [`wechat-router/src/navigator.py`](wechat-router/src/navigator.py) instead of inventing a second UI automation path.
- Preserve rule configuration in [`wechat-router/config.yaml`](wechat-router/config.yaml), but change matched-rule behavior from fixed text reply to queue submission.
- Treat [`sub-repo/ChatGPT-on-WeChat/src/main.ts`](sub-repo/ChatGPT-on-WeChat/src/main.ts) and [`sub-repo/ChatGPT-on-WeChat/src/chatgpt.ts`](sub-repo/ChatGPT-on-WeChat/src/chatgpt.ts) as a separate fallback bot path rather than mixing its runtime directly into `wechat-router`.

## File Map
- Modify [`wechat-router/src/navigator.py`](wechat-router/src/navigator.py): improve chat lookup reliability by scoring all OCR candidates, retrying deterministically, and adding a fallback OCR pass before declaring failure.
- Modify [`wechat-router/src/platform_adapter.py`](wechat-router/src/platform_adapter.py): honor saved calibration rectangles when present so OCR works against the real sidebar bounds instead of ratios alone.
- Modify [`wechat-router/src/trigger.py`](wechat-router/src/trigger.py): keep SSE/rule matching, but ensure callback execution only enqueues durable work and does not block the stream with long LLM calls.
- Modify [`wechat-router/config.yaml`](wechat-router/config.yaml): add `llm` and queue settings, plus switch the trigger rule to a new queue callback.
- Add [`wechat-router/src/reply_plugins/llm_queue.py`](wechat-router/src/reply_plugins/llm_queue.py): build the task payload from the matched message and persist a queue item.
- Add [`wechat-router/src/task_store.py`](wechat-router/src/task_store.py) or extend [`wechat-router/src/storage.py`](wechat-router/src/storage.py): store task state, external task id, attempts, timestamps, original chat metadata, final response, and last error.
- Add [`wechat-router/src/llm_worker.py`](wechat-router/src/llm_worker.py): submit pending tasks to the external LLM service, poll for completion, and hand completed outputs to the existing reply sender.
- Add or update focused tests under [`wechat-router/tests`](wechat-router/tests) for queue state transitions, trigger enqueue behavior, and chat lookup ranking/fallback logic.
- Modify [`sub-repo/ChatGPT-on-WeChat/src/interface.ts`](sub-repo/ChatGPT-on-WeChat/src/interface.ts) and [`sub-repo/ChatGPT-on-WeChat/src/config.ts`](sub-repo/ChatGPT-on-WeChat/src/config.ts): extend configuration beyond OpenAI-only keys so model endpoint, base URL, and provider-specific settings can be supplied.
- Modify [`sub-repo/ChatGPT-on-WeChat/src/chatgpt.ts`](sub-repo/ChatGPT-on-WeChat/src/chatgpt.ts): isolate the model client setup so OpenAI-compatible or alternate provider endpoints can be used without source edits for every deployment.
- Modify [`sub-repo/ChatGPT-on-WeChat/config.yaml.example`](sub-repo/ChatGPT-on-WeChat/config.yaml.example), [`sub-repo/ChatGPT-on-WeChat/.env.example`](sub-repo/ChatGPT-on-WeChat/.env.example), and [`sub-repo/ChatGPT-on-WeChat/README.md`](sub-repo/ChatGPT-on-WeChat/README.md): document the new endpoint settings and the local fallback-bot startup/validation flow.

## Workstreams
### 1. Stabilize OCR-Based Chat Targeting
- Make calibration data actually influence sidebar cropping so the OCR region matches the user’s window layout.
- In `find_chat_in_sidebar`, stop returning the first fuzzy match; rank candidates by score, OCR confidence, and row quality, then click the best candidate.
- Add a second-pass fallback when the fast OCR pass fails: full-resolution OCR and/or merged row text before giving up.
- Strengthen scroll behavior so “scroll to top” and “reached bottom” are based on image stability rather than a fixed small number of scroll steps.
- Keep the existing OCR-first strategy, but make it observable with debug artifacts and logs that show candidate scores for misses.

### 2. Replace Fixed Reply With Durable Queue Submission
- Introduce a queue callback plugin that converts a matched SSE message into a persisted task record instead of replying inline.
- Store enough metadata to reply later without guessing: rule name, chat name, sender, original content, a dedupe key, created time, external task id, current status, attempt count, and final output.
- Make enqueue idempotent so reconnects or duplicate stream events do not create duplicate replies for the same source message.
- Keep cooldown logic in `trigger.py`, but treat the queue store as the durable source of truth for whether a task has already been processed.

### 3. Add Local LLM Poll Worker
- Build a worker loop that scans pending tasks, submits them to the external LLM service, stores the returned remote task id, and polls until each task is complete or failed.
- Keep the first version single-machine and local-process: no webhook server, no multi-process orchestration, no distributed queue yet.
- On completion, pass the final text into the existing navigator-based send flow so the reply still goes through WeChat UI automation.
- Persist failures with retry metadata and last error so tasks can be retried instead of silently disappearing.

### 4. Verification And Safety
- Add focused tests for queue record creation, state transitions (`pending -> submitted -> completed/failed`), and trigger dedupe behavior.
- Add targeted navigator tests for best-candidate selection and fallback execution on OCR misses.
- Verify the integrated flow manually with a sample keyword match: SSE event received, task written, worker completion observed, and reply sent to the correct chat.
- Keep the first rollout behind explicit config values so the existing echo-style behavior can still be used for debugging if needed.

### 5. Add `ChatGPT-on-WeChat` Fallback Bot Track
- Extend [`sub-repo/ChatGPT-on-WeChat/src/interface.ts`](sub-repo/ChatGPT-on-WeChat/src/interface.ts) and [`sub-repo/ChatGPT-on-WeChat/src/config.ts`](sub-repo/ChatGPT-on-WeChat/src/config.ts) so the bot can read provider-neutral settings such as API base URL, model name, and any alternate endpoint metadata instead of assuming only `openaiApiKey` and `openaiOrganizationID`.
- Refactor [`sub-repo/ChatGPT-on-WeChat/src/chatgpt.ts`](sub-repo/ChatGPT-on-WeChat/src/chatgpt.ts) so the request path supports at least OpenAI-compatible alternative endpoints first, while leaving a clean seam for truly non-compatible providers if they are needed later.
- Update [`sub-repo/ChatGPT-on-WeChat/config.yaml.example`](sub-repo/ChatGPT-on-WeChat/config.yaml.example), [`sub-repo/ChatGPT-on-WeChat/.env.example`](sub-repo/ChatGPT-on-WeChat/.env.example), and [`sub-repo/ChatGPT-on-WeChat/README.md`](sub-repo/ChatGPT-on-WeChat/README.md) with the new provider/base URL settings and a clear local startup path using `npm run dev` and Docker/Compose options.
- Validate whether the fallback bot can be deployed and logged into locally in this environment, and record either a successful automated-bot startup path or the concrete blocker if QR-login, account restrictions, or dependency/runtime issues prevent completion.
- Keep this fallback track parallel to the OCR and GUI auto-send path so it can be used if UI automation remains unreliable in production.

## Acceptance Criteria
- A keyword match no longer sends a hardcoded inline reply; it creates a durable local task instead.
- A local worker can submit and poll LLM tasks without blocking the SSE trigger loop.
- Completed LLM output is sent back to the original WeChat chat through the existing send path.
- OCR-based chat targeting is measurably more reliable because calibration, candidate ranking, and retry/fallback logic are in place.
- Duplicate messages do not lead to duplicate LLM jobs or duplicate replies after reconnects/restarts.
- `sub-repo/ChatGPT-on-WeChat` can be configured for at least one non-default model endpoint without editing source code for each deployment.
- The fallback bot path has a documented local validation result: either a successful local deployment/login flow or explicit blockers recorded from the environment check.
