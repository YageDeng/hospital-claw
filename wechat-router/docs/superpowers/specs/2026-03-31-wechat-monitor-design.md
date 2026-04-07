# WeChat Monitor — Design Spec

**Date:** 2026-03-31
**Status:** Approved

## Overview

A cross-platform (Windows + macOS) GUI automation tool that continuously monitors the WeChat desktop app for unread messages from a configurable list of contacts/groups. It captures all message types via screenshot + OCR, and stores structured results in a SQLite database.

## Requirements

- **Platforms:** Windows 10+ and macOS (WeChat official desktop clients)
- **Monitoring:** Continuous background polling (configurable interval, default 30s)
- **Scope:** Configurable list of contacts and groups
- **Content types:** Text, images, files, links, voice (duration), video (thumbnail), stickers
- **Language:** Chinese (Simplified) primary, English secondary
- **Storage:** SQLite database + file system for attachments/screenshots
- **Privacy:** Fully offline — no data leaves the machine

## Architecture

```
┌─────────────┐    ┌──────────────┐    ┌───────────────┐    ┌────────────┐    ┌──────────┐
│  Screenshot  │───▶│  Detect      │───▶│  Open Chat &  │───▶│  OCR /     │───▶│  Store   │
│  Capture     │    │  Unread      │    │  Capture      │    │  Parse     │    │  in DB   │
│              │    │  Badges      │    │  Messages     │    │  Content   │    │          │
└─────────────┘    └──────────────┘    └───────────────┘    └────────────┘    └──────────┘
```

### Components

| Component | Module | Responsibility |
|---|---|---|
| ScreenCapture | `capture.py` | Takes screenshots of the WeChat window (not full screen) |
| UnreadDetector | `detector.py` | Finds unread badges on monitored contacts/groups in the chat list |
| ChatNavigator | `navigator.py` | Clicks into a chat and scrolls to capture the message area |
| ContentExtractor | `extractor.py` | OCR on message regions, classifies content type |
| OCREngine | `ocr_engine.py` | Pluggable OCR interface, default Tesseract implementation |
| StorageManager | `storage.py` | SQLite database operations, deduplication |
| ConfigManager | `config.py` | YAML config loading and validation |
| PlatformAdapter | `platform_adapter.py` | Abstracts Windows/macOS differences |

## Data Model

### SQLite Schema

```sql
CREATE TABLE contacts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    type        TEXT NOT NULL CHECK(type IN ('contact', 'group')),
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id      INTEGER NOT NULL REFERENCES contacts(id),
    sender          TEXT,
    content_type    TEXT NOT NULL CHECK(content_type IN ('text', 'image', 'file', 'link', 'voice', 'video', 'sticker', 'other')),
    text_content    TEXT,
    timestamp_ocr   TEXT,
    captured_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    content_hash    TEXT UNIQUE,
    raw_screenshot  TEXT
);

CREATE TABLE attachments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id  INTEGER NOT NULL REFERENCES messages(id),
    file_type   TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    file_name   TEXT,
    saved_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Deduplication

Messages are deduplicated via `content_hash` — a hash of `(contact_name, sender, text_content, timestamp_ocr)`. Duplicate inserts are silently skipped.

## Platform Adapter

### Interface

```python
class PlatformAdapter:
    def find_wechat_window()       # locate and bring WeChat to front
    def capture_window()           # screenshot just the WeChat window
    def get_chat_list_region()     # region of the sidebar
    def get_message_area_region()  # region of the main message display
    def click(x, y)               # click at coordinates within the window
    def scroll(direction, amount)  # scroll within a region
```

### Windows Implementation

- `pygetwindow` to find WeChat by window title
- `pyautogui` for screenshots and input
- Templates in `templates/windows/`

### macOS Implementation

- `pygetwindow` or AppleScript for window management
- `pyautogui` for screenshots and input
- Templates in `templates/macos/`

### Calibration

First-run calibration auto-detects window regions and saves coordinates to `data/calibration.json`. Multi-scale template matching handles DPI/resolution differences.

## UI Interaction Flow

1. **Find WeChat window** — locate and activate
2. **Screenshot chat list** — capture the left sidebar
3. **Detect unread badges** — template match for red dot/number badges
4. **Match contact names** — OCR the name next to each badge, fuzzy-match against config
5. **Click into chat** — navigate to the matched chat
6. **Capture message area** — screenshot the message display region
7. **Scroll for older messages** — scroll up until hitting already-captured messages
8. **Return to chat list** — navigate back and process next unread chat

## Content Extraction Pipeline

### Per-message bubble:

1. **Crop** — OpenCV contour detection to isolate each message bubble
2. **Preprocess** — Grayscale, adaptive threshold, denoise, upscale small text 2x
3. **Classify** content type:
   - Text: OCR returns meaningful characters
   - Image: Large bubble, low OCR confidence, high color variance
   - Sticker/Emoji: Small square, very low OCR confidence
   - Link: URL patterns or link card template match
   - File: File icon template match
   - Voice: Voice waveform icon template match
   - Video: Play button overlay template match
4. **Extract** content per type:
   - Text → Tesseract `chi_sim+eng`
   - Image → Save to attachments directory
   - Link → OCR title + URL text
   - File → OCR filename
   - Voice → OCR duration label
   - Video → Save thumbnail

### Sender Detection (Group Chats)

- Sender name appears above left-side message bubbles
- OCR the region above each left-side bubble
- Right-side bubbles are the logged-in user ("self")

### Timestamp Extraction

- WeChat shows timestamps as centered gray text between message groups
- Detect and associate with nearby messages

## OCR Engine

### Interface

```python
class OCREngine:
    def recognize(image) -> str
    def confidence(image) -> float
    def detect_regions(image) -> list
```

Default: Tesseract with `chi_sim+eng` language pack.
Pluggable: Can be swapped for PaddleOCR or cloud APIs.

## Configuration

```yaml
wechat:
  polling_interval_seconds: 30
  window_title: "WeChat"

monitored:
  - name: "张三"
    type: contact
  - name: "工作群"
    type: group

ocr:
  engine: tesseract
  languages: "chi_sim+eng"
  confidence_threshold: 0.6

storage:
  database_path: "data/wechat_monitor.db"
  screenshots_dir: "data/screenshots"
  attachments_dir: "data/attachments"

platform:
  auto_detect: true
  calibration_file: "data/calibration.json"

logging:
  level: INFO
  file: "logs/wechat_monitor.log"
```

## Error Handling

| Scenario | Behavior |
|---|---|
| WeChat window not found | Log warning, retry next cycle |
| OCR empty/low confidence | Save raw screenshot, store as `content_type: other` |
| Template match failure | Log with screenshot, skip element |
| SQLite write conflict | Retry with exponential backoff (3 attempts) |
| Duplicate message | Skip silently |
| Unrecoverable crash | Log traceback, restart after 60s cooldown |

## Project Structure

```
wechat-monitor/
├── config.yaml
├── requirements.txt
├── README.md
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── capture.py
│   ├── detector.py
│   ├── navigator.py
│   ├── extractor.py
│   ├── ocr_engine.py
│   ├── storage.py
│   ├── platform_adapter.py
│   └── utils.py
├── templates/
│   ├── windows/
│   └── macos/
├── data/
├── logs/
└── tests/
    ├── test_extractor.py
    ├── test_storage.py
    └── test_detector.py
```

## Dependencies

- `pyautogui` — GUI automation, screenshots, mouse/keyboard
- `pygetwindow` — window management
- `opencv-python` — image processing, template matching, contour detection
- `pytesseract` — Tesseract OCR Python wrapper
- `Pillow` — image manipulation
- `pyyaml` — config file parsing
- `thefuzz[speedup]` — fuzzy string matching for contact names

System dependency: Tesseract OCR with `chi_sim` language pack.

## CLI

```bash
python src/main.py                # continuous monitoring
python src/main.py --once         # single scan and exit
python src/main.py --calibrate    # first-time calibration
```
