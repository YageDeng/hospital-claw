"""Debug script to inspect badge detection and OCR on the chat list."""
import sys
import os
import logging

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

from src.config import ConfigManager
from src.platform_adapter import create_adapter
from src.capture import ScreenCapture
from src.detector import UnreadDetector, RED_LOWER_1, RED_UPPER_1, RED_LOWER_2, RED_UPPER_2
from src.ocr_engine import create_ocr_engine

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)

cfg_mgr = ConfigManager("config.yaml")
cfg = cfg_mgr.config
cfg_mgr.ensure_directories()

adapter = create_adapter()
ocr = create_ocr_engine(cfg.ocr.engine, languages=cfg.ocr.languages)

print(f"\nMonitored: {[m.name for m in cfg.monitored]}")

found = adapter.find_wechat_window(cfg.wechat.window_title)
print(f"Window found: {found}")
if not found:
    sys.exit(1)

rect = adapter.get_window_rect()
print(f"Window rect: {rect}")

screenshots_dir = cfg_mgr.resolve_path(cfg.storage.screenshots_dir)
capture = ScreenCapture(adapter, screenshots_dir)

chat_list_img = capture.capture_chat_list(save=True)
print(f"Chat list shape: {chat_list_img.shape}")

# Analyze red content in the chat list
hsv = cv2.cvtColor(chat_list_img, cv2.COLOR_BGR2HSV)
mask1 = cv2.inRange(hsv, RED_LOWER_1, RED_UPPER_1)
mask2 = cv2.inRange(hsv, RED_LOWER_2, RED_UPPER_2)
red_mask = cv2.bitwise_or(mask1, mask2)
red_pixels = cv2.countNonZero(red_mask)
total_pixels = chat_list_img.shape[0] * chat_list_img.shape[1]
print(f"\nRed pixel analysis: {red_pixels} red pixels out of {total_pixels} ({red_pixels/total_pixels*100:.3f}%)")

# Find contours on red mask
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel)
red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel)
contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
print(f"Red contours found: {len(contours)}")

for i, cnt in enumerate(contours[:20]):
    area = cv2.contourArea(cnt)
    x, y, w, h = cv2.boundingRect(cnt)
    perimeter = cv2.arcLength(cnt, True)
    circularity = 4 * np.pi * area / (perimeter ** 2) if perimeter > 0 else 0
    print(f"  Contour {i}: area={area:.0f} pos=({x},{y}) size=({w}x{h}) circ={circularity:.2f}")

# Run OCR on chat list to see all readable text
print("\n=== OCR on chat list (top portion) ===")
h = chat_list_img.shape[0]
top_portion = chat_list_img[:min(h, 800), :]
regions = ocr.detect_regions(top_portion)
print(f"Found {len(regions)} text regions")
for r in regions[:20]:
    print(f"  \"{r['text']}\" (conf={r['confidence']:.2f}, bbox={r['bbox']})")

# Save red mask for inspection
cv2.imwrite(os.path.join(screenshots_dir, "debug_red_mask.png"), red_mask)
print(f"\nSaved red mask to {screenshots_dir}/debug_red_mask.png")
