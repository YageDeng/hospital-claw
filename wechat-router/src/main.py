"""CLI entry point and main monitoring loop."""

import argparse
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.capture import ScreenCapture
from src.config import ConfigManager
from src.detector import UnreadDetector
from src.extractor import ContentExtractor
from src.navigator import ChatNavigator
from src.ocr_engine import create_ocr_engine
from src.platform_adapter import create_adapter
from src.storage import StorageManager
from src.utils import DebugSaver, setup_logging

logger = logging.getLogger(__name__)

CRASH_COOLDOWN = 60


def _log_message(contact_name: str, msg) -> None:
    """Log a single parsed message for visibility."""
    sender = msg.sender or "unknown"
    text_preview = (msg.text_content or "").replace("\n", " ")[:80]
    ts = msg.timestamp_ocr or ""
    if msg.content_type == "text":
        logger.info("  [%s] %s | %s: %s", contact_name, ts, sender, text_preview)
    elif msg.attachment_path:
        logger.info("  [%s] %s | %s: <%s> %s", contact_name, ts, sender,
                     msg.content_type, os.path.basename(msg.attachment_path))
    else:
        logger.info("  [%s] %s | %s: <%s> %s", contact_name, ts, sender,
                     msg.content_type, text_preview)


def run_query(storage: StorageManager, contact_name: str = None, limit: int = 50) -> None:
    """Print messages from the database, optionally filtered by contact name."""
    msgs = storage.get_messages(contact_name=contact_name, limit=limit)
    if not msgs:
        print("No messages found.")
        return

    print(f"\n{'='*70}")
    print(f" Messages{' for ' + contact_name if contact_name else ''} ({len(msgs)} result(s))")
    print(f"{'='*70}\n")

    for m in reversed(msgs):
        sender = m.get("sender") or ""
        ctype = m["content_type"]
        text = m.get("text_content") or ""
        ts_ocr = m.get("timestamp_ocr") or ""
        captured = m["captured_at"]
        contact = m["contact_name"]

        header = f"[{contact}] {ts_ocr}"
        if sender:
            header += f" | {sender}"

        if ctype == "text":
            print(f"  {header}")
            print(f"    {text}")
        else:
            print(f"  {header} <{ctype}>")
            if text:
                print(f"    {text}")

        print()


def _build_stop_keywords() -> list:
    """Build a list of date strings that indicate 'before today' in WeChat timestamps.

    WeChat uses relative timestamps like "Yesterday", "昨天", or absolute dates
    like "03/29", "2026/03/29", "3月29日", etc. We generate patterns for
    yesterday and earlier so we know when to stop scrolling.
    """
    today = datetime.now()

    keywords = [
        "Yesterday",
        "昨天",
    ]

    for delta in range(1, 7):
        d = today - timedelta(days=delta)
        keywords.append(f"{d.month:02d}/{d.day:02d}")          # 03/29
        keywords.append(f"{d.month}/{d.day}")                   # 3/29
        keywords.append(f"{d.month:02d}\u6708{d.day:02d}\u65e5")  # 03月29日
        keywords.append(f"{d.month}\u6708{d.day}\u65e5")          # 3月29日
        keywords.append(f"{d.year}/{d.month:02d}/{d.day:02d}")    # 2026/03/29

    return list(dict.fromkeys(keywords))


def run_calibration(adapter, config_mgr):
    """Run first-time calibration to detect WeChat window regions."""
    logger.info("Starting calibration...")

    title = config_mgr.config.wechat.window_title
    if not adapter.find_wechat_window(title):
        logger.error("Cannot calibrate: WeChat window not found")
        return False

    rect = adapter.get_window_rect()
    if not rect:
        logger.error("Cannot calibrate: could not get window rect")
        return False

    left, top, ww, wh = rect
    sidebar_w = adapter.get_sidebar_width(ww)

    calibration = {
        "window": {"left": left, "top": top, "width": ww, "height": wh},
        "chat_list": [0, 0, sidebar_w, wh],
        "message_area": [sidebar_w, 0, ww - sidebar_w, wh],
    }

    cal_path = config_mgr.resolve_path(config_mgr.config.platform.calibration_file)
    adapter.save_calibration(cal_path, calibration)
    logger.info("Calibration complete. Saved to %s", cal_path)
    return True


def run_scan(adapter, capture, detector, navigator, extractor, storage, config_mgr, ocr=None):
    """Run a single scan cycle: detect unreads, open chats, extract messages."""
    title = config_mgr.config.wechat.window_title
    if not adapter.find_wechat_window(title):
        logger.warning("WeChat window not found — skipping cycle")
        return 0

    cal_path = config_mgr.resolve_path(config_mgr.config.platform.calibration_file)
    calibration = adapter.load_calibration(cal_path)

    if ocr:
        navigator.reset_chat_selection(
            ocr, config_mgr.config.wechat.reset_chat, calibration)

    chat_list_img = capture.capture_chat_list(calibration, save=True)
    if chat_list_img is None:
        logger.warning("Failed to capture chat list — skipping cycle")
        return 0

    unread_chats = detector.detect_unread(chat_list_img)
    if not unread_chats:
        logger.info("No unread messages from monitored contacts")
        return 0

    total_messages = 0
    monitored_map = {m.name: m for m in config_mgr.config.monitored}

    for chat in unread_chats:
        logger.info("Processing unread chat: %s (score=%.2f)", chat.name, chat.match_score)

        if not navigator.open_chat(chat.click_point[0], chat.click_point[1]):
            logger.warning("Failed to open chat: %s", chat.name)
            continue

        screenshots = navigator.capture_all_messages(calibration)

        contact_info = monitored_map.get(chat.name)
        is_group = contact_info.type == "group" if contact_info else False

        for screenshot in screenshots:
            messages = extractor.extract_messages(screenshot, is_group=is_group)

            for msg in messages:
                msg_id = storage.insert_message(
                    contact_name=chat.name,
                    contact_type="group" if is_group else "contact",
                    sender=msg.sender,
                    content_type=msg.content_type,
                    text_content=msg.text_content,
                    timestamp_ocr=msg.timestamp_ocr,
                    raw_screenshot=None,
                )
                if msg_id and msg.attachment_path:
                    storage.insert_attachment(
                        message_id=msg_id,
                        file_type=msg.content_type,
                        file_path=msg.attachment_path,
                        file_name=os.path.basename(msg.attachment_path),
                    )
                if msg_id:
                    total_messages += 1
                    _log_message(chat.name, msg)
                else:
                    logger.debug("[%s] duplicate skipped: %s", chat.name,
                                 (msg.text_content or "")[:60])

        navigator.return_to_chat_list()

    logger.info("Scan complete: stored %d new message(s)", total_messages)
    return total_messages


def run_parse_today(target_name, adapter, navigator, ocr, extractor, storage,
                    config_mgr, contact_type="group"):
    """Open a specific chat and parse all messages from today.

    Three-phase workflow:
      1. Scroll UP fast (no screenshots) until a stop keyword (e.g. "Yesterday")
      2. Scroll DOWN capturing screenshots all the way to the bottom
      3. OCR all captured screenshots in batch
    """
    title = config_mgr.config.wechat.window_title
    if not adapter.find_wechat_window(title):
        logger.error("WeChat window not found")
        return 0

    cal_path = config_mgr.resolve_path(config_mgr.config.platform.calibration_file)
    calibration = adapter.load_calibration(cal_path)

    navigator.reset_chat_selection(
        ocr, config_mgr.config.wechat.reset_chat, calibration)

    # Find the chat by scrolling through the sidebar
    logger.info("Looking for '%s' in the chat list...", target_name)
    if not navigator.find_and_open_chat(target_name, ocr, calibration):
        logger.error("Could not find '%s' in the chat list", target_name)
        return 0

    stop_keywords = _build_stop_keywords()
    logger.info("Phase 1: Scrolling UP to find boundary (stop at: %s ...)", stop_keywords[:4])

    navigator.scroll_up_to_keyword(
        ocr_engine=ocr,
        stop_keywords=stop_keywords,
        calibration=calibration,
        max_scrolls=80,
    )

    # Phase 2: capture screenshots scrolling back down
    logger.info("Phase 2: Capturing screenshots scrolling DOWN to bottom...")
    screenshots = navigator.capture_downward(calibration=calibration, max_scrolls=80)

    if not screenshots:
        logger.warning("No message screenshots captured")
        return 0

    # Phase 3: OCR all captured screenshots
    logger.info("Phase 3: Extracting messages from %d screenshot(s)...", len(screenshots))
    is_group = contact_type == "group"
    total_messages = 0

    for i, screenshot in enumerate(screenshots):
        logger.info("Extracting messages from screenshot %d/%d", i + 1, len(screenshots))
        messages = extractor.extract_messages(screenshot, is_group=is_group)

        for msg in messages:
            msg_id = storage.insert_message(
                contact_name=target_name,
                contact_type=contact_type,
                sender=msg.sender,
                content_type=msg.content_type,
                text_content=msg.text_content,
                timestamp_ocr=msg.timestamp_ocr,
                raw_screenshot=None,
            )
            if msg_id and msg.attachment_path:
                storage.insert_attachment(
                    message_id=msg_id,
                    file_type=msg.content_type,
                    file_path=msg.attachment_path,
                    file_name=os.path.basename(msg.attachment_path),
                )
            if msg_id:
                total_messages += 1
                _log_message(target_name, msg)
            else:
                logger.debug("[%s] duplicate skipped: %s", target_name,
                             (msg.text_content or "")[:60])

    navigator.return_to_chat_list()
    logger.info("Parse today complete for '%s': stored %d new message(s)",
                target_name, total_messages)
    return total_messages


def run_send(target_name, message, adapter, navigator, ocr, config_mgr):
    """Find a chat and send a text message."""
    title = config_mgr.config.wechat.window_title
    if not adapter.find_wechat_window(title):
        logger.error("WeChat window not found")
        return False

    cal_path = config_mgr.resolve_path(config_mgr.config.platform.calibration_file)
    calibration = adapter.load_calibration(cal_path)

    navigator.reset_chat_selection(
        ocr, config_mgr.config.wechat.reset_chat, calibration)

    logger.info("Looking for '%s' in the chat list...", target_name)
    if not navigator.find_and_open_chat(target_name, ocr, calibration):
        logger.error("Could not find '%s' in the chat list", target_name)
        return False

    success = navigator.send_message(message)
    if success:
        logger.info("Message sent to '%s'", target_name)
    else:
        logger.error("Failed to send message to '%s'", target_name)
    return success


def main():
    parser = argparse.ArgumentParser(description="WeChat Monitor — capture unread messages")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    parser.add_argument("--once", action="store_true", help="Single scan and exit")
    parser.add_argument("--calibrate", action="store_true", help="Run calibration wizard")
    parser.add_argument("--parse-today", metavar="NAME",
                        help="Parse all of today's messages from a specific contact or group")
    parser.add_argument("--type", choices=["contact", "group"], default=None,
                        help="Contact type for --parse-today (auto-detected from config if omitted)")
    parser.add_argument("--send", metavar="NAME",
                        help="Send a message to a specific contact or group")
    parser.add_argument("--message", "-m", metavar="TEXT",
                        help="Message text to send (used with --send)")
    parser.add_argument("--query", nargs="?", const="__all__", metavar="NAME",
                        help="Query stored messages. Optionally filter by contact/group name")
    parser.add_argument("--limit", type=int, default=50,
                        help="Max messages to show with --query (default: 50)")
    args = parser.parse_args()

    config_mgr = ConfigManager(args.config)
    cfg = config_mgr.config

    log_file = config_mgr.resolve_path(cfg.logging.file)
    setup_logging(cfg.logging.level, log_file)
    config_mgr.ensure_directories()

    logger.info("WeChat Monitor starting")

    adapter = create_adapter()
    adapter.nav_bar_ratio = cfg.platform.nav_bar_ratio
    adapter.sidebar_ratio = cfg.platform.sidebar_ratio
    adapter.avatar_ratio = cfg.platform.avatar_ratio
    ocr = create_ocr_engine(cfg.ocr.engine, languages=cfg.ocr.languages)
    db_path = config_mgr.resolve_path(cfg.storage.database_path)
    storage = StorageManager(db_path)
    screenshots_dir = config_mgr.resolve_path(cfg.storage.screenshots_dir)
    attachments_dir = config_mgr.resolve_path(cfg.storage.attachments_dir)
    debug_dir = config_mgr.resolve_path(cfg.storage.debug_dir)

    debug = DebugSaver(debug_dir, enabled=True)

    capture = ScreenCapture(adapter, screenshots_dir, debug=debug)
    monitored_names = [m.name for m in cfg.monitored]
    detector = UnreadDetector(ocr, adapter, monitored_names, debug=debug)
    navigator = ChatNavigator(adapter, debug=debug)
    extractor = ContentExtractor(
        ocr, attachments_dir,
        confidence_threshold=cfg.ocr.confidence_threshold,
        debug=debug,
        msg_avatar_ratio=cfg.platform.msg_avatar_ratio,
    )

    if args.query is not None:
        contact_filter = None if args.query == "__all__" else args.query
        run_query(storage, contact_name=contact_filter, limit=args.limit)
        storage.close()
        sys.exit(0)

    if args.calibrate:
        success = run_calibration(adapter, config_mgr)
        storage.close()
        sys.exit(0 if success else 1)

    if args.send:
        if not args.message:
            parser.error("--send requires --message (-m) with the text to send")
        target = args.send
        logger.info("Sending message to: %s", target)
        success = run_send(target, args.message, adapter, navigator, ocr, config_mgr)
        storage.close()
        sys.exit(0 if success else 1)

    if args.parse_today:
        target = args.parse_today
        # Auto-detect contact type from config
        contact_type = args.type
        if not contact_type:
            for m in cfg.monitored:
                if m.name == target:
                    contact_type = m.type
                    break
            if not contact_type:
                contact_type = "contact"
                logger.warning("'%s' not found in config.monitored, defaulting to type='contact'", target)

        logger.info("Parsing today's messages for: %s (type=%s)", target, contact_type)
        count = run_parse_today(
            target, adapter, navigator, ocr, extractor, storage,
            config_mgr, contact_type=contact_type,
        )
        storage.close()
        logger.info("Done: %d message(s) captured", count)
        sys.exit(0)

    if args.once:
        logger.info("Monitoring %d contact(s)/group(s)", len(cfg.monitored))
        count = run_scan(adapter, capture, detector, navigator, extractor, storage, config_mgr, ocr=ocr)
        storage.close()
        logger.info("Single scan finished: %d message(s)", count)
        sys.exit(0)

    logger.info("Monitoring %d contact(s)/group(s)", len(cfg.monitored))
    logger.info("Starting continuous monitoring (interval=%ds)",
                cfg.wechat.polling_interval_seconds)

    while True:
        try:
            run_scan(adapter, capture, detector, navigator, extractor, storage, config_mgr, ocr=ocr)
        except KeyboardInterrupt:
            logger.info("Interrupted by user — shutting down")
            break
        except Exception:
            logger.exception("Unrecoverable error — cooling down %ds", CRASH_COOLDOWN)
            time.sleep(CRASH_COOLDOWN)
            continue

        time.sleep(cfg.wechat.polling_interval_seconds)

    storage.close()
    logger.info("WeChat Monitor stopped")


if __name__ == "__main__":
    main()
