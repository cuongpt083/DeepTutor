"""Coercion for provider ``usage`` payloads.

Token counts arrive in three shapes and every reader used to guess for itself:

* a plain dict — DeepTutor's own :class:`~deeptutor.services.llm.types.TutorStreamChunk`
  carries ``usage: dict[str, int]``, and the native adapters build one directly;
* a pydantic model — the OpenAI SDK's ``CompletionUsage``;
* a bare object with attributes — some gateways and the Responses API SDK.

Four call sites each re-derived that guess, so teaching the codebase a new
shape meant finding all four (the bug fixed in #919 was exactly one of them
missing the dict case). This module is the only place the guessing happens.

Key names differ by API dialect — chat completions says ``prompt_tokens`` while
the Responses API says ``input_tokens`` — so :func:`token_counts` takes the
source names and always returns DeepTutor's canonical triple.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

CANONICAL_KEYS: tuple[str, str, str] = ("prompt_tokens", "completion_tokens", "total_tokens")


def usage_mapping(payload: Any, *, keys: Sequence[str] = CANONICAL_KEYS) -> dict[str, Any]:
    """Return *payload* as a plain mapping, or ``{}`` when it carries nothing.

    ``keys`` is only consulted for the bare-object case: a mapping and a
    pydantic model already hand over every field they have, while an arbitrary
    object has to be asked for names.
    """
    if payload is None:
        return {}
    if isinstance(payload, Mapping):
        return dict(payload)
    dump = getattr(payload, "model_dump", None)
    if callable(dump):
        try:
            dumped = dump()
        except Exception:  # a model_dump that needs arguments is not ours to call
            dumped = None
        if isinstance(dumped, Mapping):
            return dict(dumped)
    return {key: getattr(payload, key) for key in keys if hasattr(payload, key)}


def token_counts(
    payload: Any,
    *,
    prompt: str = "prompt_tokens",
    completion: str = "completion_tokens",
    total: str = "total_tokens",
) -> dict[str, int]:
    """Canonical ``{prompt,completion,total}_tokens`` triple from any usage shape.

    Returns ``{}`` when the payload reports no tokens at all, so callers can
    keep using truthiness to mean "this frame had no usage report" — a
    zero-filled dict would look like a real report of zero.

    ``total`` falls back to ``prompt + completion``: providers that omit it
    (or send it as 0) still get a usable total.
    """
    frame = usage_mapping(payload, keys=(prompt, completion, total))
    if not frame:
        return {}
    prompt_tokens = _as_int(frame.get(prompt))
    completion_tokens = _as_int(frame.get(completion))
    total_tokens = _as_int(frame.get(total)) or prompt_tokens + completion_tokens
    cache_read = _as_int(frame.get("cache_read_tokens") or frame.get("cache_read_input_tokens"))
    cache_creation = _as_int(
        frame.get("cache_creation_tokens") or frame.get("cache_creation_input_tokens")
    )
    if not cache_read:
        details = frame.get("prompt_tokens_details")
        if isinstance(details, Mapping):
            cache_read = _as_int(details.get("cached_tokens"))
        else:
            cache_read = _as_int(getattr(details, "cached_tokens", 0) if details is not None else 0)
    if not (prompt_tokens or completion_tokens or total_tokens or cache_read or cache_creation):
        return {}
    counts = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }
    if cache_read:
        counts["cache_read_tokens"] = cache_read
    if cache_creation:
        counts["cache_creation_tokens"] = cache_creation
    return counts


def usage_breakdown(
    payload: Any,
    *,
    prompt: str = "prompt_tokens",
    completion: str = "completion_tokens",
    total: str = "total_tokens",
) -> dict[str, int]:
    """Return canonical token counts plus an optional reasoning-token count.

    OpenAI-compatible chat completions put the reasoning count under
    ``completion_tokens_details`` while Responses API payloads use
    ``output_tokens_details``.  Keeping the detail in this small normalized
    frame lets diagnostics distinguish a response that spent its budget on
    reasoning from one that generated visible output, without changing the
    accounting contract of :func:`token_counts`.
    """
    frame = usage_mapping(
        payload,
        keys=(
            prompt,
            completion,
            total,
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "completion_tokens_details",
            "output_tokens_details",
            "prompt_tokens_details",
            "input_tokens_details",
            "cached_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
            "prompt_cache_hit_tokens",
            "prompt_cache_miss_tokens",
            "cached_content_token_count",
        ),
    )
    if prompt not in frame and "input_tokens" in frame:
        prompt = "input_tokens"
        completion = "output_tokens"
    counts = token_counts(frame, prompt=prompt, completion=completion, total=total)
    if not counts:
        # A fully cached Anthropic request can report zero uncached input/output.
        if prompt == "input_tokens" and any(
            _as_int(frame.get(k))
            for k in ("cache_read_input_tokens", "cache_creation_input_tokens")
        ):
            counts = dict.fromkeys(CANONICAL_KEYS, 0)
        else:
            return {}
    cached = None
    for key in (
        "cache_read_input_tokens",
        "cache_read_tokens",
        "cached_tokens",
        "prompt_cache_hit_tokens",
        "cached_content_token_count",
    ):
        if frame.get(key) is not None:
            cached = frame[key]
            break
    if cached is None:
        for key in ("prompt_tokens_details", "input_tokens_details"):
            details = usage_mapping(frame.get(key), keys=("cached_tokens",))
            if details.get("cached_tokens") is not None:
                cached = details["cached_tokens"]
                break
    creation = (
        frame.get("cache_creation_input_tokens")
        if frame.get("cache_creation_input_tokens") is not None
        else frame.get("cache_creation_tokens")
        if frame.get("cache_creation_tokens") is not None
        else frame.get("prompt_cache_miss_tokens")
    )
    if creation is None:
        for key in ("prompt_tokens_details", "input_tokens_details"):
            details = usage_mapping(
                frame.get(key), keys=("cache_creation_tokens", "cache_creation_input_tokens")
            )
            for ck in ("cache_creation_tokens", "cache_creation_input_tokens"):
                if details.get(ck) is not None:
                    creation = details[ck]
                    break
            if creation is not None:
                break
    # Native Anthropic input_tokens excludes cache reads AND cache writes.
    # Canonical/OpenAI prompt_tokens already includes those tokens.
    if prompt == "input_tokens" and (
        "cache_read_input_tokens" in frame
        or "cache_read_tokens" in frame
        or creation is not None
    ):
        counts["prompt_tokens"] += _as_int(cached) + _as_int(creation)
        counts["total_tokens"] = counts["prompt_tokens"] + counts["completion_tokens"]
    elif cached is not None and _as_int(cached) > counts["prompt_tokens"]:
        counts["prompt_tokens"] += _as_int(cached)
        counts["total_tokens"] = counts["prompt_tokens"] + counts["completion_tokens"]

    if cached is not None:
        counts["cache_read_input_tokens"] = min(_as_int(cached), counts["prompt_tokens"])
    if creation is not None:
        counts["cache_creation_input_tokens"] = min(_as_int(creation), counts["prompt_tokens"])
    counts.pop("cache_read_tokens", None)
    counts.pop("cache_creation_tokens", None)
    reasoning = frame.get("reasoning_tokens")
    if reasoning is None:
        for key in ("completion_tokens_details", "output_tokens_details"):
            details = usage_mapping(frame.get(key), keys=("reasoning_tokens",))
            if details.get("reasoning_tokens") is not None:
                reasoning = details.get("reasoning_tokens")
                break
    reasoning_tokens = _as_int(reasoning)
    if reasoning is not None:
        counts["reasoning_tokens"] = reasoning_tokens
    return counts


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


__all__ = ["CANONICAL_KEYS", "token_counts", "usage_breakdown", "usage_mapping"]
