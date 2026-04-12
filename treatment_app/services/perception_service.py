"""OCR-first perception pipeline with optional VLM escalation.

Runs OCR on the full image and per-field regions, collects per-field text
and confidence scores.  When confidence is below the threshold for a field,
the field is flagged for VLM escalation (if a VLM adapter is provided).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

import numpy as np

from treatment_app.shared.ocr import OCREngine

logger = logging.getLogger(__name__)

DEFAULT_CONFIDENCE_THRESHOLD = 0.70


@dataclass(slots=True)
class FieldExtraction:
    """Extraction result for a single field."""

    field_id: str
    text: str
    confidence: float
    source: str  # "ocr" | "vlm" | "region_ocr"


@dataclass(slots=True)
class PerceptionResult:
    """Aggregated output of the perception pipeline."""

    full_text: str
    full_confidence: float
    field_extractions: dict[str, FieldExtraction] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class VLMAdapter(Protocol):
    """Protocol for optional VLM escalation."""

    def extract_field(
        self, image: np.ndarray, field_id: str, prompt_hint: Optional[str]
    ) -> FieldExtraction: ...


class PerceptionService:
    """OCR-first pipeline with optional VLM escalation on low confidence."""

    def __init__(
        self,
        ocr_engine: OCREngine,
        vlm_adapter: Optional[VLMAdapter] = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> None:
        self._ocr = ocr_engine
        self._vlm = vlm_adapter
        self._threshold = confidence_threshold

    def extract(
        self,
        full_image: np.ndarray,
        region_images: Optional[dict[str, np.ndarray]] = None,
        field_hints: Optional[dict[str, str]] = None,
    ) -> PerceptionResult:
        """Run the full perception pipeline.

        Parameters
        ----------
        full_image : the captured window screenshot.
        region_images : per-field cropped images keyed by field_id.
        field_hints : optional prompt hints per field_id (for VLM).
        """
        full_text = self._ocr.recognize(full_image)
        full_confidence = self._ocr.confidence(full_image)

        result = PerceptionResult(
            full_text=full_text,
            full_confidence=full_confidence,
        )

        region_images = region_images or {}
        field_hints = field_hints or {}

        for field_id, region_img in region_images.items():
            extraction = self._extract_field_ocr(field_id, region_img)

            if extraction.confidence < self._threshold:
                result.warnings.append(
                    f"Low OCR confidence ({extraction.confidence:.0%}) for field '{field_id}'"
                )
                if self._vlm is not None:
                    try:
                        vlm_extraction = self._vlm.extract_field(
                            region_img,
                            field_id,
                            field_hints.get(field_id),
                        )
                        if vlm_extraction.confidence > extraction.confidence:
                            extraction = vlm_extraction
                            logger.info(
                                "VLM improved '%s': %.0f%% -> %.0f%%",
                                field_id,
                                extraction.confidence * 100,
                                vlm_extraction.confidence * 100,
                            )
                    except Exception as exc:
                        logger.warning("VLM escalation failed for '%s': %s", field_id, exc)
                        result.warnings.append(f"VLM escalation failed for '{field_id}'")

            result.field_extractions[field_id] = extraction

        return result

    def _extract_field_ocr(self, field_id: str, image: np.ndarray) -> FieldExtraction:
        text = self._ocr.recognize(image)
        confidence = self._ocr.confidence(image)
        return FieldExtraction(
            field_id=field_id,
            text=text,
            confidence=confidence,
            source="region_ocr",
        )
