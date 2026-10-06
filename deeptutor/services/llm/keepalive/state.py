"""State tracking for session prompt-cache keep-warm."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Literal


@dataclass
class KeepWarmCapture:
    owner_scope: str
    session_id: str
    model: str
    binding: str
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] | None
    real_at: float
    last_touch: float
    pings: int = 0
    failures: int = 0
    last_failure_at: float = 0.0
    in_flight: bool = False
    pinging: bool = False


@dataclass(frozen=True)
class KeepWarmConfig:
    enabled: bool = False
    window_min: int = 30
    max_pings: int = 4


Action = Literal["none", "ping"]


def evaluate_keep_warm(
    capture: KeepWarmCapture,
    config: KeepWarmConfig,
    policy_ttl_s: float,
    policy_lead_s: float,
    policy_ping_cap: int,
    now: float,
) -> Action:
    """Determine if a captured session is due for a keep-warm ping."""
    if not config.enabled:
        return "none"
    if capture.pinging or capture.in_flight:
        return "none"
    # Idle window exceeded
    if now - capture.real_at > config.window_min * 60:
        return "none"
    # Ping cap reached
    effective_cap = min(policy_ping_cap, config.max_pings)
    if capture.pings >= effective_cap:
        return "none"
    # Backoff on failures
    if capture.failures >= 2 and (now - capture.last_failure_at < 120.0):
        return "none"
    
    expires = capture.last_touch + policy_ttl_s
    if now >= expires - policy_lead_s:
        return "ping"
    return "none"
