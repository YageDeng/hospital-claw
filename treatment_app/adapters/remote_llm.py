"""Remote LLM adapter for treatment-plan optimization.

Sends a structured JSON request to the LLM endpoint and validates the
response against the case schema before returning.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional, Protocol

from treatment_app.schemas import TreatmentPlanCase

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 2
DEFAULT_BACKOFF = 2.0


class LLMClient(Protocol):
    """Protocol for the raw LLM call — injectable for testing."""

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class RemoteLLMAdapter:
    """Send a TreatmentPlanCase to a remote LLM and apply the optimized response.

    Parameters
    ----------
    llm_client : any object implementing the ``LLMClient`` protocol.
    max_retries / backoff : retry policy for LLM calls.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        max_retries: int = DEFAULT_RETRIES,
        backoff: float = DEFAULT_BACKOFF,
    ) -> None:
        self._client = llm_client
        self._max_retries = max_retries
        self._backoff = backoff

    def optimize(self, case: TreatmentPlanCase) -> TreatmentPlanCase:
        """Send the case to the LLM, validate the response, and apply it.

        Raises ValueError if the LLM returns an invalid response after
        all retries are exhausted.
        """
        payload = case.to_llm_payload()
        last_exc: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                raw_response = self._client.complete(payload)
                response = self._validate_response(raw_response)
                case.apply_llm_response(response)
                logger.info("LLM optimization applied on attempt %d", attempt)
                return case
            except (ValueError, KeyError, TypeError) as exc:
                last_exc = exc
                logger.warning(
                    "LLM response invalid on attempt %d/%d: %s",
                    attempt, self._max_retries, exc,
                )
                if attempt < self._max_retries:
                    time.sleep(self._backoff * (2 ** (attempt - 1)))
            except Exception as exc:
                last_exc = exc
                logger.error("LLM call failed on attempt %d/%d: %s", attempt, self._max_retries, exc)
                if attempt < self._max_retries:
                    time.sleep(self._backoff * (2 ** (attempt - 1)))

        raise ValueError(
            f"LLM optimization failed after {self._max_retries} retries"
        ) from last_exc

    def _validate_response(self, raw: Any) -> dict[str, Any]:
        """Ensure the response has the required top-level keys."""
        if not isinstance(raw, dict):
            raise ValueError("LLM response must be a JSON object")
        for key in ("caseId", "profileId", "optimizedFields"):
            if key not in raw:
                raise ValueError(f"LLM response missing required key '{key}'")
        if not isinstance(raw["optimizedFields"], dict):
            raise ValueError("optimizedFields must be a JSON object")
        if "warnings" not in raw:
            raw["warnings"] = []
        return raw
