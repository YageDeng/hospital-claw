"""Pluggable OCR engine interface with Tesseract and EasyOCR implementations.

Refactored from wechat-router/src/ocr_engine.py with dependency-injection
support so engines can be tested without real OCR backends.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Union

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


class OCREngine(ABC):
    """Abstract OCR interface — swap implementations without touching callers."""

    @abstractmethod
    def recognize(self, image: Union[np.ndarray, Image.Image]) -> str:
        """Run OCR on an image and return the recognized text."""

    @abstractmethod
    def confidence(self, image: Union[np.ndarray, Image.Image]) -> float:
        """Return overall OCR confidence for the image (0.0-1.0)."""

    @abstractmethod
    def detect_regions(self, image: Union[np.ndarray, Image.Image]) -> list[dict]:
        """Detect text regions. Each dict has 'text', 'confidence', 'bbox' (x,y,w,h)."""


def _to_pil(image: Union[np.ndarray, Image.Image]) -> Image.Image:
    if isinstance(image, np.ndarray):
        return Image.fromarray(image)
    return image


def _to_numpy(image: Union[np.ndarray, Image.Image]) -> np.ndarray:
    if isinstance(image, Image.Image):
        return np.array(image)
    return image


class TesseractEngine(OCREngine):
    """Tesseract OCR via pytesseract.

    Pass *pytesseract_module* to inject a fake for testing.
    """

    DEFAULT_TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    def __init__(
        self,
        languages: str = "chi_sim+eng",
        tesseract_cmd: str | None = None,
        pytesseract_module: Any = None,
    ):
        if pytesseract_module is not None:
            self._pytesseract = pytesseract_module
        else:
            import pytesseract as _pytesseract
            cmd = tesseract_cmd or self.DEFAULT_TESSERACT_CMD
            if os.path.isfile(cmd):
                _pytesseract.pytesseract.tesseract_cmd = cmd
            self._pytesseract = _pytesseract

        self.languages = languages
        self._config = "--oem 3 --psm 6"

    def recognize(self, image: Union[np.ndarray, Image.Image]) -> str:
        pil_img = _to_pil(image)
        text = self._pytesseract.image_to_string(
            pil_img, lang=self.languages, config=self._config,
        )
        return text.strip()

    def confidence(self, image: Union[np.ndarray, Image.Image]) -> float:
        pil_img = _to_pil(image)
        data = self._pytesseract.image_to_data(
            pil_img,
            lang=self.languages,
            config=self._config,
            output_type=self._pytesseract.Output.DICT,
        )
        confidences = [
            int(c)
            for c in data["conf"]
            if str(c).lstrip("-").isdigit() and int(c) >= 0
        ]
        if not confidences:
            return 0.0
        return sum(confidences) / (len(confidences) * 100.0)

    def detect_regions(self, image: Union[np.ndarray, Image.Image]) -> list[dict]:
        pil_img = _to_pil(image)
        data = self._pytesseract.image_to_data(
            pil_img,
            lang=self.languages,
            config=self._config,
            output_type=self._pytesseract.Output.DICT,
        )
        regions: list[dict] = []
        n = len(data["text"])
        for i in range(n):
            text = data["text"][i].strip()
            raw_conf = data["conf"][i]
            conf = int(raw_conf) if str(raw_conf).lstrip("-").isdigit() else -1
            if text and conf >= 0:
                regions.append({
                    "text": text,
                    "confidence": conf / 100.0,
                    "bbox": (
                        data["left"][i],
                        data["top"][i],
                        data["width"][i],
                        data["height"][i],
                    ),
                })
        return regions


class EasyOCREngine(OCREngine):
    """EasyOCR implementation — no system dependency, supports Chinese out of the box.

    Pass *reader* to inject a fake for testing.
    """

    def __init__(self, languages: str = "chi_sim+eng", reader: Any = None):
        if reader is not None:
            self._reader = reader
        else:
            import easyocr
            lang_map = {"chi_sim": "ch_sim", "chi_tra": "ch_tra", "eng": "en"}
            lang_list = [lang_map.get(lang, lang) for lang in languages.split("+")]
            logger.info(
                "Initializing EasyOCR with languages: %s (may download models on first run)",
                lang_list,
            )
            self._reader = easyocr.Reader(lang_list, gpu=False)

    def recognize(self, image: Union[np.ndarray, Image.Image]) -> str:
        arr = _to_numpy(image)
        results = self._reader.readtext(arr, detail=0)
        return " ".join(results).strip()

    def confidence(self, image: Union[np.ndarray, Image.Image]) -> float:
        arr = _to_numpy(image)
        results = self._reader.readtext(arr)
        if not results:
            return 0.0
        confs = [r[2] for r in results]
        return sum(confs) / len(confs)

    def detect_regions(self, image: Union[np.ndarray, Image.Image]) -> list[dict]:
        arr = _to_numpy(image)
        results = self._reader.readtext(arr)
        regions: list[dict] = []
        for bbox, text, conf in results:
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            x, y = int(min(xs)), int(min(ys))
            w, h = int(max(xs) - x), int(max(ys) - y)
            regions.append({
                "text": text,
                "confidence": conf,
                "bbox": (x, y, w, h),
            })
        return regions


def create_ocr_engine(engine_name: str = "tesseract", **kwargs: Any) -> OCREngine:
    """Factory function for OCR engines."""
    engines: dict[str, type[OCREngine]] = {
        "tesseract": TesseractEngine,
        "easyocr": EasyOCREngine,
    }
    if engine_name not in engines:
        raise ValueError(
            f"Unknown OCR engine '{engine_name}'. Available: {list(engines)}"
        )
    return engines[engine_name](**kwargs)
