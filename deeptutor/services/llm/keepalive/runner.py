"""Prompt-cache keep-alive ping runner.

Replays the last chat turn before cache TTL elapses to keep the cache warm
at read-price (~0.1x-0.25x), saving significant latency and cost for subsequent turns.
Runs only for the 'chat' capability, default disabled, bounded by hard ping caps.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from deeptutor.services.llm.prompt_cache import resolve_cache_ttl_policy, wants_cache_control
from .state import KeepWarmCapture, KeepWarmConfig, evaluate_keep_warm

logger = logging.getLogger(__name__)

PING_PROMPT = "[cache keep-alive] Automated cache-warming ping. Do not call any tools. Reply with exactly: ok"
TICK_INTERVAL_S = 15.0

_captures: dict[tuple[str, str], KeepWarmCapture] = {}
_in_flight: set[tuple[str, str]] = set()
_runner_task: asyncio.Task[None] | None = None
_config: KeepWarmConfig = KeepWarmConfig(enabled=False)


def get_config() -> KeepWarmConfig:
    return _config


def set_config(config: KeepWarmConfig) -> None:
    global _config
    _config = config


def mark_in_flight(owner_scope: str, session_id: str, flag: bool) -> None:
    """Track a live turn independently of the captured snapshot.

    ``capture_chat_turn`` replaces the snapshot mid-turn; the in-flight set
    survives that replacement so a ping cannot overlap the user's request.
    """
    key = (owner_scope, session_id)
    if flag:
        _in_flight.add(key)
    else:
        _in_flight.discard(key)
    if key in _captures:
        _captures[key].in_flight = flag


def note_turn_started(owner_scope: str, session_id: str) -> None:
    if owner_scope and session_id:
        mark_in_flight(owner_scope, session_id, True)


def note_turn_finished(owner_scope: str, session_id: str) -> None:
    if owner_scope and session_id:
        mark_in_flight(owner_scope, session_id, False)


def capture_chat_turn(
    *,
    owner_scope: str,
    session_id: str,
    capability: str,
    model: str,
    binding: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> None:
    """Capture chat request snapshot for keep-warm if eligible."""
    if capability != "chat":
        return
    if not _config.enabled:
        return
    policy = resolve_cache_ttl_policy(model, binding)
    if not policy:
        return

    now = time.time()
    key = (owner_scope, session_id)
    _captures[key] = KeepWarmCapture(
        owner_scope=owner_scope,
        session_id=session_id,
        model=model,
        binding=binding,
        messages=list(messages),
        tools=list(tools) if tools else None,
        real_at=now,
        last_touch=now,
        pings=0,
        failures=0,
        in_flight=key in _in_flight,
        pinging=False,
    )
    ensure_runner_started()


def load_config_from_settings() -> KeepWarmConfig:
    """Read keep-warm from runtime system settings. Default is disabled."""
    enabled = False
    window_min = 30
    max_pings = 4
    try:
        from deeptutor.services.config.runtime_settings import load_system_settings

        raw = load_system_settings().get("keep_warm") or {}
        if isinstance(raw, dict):
            enabled = bool(raw.get("enabled", False))
            window_min = int(raw.get("window_min") or 30)
            max_pings = int(raw.get("max_pings") or 4)
    except Exception:
        logger.debug("keep-warm settings unavailable", exc_info=True)
    env = os.environ.get("DEEPTUTOR_KEEP_WARM_ENABLED", "").strip().lower()
    if env in {"1", "true", "yes", "on"}:
        enabled = True
    elif env in {"0", "false", "no", "off"}:
        enabled = False
    return KeepWarmConfig(enabled=enabled, window_min=max(1, window_min), max_pings=max(0, max_pings))


def apply_settings_config() -> None:
    set_config(load_config_from_settings())


async def _provider_for_ping(cap: KeepWarmCapture) -> Any:
    """Build a ping provider bound to the capturing owner, never another account."""
    binding = (cap.binding or "").strip().lower()
    if binding in {"antigravity", "google_antigravity"} or "antigravity" in (cap.model or "").lower():
        from deeptutor.multi_user.paths import owner_secrets_dir
        from deeptutor.services.antigravity_auth.service import AntigravityAuthService
        from deeptutor.services.llm.provider_core.antigravity_provider import AntigravityProvider

        service = AntigravityAuthService(owner_secrets_dir(cap.owner_scope))
        token = await service.get_valid_token()
        access = token if isinstance(token, str) else getattr(token, "access_token", "")
        if not str(access or "").strip():
            raise RuntimeError("antigravity keep-warm token unavailable")
        return AntigravityProvider(token_getter=lambda: token, default_model=cap.model)

    from deeptutor.services.llm.config import get_llm_config
    from deeptutor.services.llm.provider_factory import build_isolated_provider

    base = get_llm_config()
    base_bind = (getattr(base, "binding", "") or "").strip().lower()
    base_name = (getattr(base, "provider_name", "") or "").strip().lower()
    if binding and binding not in {base_bind, base_name}:
        raise RuntimeError(
            "keep-warm ping skipped: credentials are not scoped to the capturing owner"
        )
    config = base.model_copy(
        update={"model": cap.model or base.model, "max_tokens": 1, "temperature": 0.0}
    )
    return build_isolated_provider(config)


async def _ping_capture(cap: KeepWarmCapture) -> None:
    cap.pinging = True
    now = time.time()
    try:
        if cap.in_flight or (cap.owner_scope, cap.session_id) in _in_flight:
            return
        provider = await _provider_for_ping(cap)

        # Append minimal keep-alive turn. Native Anthropic providers re-apply
        # cache_control (including ttl=1h when long retention is on) in
        # ``_build_kwargs``, so the ping refreshes the same breakpoint.
        ping_messages = list(cap.messages)
        ping_messages.append({"role": "user", "content": PING_PROMPT})

        logger.debug("Firing keep-warm ping for session %s (model: %s)", cap.session_id, cap.model)
        await provider.chat(
            messages=ping_messages,
            tools=None,
            max_tokens=1,
            temperature=0.0,
        )
        cap.pings += 1
        cap.last_touch = now
        cap.failures = 0
    except Exception as exc:
        cap.failures += 1
        cap.last_failure_at = now
        logger.debug("Keep-warm ping failed for session %s: %s", cap.session_id, exc)
    finally:
        cap.pinging = False


async def _runner_loop() -> None:
    while True:
        try:
            await asyncio.sleep(TICK_INTERVAL_S)
            if not _config.enabled or not _captures:
                continue

            now = time.time()
            to_remove = []

            for key, cap in list(_captures.items()):
                policy = resolve_cache_ttl_policy(cap.model, cap.binding)
                if not policy:
                    to_remove.append(key)
                    continue

                action = evaluate_keep_warm(
                    cap,
                    _config,
                    policy_ttl_s=policy.ttl_s,
                    policy_lead_s=policy.lead_s,
                    policy_ping_cap=policy.ping_cap,
                    now=now,
                )

                if action == "ping":
                    asyncio.create_task(_ping_capture(cap))
                elif now - cap.real_at > _config.window_min * 60:
                    to_remove.append(key)

            for key in to_remove:
                _captures.pop(key, None)

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Keep-warm runner error: %s", exc)


def ensure_runner_started() -> None:
    global _runner_task
    try:
        loop = asyncio.get_running_loop()
        if _runner_task is None or _runner_task.done():
            _runner_task = loop.create_task(_runner_loop())
    except RuntimeError:
        pass


def stop_runner() -> None:
    global _runner_task
    if _runner_task and not _runner_task.done():
        _runner_task.cancel()
        _runner_task = None
    _captures.clear()
    _in_flight.clear()
