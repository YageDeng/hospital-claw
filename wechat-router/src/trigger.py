"""SSE trigger engine — subscribe to wechat-decrypt's message stream,
match against config rules, call reply callbacks, and send replies
via the WeChat UI.

Usage:
    python src/trigger.py [--config config.yaml]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Callable, Optional

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import ConfigManager
from src.navigator import ChatNavigator
from src.ocr_engine import create_ocr_engine
from src.platform_adapter import create_adapter
from src.utils import DebugSaver, setup_logging

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Callback loader
# ------------------------------------------------------------------

_callback_cache: dict[str, Callable] = {}


def load_callback(spec: str) -> Callable:
    """Dynamically import a callback from 'path/to/module.py::function_name'."""
    if spec in _callback_cache:
        return _callback_cache[spec]

    module_path, func_name = spec.rsplit("::", 1)
    abs_path = str(Path(module_path).resolve())

    mod_spec = importlib.util.spec_from_file_location(
        f"_trigger_plugin_{Path(module_path).stem}", abs_path)
    if mod_spec is None or mod_spec.loader is None:
        raise ImportError(f"Cannot load module: {module_path}")

    module = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(module)

    func = getattr(module, func_name, None)
    if func is None:
        raise AttributeError(f"Function '{func_name}' not found in {module_path}")

    _callback_cache[spec] = func
    return func


# ------------------------------------------------------------------
# Rule matching
# ------------------------------------------------------------------

class TriggerRule:
    def __init__(self, name: str, chat_pattern: str, content_pattern: str,
                 reply_callback: str):
        self.name = name
        self.chat_re = re.compile(chat_pattern, re.IGNORECASE)
        self.content_re = re.compile(content_pattern, re.IGNORECASE)
        self.reply_callback = reply_callback
        self._callback_fn: Optional[Callable] = None

    def matches(self, msg: dict) -> Optional[re.Match]:
        """Check if a message matches this rule. Returns the content Match or None."""
        chat = msg.get("chat", "")
        content = msg.get("content", "")
        if not self.chat_re.search(chat):
            return None
        return self.content_re.search(content)

    def get_callback(self) -> Callable:
        if self._callback_fn is None:
            self._callback_fn = load_callback(self.reply_callback)
        return self._callback_fn


# ------------------------------------------------------------------
# Cooldown tracker
# ------------------------------------------------------------------

class CooldownTracker:
    """Prevents reply loops by enforcing a per-rule+chat cooldown."""

    def __init__(self, cooldown_seconds: float = 10):
        self.cooldown = cooldown_seconds
        self._last: dict[str, float] = {}

    def is_allowed(self, rule_name: str, chat: str) -> bool:
        key = f"{rule_name}|{chat}"
        now = time.time()
        last = self._last.get(key, 0)
        if now - last < self.cooldown:
            return False
        self._last[key] = now
        return True


# ------------------------------------------------------------------
# SSE client
# ------------------------------------------------------------------

def sse_stream(url: str):
    """Generator that yields parsed SSE message dicts with auto-reconnect."""
    while True:
        try:
            logger.info("Connecting to SSE stream: %s", url)
            resp = requests.get(url, stream=True, timeout=(10, None))
            resp.raise_for_status()
            resp.encoding = "utf-8"
            logger.info("Connected to SSE stream")

            buffer = ""
            event_type = ""
            line_count = 0

            for line in resp.iter_lines(chunk_size=1, decode_unicode=True):
                if line is None:
                    continue

                line_count += 1
                if line_count <= 5:
                    logger.info("SSE raw line %d: %s", line_count, line[:120])

                if line.startswith("event:"):
                    event_type = line[6:].strip()
                    continue

                if line.startswith("data:"):
                    buffer = line[5:].strip()
                    continue

                if line == "" and buffer:
                    if not event_type:
                        try:
                            parsed = json.loads(buffer)
                            logger.debug("SSE parsed event: %s", buffer[:120])
                            yield parsed
                        except json.JSONDecodeError:
                            logger.warning("Failed to parse SSE data: %s", buffer[:100])
                    else:
                        logger.debug("SSE skipping event type '%s'", event_type)
                    buffer = ""
                    event_type = ""

        except requests.ConnectionError:
            logger.warning("SSE connection lost, reconnecting in 3s...")
        except requests.Timeout:
            logger.warning("SSE connection timed out, reconnecting in 3s...")
        except Exception as e:
            logger.exception("SSE error: %s, reconnecting in 5s...", e)
            time.sleep(2)

        time.sleep(3)


# ------------------------------------------------------------------
# Main trigger loop
# ------------------------------------------------------------------

def run_trigger(config_mgr: ConfigManager):
    """Main loop: listen to SSE, match rules, send replies."""
    cfg = config_mgr.config
    raw_yaml_path = Path(config_mgr.config_path)
    with open(raw_yaml_path, "r", encoding="utf-8") as f:
        import yaml
        raw = yaml.safe_load(f) or {}

    triggers_cfg = raw.get("triggers", {})
    sse_url = triggers_cfg.get("sse_url", "http://localhost:5678/stream")
    cooldown_seconds = triggers_cfg.get("cooldown_seconds", 10)
    raw_rules = triggers_cfg.get("rules", [])

    if not raw_rules:
        logger.warning("No trigger rules configured in config.yaml — nothing to do")
        logger.info("Add rules under 'triggers.rules' in config.yaml")
        return

    rules = []
    for r in raw_rules:
        try:
            rule = TriggerRule(
                name=r["name"],
                chat_pattern=r.get("chat_pattern", ".*"),
                content_pattern=r["content_pattern"],
                reply_callback=r["reply_callback"],
            )
            rule.get_callback()
            rules.append(rule)
            logger.info("Loaded rule '%s': chat=/%s/ content=/%s/ -> %s",
                         rule.name, r.get("chat_pattern", ".*"),
                         r["content_pattern"], r["reply_callback"])
        except Exception as e:
            logger.error("Failed to load rule '%s': %s", r.get("name", "?"), e)

    if not rules:
        logger.error("No valid rules loaded — exiting")
        return

    cooldown = CooldownTracker(cooldown_seconds)

    adapter = create_adapter()
    adapter.nav_bar_ratio = cfg.platform.nav_bar_ratio
    adapter.sidebar_ratio = cfg.platform.sidebar_ratio
    adapter.avatar_ratio = cfg.platform.avatar_ratio
    ocr = create_ocr_engine(cfg.ocr.engine, languages=cfg.ocr.languages)

    debug_dir = config_mgr.resolve_path(cfg.storage.debug_dir)
    debug = DebugSaver(debug_dir, enabled=True)
    navigator = ChatNavigator(adapter, debug=debug)

    ctx = {
        "config_mgr": config_mgr,
        "adapter": adapter,
        "ocr": ocr,
        "navigator": navigator,
    }

    logger.info("Trigger engine started with %d rule(s), cooldown=%ds",
                 len(rules), cooldown_seconds)
    logger.info("Listening on %s", sse_url)

    for msg in sse_stream(sse_url):
        msg_type = msg.get("type", "")
        content = msg.get("content", "")
        chat = msg.get("chat", "")
        sender = msg.get("sender", "")
        msg_time = msg.get("time", "")

        logger.info("SSE msg: [%s] chat='%s' sender='%s' type='%s' content='%s'",
                     msg_time, chat, sender, msg_type, (content or "")[:80])

        if not content or not chat:
            logger.info("  Skipped: empty content or chat")
            continue

        for rule in rules:
            match = rule.matches(msg)
            if match is None:
                continue

            logger.info("[%s] Rule '%s' matched in '%s' (sender=%s): %s",
                         msg.get("time", ""), rule.name, chat, sender, content[:60])

            if not cooldown.is_allowed(rule.name, chat):
                logger.info("  Cooldown active for rule '%s' in '%s', skipping", rule.name, chat)
                continue

            try:
                callback = rule.get_callback()
                callback(msg, match, ctx)
            except Exception as e:
                logger.exception("  Callback error for rule '%s': %s", rule.name, e)


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="WeChat trigger engine — auto-reply based on SSE message stream")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    args = parser.parse_args()

    config_mgr = ConfigManager(args.config)
    cfg = config_mgr.config

    log_file = config_mgr.resolve_path(cfg.logging.file)
    setup_logging(cfg.logging.level, log_file)
    config_mgr.ensure_directories()

    logger.info("WeChat Trigger Engine starting")

    try:
        run_trigger(config_mgr)
    except KeyboardInterrupt:
        logger.info("Trigger engine stopped by user")


if __name__ == "__main__":
    main()
