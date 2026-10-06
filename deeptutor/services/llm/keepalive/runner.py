"""Prompt-cache keep-alive ping runner.

Replays the last chat turn before cache TTL elapses to keep the cache warm
at read-price (~0.1x-0.25x), saving significant latency and cost for subsequent turns.
Runs only for the 'chat' capability, default disabled, bounded by hard ping caps.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from deeptutor.services.llm.prompt_cache import resolve_cache_ttl_policy, wants_cache_control
from .state import KeepWarmCapture, KeepWarmConfig, evaluate_keep_warm

logger = logging.getLogger(__name__)

PING_PROMPT = "[cache keep-alive] Automated cache-warming ping. Do not call any tools. Reply with exactly: ok"
TICK_INTERVAL_S = 15.0

_captures: dict[tuple[str, str], KeepWarmCapture] = {}
_runner_task: asyncio.Task[None] | None = None
_config: KeepWarmConfig = KeepWarmConfig(enabled=False)


def get_config() -> KeepWarmConfig:
    return _config


def set_config(config: KeepWarmConfig) -> None:
    global _config
    _config = config


def mark_in_flight(owner_scope: str, session_id: str, flag: bool) -> None:
    key = (owner_scope, session_id)
    if key in _captures:
        _captures[key].in_flight = flag


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
        in_flight=False,
        pinging=False,
    )
    ensure_runner_started()


async def _ping_capture(cap: KeepWarmCapture) -> None:
    from deeptutor.services.llm.config import LLMConfig
    from deeptutor.services.llm.provider_factory import get_runtime_provider

    cap.pinging = True
    now = time.time()
    try:
        # Re-resolve provider for the owner dynamically
        config = LLMConfig(
            model=cap.model,
            binding=cap.binding,
            max_tokens=1,
            temperature=0.0,
        )
        provider = get_runtime_provider(config)
        
        # Append minimal keep-alive turn
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
