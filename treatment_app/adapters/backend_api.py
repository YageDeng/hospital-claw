"""Backend API adapter for fetching / pushing patient and case data.

Provides a protocol-based interface so callers don't depend on HTTP details.
The default implementation uses ``requests`` with retry and timeout.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional, Protocol

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 1.0


class BackendAPI(Protocol):
    """Protocol for backend data access."""

    def fetch_patient(self, patient_id: str) -> dict[str, Any]: ...
    def submit_case(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class HTTPBackendAPI:
    """REST backend adapter with retry and timeout.

    Parameters
    ----------
    base_url : root URL of the backend (e.g. ``http://10.0.0.1:8080/api``).
    api_key : optional bearer token.
    timeout : request timeout in seconds.
    max_retries / backoff : retry policy for transient errors.
    http_client : injectable requests-like object for testing.
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_RETRIES,
        backoff: float = DEFAULT_BACKOFF,
        http_client: Any = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff = backoff
        self._http = http_client

    def _get_http(self) -> Any:
        if self._http is not None:
            return self._http
        import requests
        self._http = requests.Session()
        return self._http

    def fetch_patient(self, patient_id: str) -> dict[str, Any]:
        url = f"{self._base}/patients/{patient_id}"
        return self._get_json("GET", url)

    def submit_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base}/cases"
        return self._get_json("POST", url, json_body=payload)

    def _get_json(
        self,
        method: str,
        url: str,
        json_body: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        last_exc: Optional[Exception] = None
        http = self._get_http()
        for attempt in range(1, self._max_retries + 1):
            try:
                resp = http.request(
                    method,
                    url,
                    headers=self._headers,
                    json=json_body,
                    timeout=self._timeout,
                )
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:
                last_exc = exc
                wait = self._backoff * (2 ** (attempt - 1))
                logger.warning(
                    "Backend %s %s attempt %d/%d failed: %s — retrying in %.1fs",
                    method, url, attempt, self._max_retries, exc, wait,
                )
                time.sleep(wait)
        raise RuntimeError(f"Backend request failed after {self._max_retries} retries") from last_exc
