"""Image and OCR text utilities shared between wechat-router and treatment app."""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

_FULLWIDTH_OFFSET = 0xFEE0


def normalize_ocr_text(text: Optional[str]) -> str:
    """Normalize OCR text so slight recognition differences still match.

    Handles: extra whitespace, full-width/half-width, common substitutions,
    stray punctuation, and case differences.
    """
    if not text:
        return ""

    chars = []
    for ch in text:
        cp = ord(ch)
        if 0xFF01 <= cp <= 0xFF5E:
            chars.append(chr(cp - _FULLWIDTH_OFFSET))
        elif cp == 0x3000:
            chars.append(" ")
        else:
            chars.append(ch)
    s = "".join(chars)

    s = unicodedata.normalize("NFKC", s)
    s = s.lower()
    s = s.replace("\u2018", "'").replace("\u2019", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2014", "-").replace("\u2013", "-")
    s = s.replace("\u00b7", ".").replace("\u2022", ".")
    s = re.sub(r"\s+", " ", s).strip()

    return s


def merge_ocr_regions(regions_a: list[dict], regions_b: list[dict]) -> list[dict]:
    """Merge two OCR region lists, dropping near-duplicate bboxes.

    Keeps the higher-confidence detection when two regions overlap.
    Used to combine results from raw and preprocessed OCR passes.
    """
    merged = [dict(r) for r in regions_a]
    for rb in regions_b:
        bx, by, bw, bh = rb["bbox"]
        bc_x, bc_y = bx + bw // 2, by + bh // 2
        is_dup = False
        for ra in merged:
            ax, ay, aw, ah = ra["bbox"]
            ac_x, ac_y = ax + aw // 2, ay + ah // 2
            if abs(bc_x - ac_x) < 20 and abs(bc_y - ac_y) < 20:
                if rb["confidence"] > ra["confidence"]:
                    ra.update(rb)
                is_dup = True
                break
        if not is_dup:
            merged.append(dict(rb))
    return merged
