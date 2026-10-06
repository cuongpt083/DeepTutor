"""Prompt-cache hygiene for chat and other agentic LLM calls.

Goal is API spend: keep a byte-stable prefix so providers can return
cache-read tokens instead of billing the full system prompt every round.

Two layers:

* **Prefix layout** — callers put the stable tutor identity / tools / memory
  in the first system block and anything per-turn (attachments, sidebar,
  compacted-history summary) after it. Markers land on that first block.
* **Wire knobs** — ``cache_control`` by model *family* (Claude, Gemini),
  ``prompt_cache_key`` from the workhorse session id (OpenAI / gateways).

Anthropic and OpenAI-compatible gateways bill cache writes and cache reads
differently than uncached input:
- writes are typically 1.25x (or 2.0x for 1-hour retention on Anthropic)
- reads are 0.1x to 0.5x
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from deeptutor.services.llm.provider_core.base import LLMProvider

PROMPT_CACHE_TTL_SECONDS = 300

CacheFamily = Literal["claude", "gemini", "openai", "none"]
CacheRetention = Literal["short", "long"]


@dataclass(frozen=True)
class CacheTtlPolicy:
    """Provider prompt-cache retention policies, TTLs, and ping limits."""

    ttl_s: float
    lead_s: float
    ping_cap: int
    guaranteed: bool


_CACHE_MARKER: dict[str, str] = {"type": "ephemeral"}

_PROMPT_CACHE_KEY_BINDINGS: frozenset[str] = frozenset(
    {
        "openai",
        "openrouter",
        "openai_codex",
        "github_copilot",
        "azure_openai",
        "custom",
    }
)

# Bindings whose native SDK rejects OpenAI-style cache fields.
_NATIVE_NO_PROMPT_CACHE_KEY: frozenset[str] = frozenset({"anthropic", "claude", "codebuddy"})


def supports_ttl1h(binding: str | None = None, provider_name: str | None = None) -> bool:
    """Return True only when the provider is direct Anthropic API with standard API key.

    Excludes OAuth, OpenRouter, Bedrock, and legacy proxy aliases.
    """
    bind = (binding or "").strip().lower()
    name = (provider_name or "").strip().lower()
    if bind in {"anthropic"} or name in {"anthropic"}:
        # Exclude OAuth / bedrock / proxy
        if any(token in bind or token in name for token in ("oauth", "bedrock", "minimax", "custom")):
            return False
        return True
    return False


def resolve_cache_ttl_policy(
    model: str | None,
    binding: str | None = None,
    provider_name: str | None = None,
    *,
    retention: CacheRetention = "short",
    ttl_override: int | None = None,
) -> CacheTtlPolicy | None:
    """Resolve cache TTL and ping policy for a provider/model family.

    Returns None for providers without a defined cache retention policy.
    """
    bind = (binding or "").strip().lower()
    name = (provider_name or "").strip().lower()
    model_lower = (model or "").lower()
    family = cache_family(model)

    # 1. Anthropic family
    if family == "claude" or bind == "anthropic" or name == "anthropic":
        direct = supports_ttl1h(bind, name)
        ttl = 3600.0 if (retention == "long" and direct) else 300.0
        return CacheTtlPolicy(
            ttl_s=float(ttl_override) if ttl_override and ttl_override >= 30 else ttl,
            lead_s=60.0,
            ping_cap=6,
            guaranteed=direct,
        )

    # 2. OpenAI family
    if (
        family == "openai"
        or name in {"openai", "openai_codex"}
        or bind in {"openai", "openai_codex"}
    ):
        return CacheTtlPolicy(
            ttl_s=float(ttl_override) if ttl_override and ttl_override >= 30 else 300.0,
            lead_s=60.0,
            ping_cap=4,
            guaranteed=False,
        )

    # 3. Gemini / Google / Antigravity family
    if (
        family == "gemini"
        or name in {"gemini", "google", "google_antigravity", "antigravity"}
        or bind in {"gemini", "google", "google_antigravity", "antigravity"}
        or "antigravity" in model_lower
    ):
        return CacheTtlPolicy(
            ttl_s=float(ttl_override) if ttl_override and ttl_override >= 30 else 240.0,
            lead_s=45.0,
            ping_cap=2,
            guaranteed=False,
        )

    # 4. xAI / Grok
    if name in {"xai"} or bind in {"xai", "xai_grok"} or "grok" in model_lower:
        return CacheTtlPolicy(
            ttl_s=float(ttl_override) if ttl_override and ttl_override >= 30 else 240.0,
            lead_s=45.0,
            ping_cap=2,
            guaranteed=False,
        )

    return None


def cache_family(model: str | None) -> CacheFamily:
    """Classify *model* for cache-marker selection, ignoring provider prefixes."""
    name = (model or "").strip().lower()
    if not name:
        return "none"
    slug = name.split("/")[-1]
    haystack = f"{name} {slug}"
    if "claude" in haystack or name.startswith("anthropic/"):
        return "claude"
    if "gemini" in haystack or slug.startswith("gemma"):
        return "gemini"
    if any(
        token in haystack for token in ("gpt-5", "gpt-4.1", "gpt-4o", "o1", "o3", "o4", "chatgpt")
    ):
        return "openai"
    return "none"


def wants_cache_control(model: str | None, binding: str | None = None) -> bool:
    """Whether to attach Anthropic-style ``cache_control`` breakpoints.

    Claude always (native Messages API and OpenRouter). Gemini only through
    gateways that document the same marker; Google's own OpenAI-compat
    endpoint does not.
    """
    bind = (binding or "").strip().lower()
    if bind in {"antigravity", "google_antigravity"} or (model and "google-antigravity" in model):
        return False
    family = cache_family(model)
    name = (binding or "").strip().lower()
    if family == "claude":
        return name not in {"ollama", "lm_studio", "vllm", "llama_cpp"}
    if family == "gemini":
        return name in {"openrouter"} or name.endswith("router")
    return False


def wants_prompt_cache_key(binding: str | None, model: str | None) -> bool:
    name = (binding or "").strip().lower()
    if name in {"antigravity", "google_antigravity"} or (model and "google-antigravity" in model):
        return False
    if name in _NATIVE_NO_PROMPT_CACHE_KEY:
        return False
    if cache_family(model) == "openai":
        return True
    return name in _PROMPT_CACHE_KEY_BINDINGS or name.endswith("router")


def cache_price_multipliers(
    model: str | None,
    ttl: str | None = None,
    ttl_s: float | None = None,
) -> tuple[float, float]:
    """Return ``(cache_read, cache_write)`` multipliers on the input price.

    Anthropic: standard writes 1.25x, 1h writes 2.0x, reads 0.1x.
    OpenAI cached input is typically 0.5x with no separate write surcharge.
    Gemini cached input is 0.25x.
    Unknown families keep 1.0 / 1.0 so we never under-report cost.
    """
    family = cache_family(model)
    if family == "claude":
        is_1h = ttl == "1h" or (ttl_s is not None and ttl_s >= 3600.0)
        write_multiplier = 2.0 if is_1h else 1.25
        return 0.1, write_multiplier
    if family == "openai":
        return 0.5, 1.0
    if family == "gemini":
        return 0.25, 1.0
    return 1.0, 1.0


def _mark_content(content: Any, *, first_part: bool) -> Any:
    """Attach ``cache_control`` to a message body.

    ``first_part=True`` marks the leading text block (stable system prefix).
    Otherwise the last part is marked (near-last conversation message).
    """
    if isinstance(content, str):
        return [{"type": "text", "text": content, "cache_control": dict(_CACHE_MARKER)}]
    if isinstance(content, list) and content:
        idx = 0 if first_part else len(content) - 1
        part = content[idx]
        if not isinstance(part, dict):
            return content
        if "cache_control" in part:
            return content
        updated = list(content)
        updated[idx] = {**part, "cache_control": dict(_CACHE_MARKER)}
        return updated
    return content


def mark_openai_messages(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    """Copy *messages* / *tools* with OpenAI-compat ``cache_control`` breakpoints."""
    budget = 4
    new_messages = list(messages)
    if new_messages and new_messages[0].get("role") == "system" and budget > 0:
        first = dict(new_messages[0])
        first["content"] = _mark_content(first.get("content"), first_part=True)
        new_messages[0] = first
        budget -= 1
    if new_messages and new_messages[-1].get("role") == "tool" and budget > 0:
        last = dict(new_messages[-1])
        last["content"] = _mark_content(last.get("content"), first_part=False)
        new_messages[-1] = last
        budget -= 1
    elif len(new_messages) >= 3 and budget > 0:
        near_last = dict(new_messages[-2])
        near_last["content"] = _mark_content(near_last.get("content"), first_part=False)
        new_messages[-2] = near_last
        budget -= 1

    new_tools = tools
    if tools and budget > 0:
        new_tools = list(tools)
        for idx in LLMProvider._tool_cache_marker_indices(new_tools)[:budget]:
            new_tools[idx] = {**new_tools[idx], "cache_control": dict(_CACHE_MARKER)}
            budget -= 1
    return new_messages, new_tools


def mark_anthropic_payload(
    system: str | list[dict[str, Any]],
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    *,
    cache_ttl: str | None = None,
) -> tuple[str | list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]] | None]:
    """Copy Anthropic system/messages/tools with at most 4 breakpoints."""
    marker = dict(_CACHE_MARKER)
    if cache_ttl:
        marker["ttl"] = cache_ttl
    budget = 4

    if isinstance(system, str) and system:
        system = [{"type": "text", "text": system, "cache_control": marker}]
        budget -= 1
    elif isinstance(system, list) and system:
        system = list(system)
        first = system[0]
        if isinstance(first, dict) and "cache_control" not in first:
            system[0] = {**first, "cache_control": marker}
            budget -= 1
        elif isinstance(first, dict):
            budget -= 1

    new_msgs = list(messages)
    if len(new_msgs) >= 3 and budget > 0:
        m = new_msgs[-2]
        c = m.get("content")
        if isinstance(c, str):
            new_msgs[-2] = {
                **m,
                "content": [{"type": "text", "text": c, "cache_control": marker}],
            }
            budget -= 1
        elif isinstance(c, list) and c:
            last = c[-1]
            if isinstance(last, dict) and "cache_control" not in last:
                nc = list(c)
                nc[-1] = {**last, "cache_control": marker}
                new_msgs[-2] = {**m, "content": nc}
                budget -= 1

    new_tools = tools
    if tools and budget > 0:
        new_tools = list(tools)
        for idx in LLMProvider._tool_cache_marker_indices(new_tools)[:budget]:
            new_tools[idx] = {**new_tools[idx], "cache_control": marker}

    return system, new_msgs, new_tools


def apply_to_completion_kwargs(
    kwargs: dict[str, Any],
    *,
    model: str | None,
    binding: str | None = None,
    session_id: str | None = None,
    cache_ttl: str | None = None,
) -> dict[str, Any]:
    """Mutate a ``chat.completions.create`` kwargs dict with cache knobs.

    Safe to call on every round: markers are copied onto a new messages/tools
    list, so the caller's growing conversation is not permanently rewritten.
    """
    if wants_cache_control(model, binding):
        messages = kwargs.get("messages")
        if isinstance(messages, list) and messages:
            marked_messages, marked_tools = mark_openai_messages(messages, kwargs.get("tools"))
            kwargs["messages"] = marked_messages
            if "tools" in kwargs:
                kwargs["tools"] = marked_tools

    key = str(session_id or "").strip()
    if key and wants_prompt_cache_key(binding, model):
        kwargs.setdefault("prompt_cache_key", key)
    return kwargs


def session_cache_key(*parts: str | None) -> str:
    """Stable OpenAI ``prompt_cache_key`` from session identity parts."""
    cleaned = [str(part).strip() for part in parts if str(part or "").strip()]
    return ":".join(cleaned)


__all__ = [
    "PROMPT_CACHE_TTL_SECONDS",
    "CacheFamily",
    "CacheRetention",
    "CacheTtlPolicy",
    "apply_to_completion_kwargs",
    "cache_family",
    "cache_price_multipliers",
    "mark_anthropic_payload",
    "mark_openai_messages",
    "resolve_cache_ttl_policy",
    "session_cache_key",
    "supports_ttl1h",
    "wants_cache_control",
    "wants_prompt_cache_key",
]
