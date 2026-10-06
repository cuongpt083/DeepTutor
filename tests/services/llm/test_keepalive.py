"""Unit tests for keep-warm caching evaluation and runner."""

from __future__ import annotations

import time
import pytest

from deeptutor.services.llm.keepalive.state import (
    KeepWarmCapture,
    KeepWarmConfig,
    evaluate_keep_warm,
)
from deeptutor.services.llm.keepalive.runner import (
    capture_chat_turn,
    get_config,
    set_config,
    stop_runner,
    _captures,
)


def test_evaluate_keep_warm_disabled() -> None:
    now = time.time()
    cap = KeepWarmCapture(
        owner_scope="user-1",
        session_id="sess-1",
        model="claude-sonnet-4",
        binding="anthropic",
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        real_at=now,
        last_touch=now,
    )
    # Disabled config
    cfg = KeepWarmConfig(enabled=False)
    assert evaluate_keep_warm(cap, cfg, 300.0, 60.0, 4, now + 250.0) == "none"


def test_evaluate_keep_warm_triggers_ping_at_lead_time() -> None:
    now = 1000.0
    cap = KeepWarmCapture(
        owner_scope="user-1",
        session_id="sess-1",
        model="claude-sonnet-4",
        binding="anthropic",
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        real_at=now,
        last_touch=now,
    )
    cfg = KeepWarmConfig(enabled=True, window_min=30, max_pings=4)
    ttl = 300.0
    lead = 60.0

    # Before lead time (e.g. at 200s elapsed, expires=1300, lead_start=1240)
    assert evaluate_keep_warm(cap, cfg, ttl, lead, 4, now=1200.0) == "none"

    # Within lead window (e.g. at 250s elapsed >= 1240)
    assert evaluate_keep_warm(cap, cfg, ttl, lead, 4, now=1250.0) == "ping"

    # In flight stops ping
    cap.in_flight = True
    assert evaluate_keep_warm(cap, cfg, ttl, lead, 4, now=1250.0) == "none"
    cap.in_flight = False

    # Max pings stops ping
    cap.pings = 4
    assert evaluate_keep_warm(cap, cfg, ttl, lead, 4, now=1250.0) == "none"


def test_capture_chat_turn_gated() -> None:
    set_config(KeepWarmConfig(enabled=True))
    _captures.clear()

    # Capability other than 'chat' is ignored
    capture_chat_turn(
        owner_scope="user-1",
        session_id="sess-1",
        capability="deep_solve",
        model="claude-sonnet-4",
        binding="anthropic",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert len(_captures) == 0

    # Chat capability is captured
    capture_chat_turn(
        owner_scope="user-1",
        session_id="sess-1",
        capability="chat",
        model="claude-sonnet-4",
        binding="anthropic",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert ("user-1", "sess-1") in _captures
    stop_runner()
