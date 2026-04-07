"""Example reply plugin — echoes back the matched content.

Callback signature:
    def on_match(message: dict, match: re.Match, ctx: dict) -> None

Args:
    message: SSE message dict with keys: chat, username, sender,
             content, timestamp, type, is_group
    match:   regex Match object from the content_pattern
    ctx:     dict with keys: config_mgr, adapter, ocr, navigator

The callback is responsible for all actions (sending replies, etc.).
"""

from __future__ import annotations

import logging
import re
import time

logger = logging.getLogger(__name__)


def _strip_emoji(text: str) -> str:
    """Remove emoji and other non-BMP characters that OCR can't recognize."""
    return re.sub(
        r'[\U00010000-\U0010ffff'   # supplementary planes (most emoji)
        r'\u2600-\u27bf'            # misc symbols
        r'\u2b50-\u2bff'            # additional symbols
        r'\ufe00-\ufe0f'            # variation selectors
        r'\u200d'                   # zero-width joiner
        r'\u20e3'                   # combining enclosing keycap
        r']+', '', text
    ).strip()


def send_reply(ctx: dict, chat_name: str, reply_text: str,
               max_retries: int = 3) -> bool:
    """Bring WeChat to front, find the chat, and send a reply.

    Each retry: scroll to top -> try find chat -> if fail, retry.
    Strips emoji from chat_name for OCR matching.
    """
    config_mgr = ctx["config_mgr"]
    adapter = ctx["adapter"]
    ocr = ctx["ocr"]
    navigator = ctx["navigator"]
    cfg = config_mgr.config

    search_name = _strip_emoji(chat_name)
    if search_name != chat_name:
        logger.info("Stripped emoji from chat name: '%s' -> '%s'", chat_name, search_name)

    try:
        if not adapter.find_wechat_window(cfg.wechat.window_title):
            logger.error("WeChat window not found, cannot send reply")
            return False
        time.sleep(0.5)

        cal_path = config_mgr.resolve_path(cfg.platform.calibration_file)
        calibration = adapter.load_calibration(cal_path)

        for attempt in range(1, max_retries + 1):
            logger.info("Attempt %d/%d: find '%s'",
                         attempt, max_retries, search_name)

            if navigator.find_and_open_chat(search_name, ocr, calibration):
                navigator.send_message(reply_text)
                logger.info("Reply sent to '%s': %s", chat_name, reply_text[:80])
                return True

            logger.warning("Attempt %d/%d: could not find '%s', retrying...",
                            attempt, max_retries, search_name)
            time.sleep(1)

        logger.error("Failed to find chat '%s' after %d retries", chat_name, max_retries)
        return False

    except Exception as e:
        logger.exception("Failed to send reply to '%s': %s", chat_name, e)
        return False


def on_match(message: dict, match: re.Match, ctx: dict) -> None:
    """Echo the matched content back to the sender."""
    chat = message.get("chat", "")
    sender = message.get("sender", "")
    content = message.get("content", "")
    matched_text = match.group(0)

    reply = f"[auto-reply] Received '{matched_text}' in {chat} from {sender}, full content: {content}"

    logger.info("Echo plugin: replying to '%s' in 2s", chat)
    time.sleep(2)

    send_reply(ctx, chat, reply)
