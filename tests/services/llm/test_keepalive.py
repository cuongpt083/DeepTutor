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
    mark_in_flight,
    note_turn_finished,
    note_turn_started,
    set_config,
    stop_runner,
    _captures,
)
from deeptutor.services.llm.prompt_cache import apply_to_completion_kwargs


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


def test_apply_to_completion_kwargs_captures_only_chat_with_owner() -> None:
    set_config(KeepWarmConfig(enabled=True))
    _captures.clear()
    try:
        kwargs = {"messages": [{"role": "user", "content": "hi"}]}
        apply_to_completion_kwargs(
            kwargs,
            model="claude-sonnet-4",
            binding="anthropic",
            session_id="sess-1",
            capability="deep_solve",
            owner_scope="owner-1",
        )
        assert _captures == {}

        apply_to_completion_kwargs(
            kwargs,
            model="claude-sonnet-4",
            binding="anthropic",
            session_id="sess-1",
            capability="chat",
            owner_scope="",
        )
        assert _captures == {}

        apply_to_completion_kwargs(
            kwargs,
            model="claude-sonnet-4",
            binding="anthropic",
            session_id="sess-1",
            capability="chat",
            owner_scope="owner-1",
        )
        assert ("owner-1", "sess-1") in _captures
    finally:
        set_config(KeepWarmConfig(enabled=False))
        stop_runner()


def test_apply_to_completion_kwargs_skips_capture_when_disabled() -> None:
    set_config(KeepWarmConfig(enabled=False))
    _captures.clear()
    apply_to_completion_kwargs(
        {"messages": [{"role": "user", "content": "hi"}]},
        model="claude-sonnet-4",
        binding="anthropic",
        session_id="sess-1",
        capability="chat",
        owner_scope="owner-1",
    )
    assert _captures == {}
    stop_runner()


def test_mark_in_flight_suppresses_ping_and_finally_clears() -> None:
    now = 1000.0
    cap = KeepWarmCapture(
        owner_scope="owner-1",
        session_id="sess-1",
        model="claude-sonnet-4",
        binding="anthropic",
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        real_at=now,
        last_touch=now,
    )
    cfg = KeepWarmConfig(enabled=True, window_min=30, max_pings=4)
    note_turn_started("owner-1", "sess-1")
    cap.in_flight = True
    try:
        assert evaluate_keep_warm(cap, cfg, 300.0, 60.0, 4, now=1250.0) == "none"
        raise RuntimeError("turn failed")
    except RuntimeError:
        note_turn_finished("owner-1", "sess-1")
    cap.in_flight = False
    assert evaluate_keep_warm(cap, cfg, 300.0, 60.0, 4, now=1250.0) == "ping"
    stop_runner()


def test_capture_preserves_in_flight_flag() -> None:
    set_config(KeepWarmConfig(enabled=True))
    _captures.clear()
    note_turn_started("owner-1", "sess-1")
    try:
        capture_chat_turn(
            owner_scope="owner-1",
            session_id="sess-1",
            capability="chat",
            model="claude-sonnet-4",
            binding="anthropic",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert _captures[("owner-1", "sess-1")].in_flight is True
        mark_in_flight("owner-1", "sess-1", False)
        assert _captures[("owner-1", "sess-1")].in_flight is False
    finally:
        stop_runner()


def test_stop_runner_clears_captures() -> None:
    set_config(KeepWarmConfig(enabled=True))
    capture_chat_turn(
        owner_scope="owner-1",
        session_id="sess-1",
        capability="chat",
        model="claude-sonnet-4",
        binding="anthropic",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert _captures
    stop_runner()
    assert _captures == {}
    set_config(KeepWarmConfig(enabled=False))
