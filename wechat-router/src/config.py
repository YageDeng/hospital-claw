"""Configuration loading and validation."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

logger = logging.getLogger(__name__)

VALID_CONTACT_TYPES = {"contact", "group"}
VALID_OCR_ENGINES = {"tesseract", "easyocr"}
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

DEFAULT_CONFIG = {
    "wechat": {
        "polling_interval_seconds": 30,
        "window_title": "WeChat",
        "reset_chat": "文件传输助手",
    },
    "monitored": [],
    "ocr": {
        "engine": "tesseract",
        "languages": "chi_sim+eng",
        "confidence_threshold": 0.6,
    },
    "storage": {
        "database_path": "data/wechat_monitor.db",
        "screenshots_dir": "data/screenshots",
        "attachments_dir": "data/attachments",
        "debug_dir": "data/debug",
    },
    "platform": {
        "auto_detect": True,
        "calibration_file": "data/calibration.json",
        "nav_bar_ratio": 0.035,
        "sidebar_ratio": 0.22,
        "avatar_ratio": 0.2,
        "msg_avatar_ratio": 0.04,
    },
    "logging": {
        "level": "INFO",
        "file": "logs/wechat_monitor.log",
    },
}


@dataclass
class MonitoredContact:
    name: str
    type: str  # 'contact' or 'group'


@dataclass
class WeChatConfig:
    polling_interval_seconds: int = 30
    window_title: str = "WeChat"
    reset_chat: str = "文件传输助手"


@dataclass
class OCRConfig:
    engine: str = "tesseract"
    languages: str = "chi_sim+eng"
    confidence_threshold: float = 0.6


@dataclass
class StorageConfig:
    database_path: str = "data/wechat_monitor.db"
    screenshots_dir: str = "data/screenshots"
    attachments_dir: str = "data/attachments"
    debug_dir: str = "data/debug"


@dataclass
class PlatformConfig:
    auto_detect: bool = True
    calibration_file: str = "data/calibration.json"
    nav_bar_ratio: float = 0.035
    sidebar_ratio: float = 0.22
    avatar_ratio: float = 0.2
    msg_avatar_ratio: float = 0.04


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "logs/wechat_monitor.log"


@dataclass
class AppConfig:
    wechat: WeChatConfig = field(default_factory=WeChatConfig)
    monitored: List[MonitoredContact] = field(default_factory=list)
    ocr: OCRConfig = field(default_factory=OCRConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    platform: PlatformConfig = field(default_factory=PlatformConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    base_dir: str = ""


class ConfigManager:
    """Loads and validates YAML configuration."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._find_config()
        self.config: AppConfig = self._load()

    def _find_config(self) -> str:
        candidates = [
            Path("config.yaml"),
            Path("config.local.yaml"),
            Path(__file__).parent.parent / "config.yaml",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate.resolve())
        raise FileNotFoundError(
            "No config.yaml found. Create one from the template in README."
        )

    def _load(self) -> AppConfig:
        path = Path(self.config_path)
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        merged = self._deep_merge(DEFAULT_CONFIG, raw)
        self._validate(merged)

        base_dir = str(path.parent.resolve())

        monitored = [
            MonitoredContact(name=m["name"], type=m["type"])
            for m in merged.get("monitored", [])
        ]

        return AppConfig(
            wechat=WeChatConfig(**merged["wechat"]),
            monitored=monitored,
            ocr=OCRConfig(**merged["ocr"]),
            storage=StorageConfig(**merged["storage"]),
            platform=PlatformConfig(**merged["platform"]),
            logging=LoggingConfig(**merged["logging"]),
            base_dir=base_dir,
        )

    def _deep_merge(self, base: dict, override: dict) -> dict:
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _validate(self, raw: dict) -> None:
        wechat = raw.get("wechat", {})
        interval = wechat.get("polling_interval_seconds", 30)
        if not isinstance(interval, (int, float)) or interval < 1:
            raise ValueError(f"polling_interval_seconds must be >= 1, got {interval}")

        for i, m in enumerate(raw.get("monitored", [])):
            if "name" not in m or "type" not in m:
                raise ValueError(f"monitored[{i}] must have 'name' and 'type'")
            if m["type"] not in VALID_CONTACT_TYPES:
                raise ValueError(
                    f"monitored[{i}].type must be one of {VALID_CONTACT_TYPES}, got '{m['type']}'"
                )

        ocr = raw.get("ocr", {})
        if ocr.get("engine") not in VALID_OCR_ENGINES:
            raise ValueError(f"ocr.engine must be one of {VALID_OCR_ENGINES}")
        threshold = ocr.get("confidence_threshold", 0.6)
        if not 0 <= threshold <= 1:
            raise ValueError(f"ocr.confidence_threshold must be in [0, 1], got {threshold}")

        log_level = raw.get("logging", {}).get("level", "INFO")
        if log_level not in VALID_LOG_LEVELS:
            raise ValueError(f"logging.level must be one of {VALID_LOG_LEVELS}")

    def resolve_path(self, relative_path: str) -> str:
        """Resolve a config-relative path against the project base directory."""
        p = Path(relative_path)
        if p.is_absolute():
            return str(p)
        return str(Path(self.config.base_dir) / p)

    def ensure_directories(self) -> None:
        """Create all required data directories."""
        dirs = [
            self.resolve_path(self.config.storage.screenshots_dir),
            self.resolve_path(self.config.storage.attachments_dir),
            self.resolve_path(self.config.storage.debug_dir),
            str(Path(self.resolve_path(self.config.logging.file)).parent),
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)
