"""Window capture service with region extraction and overlay exclusion.

Finds a target window via the profile's WindowMatcher list, captures it
(masking out the app's own overlay region), and optionally crops per-field
capture regions defined in the profile.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from treatment_app.schemas import CaptureRegion, RegionLocator, TargetAppProfile
from treatment_app.shared.windows import DesktopWindow, WindowsDesktopAutomation

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CaptureResult:
    """Output of a single capture pass."""

    window: DesktopWindow
    full_image: np.ndarray
    region_images: dict[str, np.ndarray] = field(default_factory=dict)


class CaptureService:
    """Captures the target window and crops per-field regions."""

    def __init__(
        self,
        automation: WindowsDesktopAutomation,
        overlay_region: Optional[RegionLocator] = None,
    ) -> None:
        self._automation = automation
        self._overlay_region = overlay_region

    def capture(self, profile: TargetAppProfile) -> Optional[CaptureResult]:
        """Find the target window, capture it, and crop regions.

        Returns None if no matching window is found.
        """
        window = self._automation.find_window(profile.window_matchers)
        if window is None:
            logger.warning("No window matched profile '%s'", profile.profile_id)
            return None

        excluded = [self._overlay_region] if self._overlay_region else []
        full_image = self._automation.capture_window(window, excluded_regions=excluded)

        region_images: dict[str, np.ndarray] = {}
        for cr in profile.capture_regions:
            cropped = _safe_crop(full_image, cr)
            if cropped is not None:
                key = cr.field_id or cr.region_id
                region_images[key] = cropped

        logger.info(
            "Captured '%s' (%dx%d), %d region crop(s)",
            window.title,
            full_image.shape[1],
            full_image.shape[0],
            len(region_images),
        )
        return CaptureResult(
            window=window,
            full_image=full_image,
            region_images=region_images,
        )


def _safe_crop(image: np.ndarray, region: CaptureRegion) -> Optional[np.ndarray]:
    """Crop a region from an image, clamping to image bounds."""
    h, w = image.shape[:2]
    x1 = max(0, region.x)
    y1 = max(0, region.y)
    x2 = min(w, region.x + region.width)
    y2 = min(h, region.y + region.height)
    if x2 <= x1 or y2 <= y1:
        logger.warning("Region '%s' falls outside image bounds", region.region_id)
        return None
    return image[y1:y2, x1:x2].copy()
