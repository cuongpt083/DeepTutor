"""Client for interacting with the standalone Laya decision service."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_LAYA_URL = "http://deeptutor-laya:8000/v1/decide"
DEFAULT_TIMEOUT_SECONDS = 0.50  # 500ms strict timeout for System 1 fast path


class LayaClient:
    """Resilient client for Laya decision model with circuit breaker."""

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 30.0):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.consecutive_failures = 0
        self.last_failure_time = 0.0

    def is_circuit_open(self) -> bool:
        if self.consecutive_failures >= self.failure_threshold:
            if time.time() - self.last_failure_time < self.cooldown_seconds:
                return True
            # Cooldown expired, enter half-open state
            self.consecutive_failures = 0
        return False

    def record_success(self) -> None:
        self.consecutive_failures = 0

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        self.last_failure_time = time.time()

    async def should_preseed(
        self,
        user_message: str,
        knowledge_bases: list[str],
        *,
        threshold: float | None = None,
        service_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> bool:
        """Query Laya service to decide whether KB preseed is needed for this query.

        Fails soft: returns False on network error, timeout, or open circuit so
        turn execution never crashes and falls back to runtime RAG tool dispatch.
        """
        if not user_message or not knowledge_bases:
            return False

        if self.is_circuit_open():
            logger.debug("Laya circuit breaker is open. Bypassing preseed.")
            return False

        url = service_url or os.getenv("LAYA_SERVICE_URL", DEFAULT_LAYA_URL)
        thresh = threshold if threshold is not None else float(os.getenv("LAYA_THRESHOLD", "0.70"))

        payload = {
            "user_message": user_message,
            "knowledge_bases": knowledge_bases,
            "threshold": thresh,
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    self.record_success()
                    data: dict[str, Any] = resp.json()
                    should_preseed = bool(data.get("should_preseed", False))
                    conf = data.get("confidence", 0.0)
                    lat = data.get("latency_ms", 0.0)
                    logger.info(
                        "Laya decision: should_preseed=%s (confidence=%.2f, latency=%.1fms)",
                        should_preseed,
                        conf,
                        lat,
                    )
                    return should_preseed
                logger.warning("Laya returned non-200 status code: %d %s", resp.status_code, resp.text)
                self.record_failure()
        except httpx.TimeoutException:
            logger.warning("Laya service timed out after %.2fs. Bypassing preseed.", timeout)
            self.record_failure()
        except Exception as exc:
            logger.warning("Failed to connect to Laya service at %s: %s. Bypassing preseed.", url, exc)
            self.record_failure()

        return False


_default_client = LayaClient()


async def should_preseed_with_laya(
    user_message: str,
    knowledge_bases: list[str],
    *,
    threshold: float | None = None,
    service_url: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> bool:
    return await _default_client.should_preseed(
        user_message,
        knowledge_bases,
        threshold=threshold,
        service_url=service_url,
        timeout=timeout,
    )
