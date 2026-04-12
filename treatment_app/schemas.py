"""Canonical schemas for the Windows treatment app."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class FieldKind(str, Enum):
    TEXT = "text"
    MULTILINE = "multiline"
    INTEGER = "integer"
    DECIMAL = "decimal"
    DATE = "date"
    LIST = "list"
    BOOLEAN = "boolean"
    CHOICE = "choice"


class FieldOrigin(str, Enum):
    EXTRACTED = "extracted"
    INFERRED = "inferred"
    BACKEND = "backend"
    LLM_GENERATED = "llm_generated"
    USER_EDITED = "edited_by_user"


class FieldReviewState(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    FILLED = "filled"


class ReviewControlType(str, Enum):
    SINGLE_LINE = "single_line"
    MULTI_LINE = "multi_line"
    DROPDOWN = "dropdown"
    CHECKBOX = "checkbox"
    READ_ONLY = "read_only"


class LocatorStrategy(str, Enum):
    UI_CONTROL = "ui_control"
    ANCHOR = "anchor"
    REGION = "region"
    DYNAMIC = "dynamic"


@dataclass(slots=True)
class CaseField:
    field_id: str
    label: str
    section_id: str
    field_type: FieldKind
    value: Any = None
    origin: FieldOrigin = FieldOrigin.EXTRACTED
    review_state: FieldReviewState = FieldReviewState.PENDING
    confidence: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_fill_value(self) -> bool:
        if self.value is None:
            return False
        if isinstance(self.value, str):
            return bool(self.value.strip())
        if isinstance(self.value, (list, dict, tuple, set)):
            return bool(self.value)
        return True

    def is_approved_for_fill(self) -> bool:
        return self.review_state == FieldReviewState.APPROVED and self.has_fill_value()


@dataclass(slots=True)
class CaseSection:
    section_id: str
    title: str
    fields: list[CaseField] = field(default_factory=list)

    def to_value_dict(self) -> dict[str, Any]:
        return {item.field_id: item.value for item in self.fields}


@dataclass(slots=True)
class TreatmentPlanCase:
    case_id: str
    profile_id: str
    sections: list[CaseSection]
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        section_ids = set()
        field_ids = set()
        for section in self.sections:
            if section.section_id in section_ids:
                raise ValueError(f"duplicate section_id '{section.section_id}'")
            section_ids.add(section.section_id)
            for item in section.fields:
                if item.section_id != section.section_id:
                    raise ValueError(
                        f"field '{item.field_id}' belongs to section '{item.section_id}', "
                        f"not '{section.section_id}'"
                    )
                if item.field_id in field_ids:
                    raise ValueError(f"duplicate field_id '{item.field_id}'")
                field_ids.add(item.field_id)

    def to_llm_payload(self) -> dict[str, Any]:
        return {
            "caseId": self.case_id,
            "profileId": self.profile_id,
            "sections": {
                section.section_id: section.to_value_dict()
                for section in self.sections
            },
            "warnings": list(self.warnings),
        }

    def field_map(self) -> dict[str, CaseField]:
        result: dict[str, CaseField] = {}
        for section in self.sections:
            for item in section.fields:
                result[item.field_id] = item
        return result

    def approved_fill_values(self) -> dict[str, Any]:
        return {
            field_id: item.value
            for field_id, item in self.field_map().items()
            if item.is_approved_for_fill()
        }

    def apply_llm_response(self, response: dict[str, Any]) -> "TreatmentPlanCase":
        if response.get("caseId") != self.case_id:
            raise ValueError("LLM response caseId does not match the active case")
        if response.get("profileId") != self.profile_id:
            raise ValueError("LLM response profileId does not match the active profile")

        optimized_fields = response.get("optimizedFields")
        if not isinstance(optimized_fields, dict):
            raise ValueError("LLM response must include an 'optimizedFields' object")

        field_map = self.field_map()
        validated_updates: dict[str, Any] = {}
        for field_id, value in optimized_fields.items():
            if field_id not in field_map:
                raise ValueError(f"unknown field_id '{field_id}' in LLM response")
            self._validate_field_value(field_map[field_id], value)
            validated_updates[field_id] = value

        warnings = response.get("warnings", [])
        if warnings is None or not isinstance(warnings, list):
            raise ValueError("LLM response warnings must be a list")

        for field_id, value in validated_updates.items():
            field_map[field_id].value = value
            field_map[field_id].origin = FieldOrigin.LLM_GENERATED
            field_map[field_id].review_state = FieldReviewState.PENDING
        self.warnings = [str(item) for item in warnings]
        return self

    def _validate_field_value(self, field: CaseField, value: Any) -> None:
        if value is None:
            return

        kind = field.field_type
        if kind in {FieldKind.TEXT, FieldKind.MULTILINE, FieldKind.DATE, FieldKind.CHOICE}:
            if not isinstance(value, str):
                raise ValueError(f"field '{field.field_id}' expects string")
            return
        if kind == FieldKind.INTEGER:
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"field '{field.field_id}' expects integer")
            return
        if kind == FieldKind.DECIMAL:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"field '{field.field_id}' expects decimal")
            return
        if kind == FieldKind.LIST:
            if not isinstance(value, list):
                raise ValueError(f"field '{field.field_id}' expects list")
            return
        if kind == FieldKind.BOOLEAN:
            if not isinstance(value, bool):
                raise ValueError(f"field '{field.field_id}' expects boolean")


@dataclass(slots=True)
class FieldDefinition:
    field_id: str
    label: str
    section_id: str
    field_type: FieldKind
    review_control: ReviewControlType
    required: bool = False
    prompt_hint: Optional[str] = None


@dataclass(slots=True)
class WindowMatcher:
    executable_names: list[str] = field(default_factory=list)
    title_patterns: list[str] = field(default_factory=list)
    class_names: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.executable_names or self.title_patterns or self.class_names)


@dataclass(slots=True)
class ReviewSectionLayout:
    section_id: str
    title: str
    order: int
    columns: int = 1
    collapsed: bool = False


@dataclass(slots=True)
class ReviewFieldLayout:
    field_id: str
    section_id: str
    row: int
    column: int
    row_span: int = 1
    column_span: int = 1
    label_override: Optional[str] = None


@dataclass(slots=True)
class RegionLocator:
    x: int
    y: int
    width: int
    height: int


@dataclass(slots=True)
class AnchorLocator:
    text: str
    offset_x: int = 0
    offset_y: int = 0


@dataclass(slots=True)
class ControlLocator:
    automation_id: Optional[str] = None
    name: Optional[str] = None
    control_type: Optional[str] = None
    class_name: Optional[str] = None

    def is_empty(self) -> bool:
        return not any((self.automation_id, self.name, self.control_type, self.class_name))


@dataclass(slots=True)
class CaptureRegion:
    region_id: str
    label: str
    x: int
    y: int
    width: int
    height: int
    field_id: Optional[str] = None


@dataclass(slots=True)
class FieldLocator:
    fill_order: int
    control: Optional[ControlLocator] = None
    anchor: Optional[AnchorLocator] = None
    region: Optional[RegionLocator] = None
    allow_dynamic_fallback: bool = False

    def ordered_strategies(self) -> list[LocatorStrategy]:
        strategies: list[LocatorStrategy] = []
        if self.control:
            strategies.append(LocatorStrategy.UI_CONTROL)
        if self.anchor:
            strategies.append(LocatorStrategy.ANCHOR)
        if self.region:
            strategies.append(LocatorStrategy.REGION)
        if self.allow_dynamic_fallback:
            strategies.append(LocatorStrategy.DYNAMIC)
        return strategies


@dataclass(slots=True)
class TargetAppProfile:
    profile_id: str
    name: str
    window_matchers: list[WindowMatcher]
    field_definitions: list[FieldDefinition]
    review_sections: list[ReviewSectionLayout]
    review_fields: list[ReviewFieldLayout]
    capture_regions: list[CaptureRegion] = field(default_factory=list)
    fill_locators: dict[str, FieldLocator] = field(default_factory=dict)
    version: str = "1.0"

    def field_definition_map(self) -> dict[str, FieldDefinition]:
        return {item.field_id: item for item in self.field_definitions}

    def validate(self) -> "TargetAppProfile":
        if not self.window_matchers:
            raise ValueError("profile must define at least one window matcher")
        if all(item.is_empty() for item in self.window_matchers):
            raise ValueError("window matcher must include at least one selector")

        section_ids: set[str] = set()
        for section in self.review_sections:
            if section.section_id in section_ids:
                raise ValueError("duplicate review section")
            section_ids.add(section.section_id)

        field_map = self.field_definition_map()
        if len(field_map) != len(self.field_definitions):
            raise ValueError("duplicate field definitions are not allowed")
        for field_definition in self.field_definitions:
            if field_definition.section_id not in section_ids:
                raise ValueError(
                    f"field definition section '{field_definition.section_id}' is missing from review sections"
                )

        for layout in self.review_fields:
            if layout.field_id not in field_map:
                raise ValueError(f"unknown field_id '{layout.field_id}' in review layout")
            if layout.section_id not in section_ids:
                raise ValueError(f"unknown section_id '{layout.section_id}' in review layout")
            if field_map[layout.field_id].section_id != layout.section_id:
                raise ValueError(
                    f"field '{layout.field_id}' does not belong to review section '{layout.section_id}'"
                )
        layout_field_ids = [layout.field_id for layout in self.review_fields]
        if len(layout_field_ids) != len(set(layout_field_ids)):
            raise ValueError("duplicate review layout")
        for field_id in field_map:
            if field_id not in layout_field_ids:
                raise ValueError(f"field '{field_id}' is missing review layout")

        seen_orders: dict[int, str] = {}
        for field_id, locator in self.fill_locators.items():
            if field_id not in field_map:
                raise ValueError(f"unknown field_id '{field_id}' in fill locators")
            if locator.control and locator.control.is_empty():
                raise ValueError(f"control locator for field '{field_id}' cannot be empty")
            has_stable_locator = bool(locator.control or locator.anchor or locator.region)
            if not has_stable_locator:
                raise ValueError(f"field '{field_id}' must define at least one stable locator")
            if locator.fill_order in seen_orders:
                raise ValueError("duplicate fill order")
            seen_orders[locator.fill_order] = field_id

        for region in self.capture_regions:
            if region.field_id and region.field_id not in field_map:
                raise ValueError(f"unknown field_id '{region.field_id}' in capture regions")

        return self
