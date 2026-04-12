"""Field-by-field form filler using profile locators.

Fills approved fields back into a target app following the locator
priority: UI control -> anchor-relative -> saved region -> dynamic fallback.
Each fill step logs the result for audit.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Protocol

from treatment_app.schemas import (
    AnchorLocator,
    ControlLocator,
    FieldLocator,
    LocatorStrategy,
    RegionLocator,
    TargetAppProfile,
    TreatmentPlanCase,
)
from treatment_app.shared.windows import DesktopWindow, WindowsDesktopAutomation

logger = logging.getLogger(__name__)


class FillStatus(str, Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(slots=True)
class FillRecord:
    field_id: str
    value: Any
    strategy_used: Optional[str]
    status: FillStatus
    error: Optional[str] = None


@dataclass(slots=True)
class FillResult:
    records: list[FillRecord] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.records if r.status == FillStatus.SUCCESS)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.records if r.status == FillStatus.FAILED)


class UIControlDriver(Protocol):
    """Protocol for UI-automation control interaction (e.g. via pywinauto)."""

    def set_value(self, locator: ControlLocator, value: Any) -> bool: ...


Typer = Callable[[Any], None]


class FormFiller:
    """Fill approved fields into the target app one-by-one.

    Parameters
    ----------
    automation : shared desktop automation for click/type.
    ui_driver : optional pywinauto-style driver for UI-control locators.
    typer : callable that types a value into the currently focused control.
    inter_field_delay : seconds to wait between filling consecutive fields.
    """

    def __init__(
        self,
        automation: WindowsDesktopAutomation,
        ui_driver: Optional[UIControlDriver] = None,
        typer: Optional[Typer] = None,
        inter_field_delay: float = 0.3,
    ) -> None:
        self._automation = automation
        self._ui_driver = ui_driver
        self._typer = typer or _default_typer
        self._delay = inter_field_delay

    def fill(
        self,
        case: TreatmentPlanCase,
        profile: TargetAppProfile,
        window: DesktopWindow,
    ) -> FillResult:
        """Fill all approved fields into *window* following locator priority."""
        approved = case.approved_fill_values()
        if not approved:
            logger.info("No approved fields to fill")
            return FillResult()

        ordered_entries = sorted(
            (
                (field_id, profile.fill_locators[field_id])
                for field_id in approved
                if field_id in profile.fill_locators
            ),
            key=lambda pair: pair[1].fill_order,
        )

        result = FillResult()

        for field_id, locator in ordered_entries:
            value = approved[field_id]
            record = self._fill_field(field_id, value, locator, window)
            result.records.append(record)
            if record.status == FillStatus.SUCCESS:
                time.sleep(self._delay)

        skipped_ids = set(approved) - {fid for fid, _ in ordered_entries}
        for field_id in sorted(skipped_ids):
            result.records.append(
                FillRecord(
                    field_id=field_id,
                    value=approved[field_id],
                    strategy_used=None,
                    status=FillStatus.SKIPPED,
                    error="no locator defined",
                )
            )

        logger.info(
            "Fill complete: %d success, %d failed, %d skipped",
            result.success_count,
            result.failed_count,
            len(result.records) - result.success_count - result.failed_count,
        )
        return result

    def _fill_field(
        self,
        field_id: str,
        value: Any,
        locator: FieldLocator,
        window: DesktopWindow,
    ) -> FillRecord:
        for strategy in locator.ordered_strategies():
            try:
                ok = self._try_strategy(strategy, locator, value, window)
                if ok:
                    logger.info("Filled '%s' via %s", field_id, strategy.value)
                    return FillRecord(
                        field_id=field_id,
                        value=value,
                        strategy_used=strategy.value,
                        status=FillStatus.SUCCESS,
                    )
            except Exception as exc:
                logger.warning(
                    "Strategy %s failed for '%s': %s", strategy.value, field_id, exc
                )

        return FillRecord(
            field_id=field_id,
            value=value,
            strategy_used=None,
            status=FillStatus.FAILED,
            error="all locator strategies exhausted",
        )

    def _try_strategy(
        self,
        strategy: LocatorStrategy,
        locator: FieldLocator,
        value: Any,
        window: DesktopWindow,
    ) -> bool:
        if strategy == LocatorStrategy.UI_CONTROL:
            if self._ui_driver and locator.control:
                return self._ui_driver.set_value(locator.control, value)
            return False

        if strategy == LocatorStrategy.ANCHOR:
            if locator.anchor:
                self._automation.click_relative(
                    window,
                    locator.anchor.offset_x,
                    locator.anchor.offset_y,
                )
                self._typer(value)
                return True
            return False

        if strategy == LocatorStrategy.REGION:
            if locator.region:
                cx = locator.region.x + locator.region.width // 2
                cy = locator.region.y + locator.region.height // 2
                self._automation.click_relative(window, cx, cy)
                self._typer(value)
                return True
            return False

        if strategy == LocatorStrategy.DYNAMIC:
            logger.info("Dynamic fallback not yet implemented")
            return False

        return False



def _default_typer(value: Any) -> None:
    """Type a value into the currently focused control via pyautogui."""
    import pyautogui
    text = str(value)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.05)
    if text.isascii():
        pyautogui.typewrite(text, interval=0.02)
    else:
        import pyperclip
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.05)
