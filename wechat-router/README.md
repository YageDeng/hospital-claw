# WeChat Monitor

A cross-platform (Windows + macOS) GUI automation tool that continuously monitors the WeChat desktop app for unread messages from a configurable list of contacts/groups. It captures all message types via screenshot + OCR and stores structured results in a SQLite database.

## Features

- Continuous background polling with configurable interval
- Monitors specific contacts and groups
- Handles text, images, files, links, voice, video, and stickers
- Chinese (Simplified) + English OCR support
- SQLite storage with automatic deduplication
- Fully offline — no data leaves your machine

## Prerequisites

- Python 3.10+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed with `chi_sim` language pack
- WeChat desktop client installed and logged in

### Install Tesseract

**Windows:** Download installer from [UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki) and add to PATH.

**macOS:** `brew install tesseract tesseract-lang`

## Installation

```bash
python -m venv venv

# Windows
venv\Scripts\activate
# macOS
source venv/bin/activate

pip install -r requirements.txt
```

## Configuration

Edit `config.yaml` to set your monitored contacts/groups:

```yaml
monitored:
  - name: "张三"
    type: contact
  - name: "工作群"
    type: group
```

## Usage

```bash
# First-time calibration (detects WeChat window regions)
python src/main.py --calibrate

# Continuous monitoring
python src/main.py

# Single scan and exit
python src/main.py --once
```

## Project Structure

```
wechat-monitor/
├── config.yaml          # Monitoring configuration
├── requirements.txt     # Python dependencies
├── src/
│   ├── main.py          # CLI entry point
│   ├── config.py        # Config loading/validation
│   ├── capture.py       # Screenshot capture
│   ├── detector.py      # Unread badge detection
│   ├── navigator.py     # Chat navigation
│   ├── extractor.py     # Content extraction & classification
│   ├── ocr_engine.py    # OCR interface (Tesseract)
│   ├── storage.py       # SQLite database operations
│   ├── platform_adapter.py  # Windows/macOS abstraction
│   └── utils.py         # Shared utilities
├── templates/           # Template images for matching
│   ├── windows/
│   └── macos/
├── data/                # Runtime data (gitignored)
├── logs/                # Log files (gitignored)
└── tests/               # Test suite
```
