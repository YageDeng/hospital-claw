"""Map raw perception extractions into a canonical TreatmentPlanCase.

Takes a PerceptionResult plus a TargetAppProfile and produces a
TreatmentPlanCase with fields populated from OCR/VLM extractions,
confidence scores propagated, and low-confidence fields flagged.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from treatment_app.schemas import (
    CaseField,
    CaseSection,
    FieldKind,
    FieldOrigin,
    FieldReviewState,
    TargetAppProfile,
    TreatmentPlanCase,
)
from treatment_app.services.perception_service import PerceptionResult

logger = logging.getLogger(__name__)

DEFAULT_LOW_CONFIDENCE = 0.70


class SchemaMapper:
    """Build a TreatmentPlanCase from perception results and a profile."""

    def __init__(
        self,
        low_confidence_threshold: float = DEFAULT_LOW_CONFIDENCE,
    ) -> None:
        self._low_threshold = low_confidence_threshold

    def map(
        self,
        perception: PerceptionResult,
        profile: TargetAppProfile,
        case_id: Optional[str] = None,
    ) -> TreatmentPlanCase:
        """Create a TreatmentPlanCase from extracted data.

        Fields with per-region extractions get their values; others get None.
        """
        case_id = case_id or f"case-{uuid.uuid4().hex[:8]}"

        section_ids_ordered: list[str] = []
        seen: set[str] = set()
        for fdef in profile.field_definitions:
            if fdef.section_id not in seen:
                section_ids_ordered.append(fdef.section_id)
                seen.add(fdef.section_id)

        section_title_map = {s.section_id: s.title for s in profile.review_sections}

        sections: list[CaseSection] = []
        for sid in section_ids_ordered:
            fields: list[CaseField] = []
            for fdef in profile.field_definitions:
                if fdef.section_id != sid:
                    continue
                extraction = perception.field_extractions.get(fdef.field_id)
                value: Any = None
                confidence: Optional[float] = None
                origin = FieldOrigin.EXTRACTED

                if extraction is not None:
                    value = _coerce(extraction.text, fdef.field_type)
                    confidence = extraction.confidence

                review_state = FieldReviewState.PENDING
                if confidence is not None and confidence < self._low_threshold:
                    review_state = FieldReviewState.BLOCKED

                fields.append(
                    CaseField(
                        field_id=fdef.field_id,
                        label=fdef.label,
                        section_id=sid,
                        field_type=fdef.field_type,
                        value=value,
                        origin=origin,
                        review_state=review_state,
                        confidence=confidence,
                    )
                )

            sections.append(
                CaseSection(
                    section_id=sid,
                    title=section_title_map.get(sid, sid),
                    fields=fields,
                )
            )

        warnings = list(perception.warnings)
        return TreatmentPlanCase(
            case_id=case_id,
            profile_id=profile.profile_id,
            sections=sections,
            warnings=warnings,
        )


def _coerce(text: str, kind: FieldKind) -> Any:
    """Best-effort coercion of OCR text into the declared field type."""
    text = text.strip()
    if not text:
        return None

    if kind == FieldKind.INTEGER:
        try:
            return int(text)
        except ValueError:
            return text
    if kind == FieldKind.DECIMAL:
        try:
            return float(text)
        except ValueError:
            return text
    if kind == FieldKind.BOOLEAN:
        return text.lower() in {"true", "yes", "1", "是"}
    if kind == FieldKind.LIST:
        return [item.strip() for item in text.split(",") if item.strip()]
    return text
