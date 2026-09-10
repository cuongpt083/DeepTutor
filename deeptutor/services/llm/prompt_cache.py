"""Prompt-cache hygiene for chat and other agentic LLM calls.

Goal is API spend: keep a byte-stable prefix so providers can return
cache-read tokens instead of billing the full system prompt every round.

Two layers:

* **Prefix layout** — callers put the stable tutor identity / tools / memory
  in the first system block and anything per-turn (attachments, sidebar,
  compacted-history summary) after it. Markers land on that first block.
* **Wire knobs** — ``cache_control`` by model *family* (Claude, Gemini),
  ``prompt_cache_key`` from the workhorse session id (OpenAI / gateways).
"""

from __future__ import annotations

from typing import Any, Literal

from deeptutor.services.llm.provider_core.base import LLMProvider

CacheFamily = Literal["claude", "gemini", "openai", "none"]

# Anthropic's default ephemeral TTL. Consecutive turns inside this window
# should not rewrite the cached prefix (system prompt or compacted summary).
PROMPT_CACHE_TTL_SECONDS = 300

_CACHE_MARKER: dict[str, str] = {"type": "ephemeral"}

_PROMPT_CACHE_KEY_BINDINGS: frozenset[str] = frozenset(
    {
        "openai",
        "openrouter",
        "openai_codex",
        "github_copilot",
        "azure_openai",
    }
)

# Bindings whose native SDK rejects OpenAI-style cache fields.
_NATIVE_NO_PROMPT_CACHE_KEY: frozenset[str] = frozenset({"anthropic", "claude", "codebuddy"})


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
    family = cache_family(model)
    name = (binding or "").strip().lower()
    if family == "claude":
        return name not in {"ollama", "lm_studio", "vllm", "llama_cpp"}
    if family == "gemini":
        return name in {"openrouter"} or name.endswith("router")
    return False


def wants_prompt_cache_key(binding: str | None, model: str | None) -> bool:
    name = (binding or "").strip().lower()
    if name in _NATIVE_NO_PROMPT_CACHE_KEY:
        return False
    if cache_family(model) == "openai":
        return True
    return name in _PROMPT_CACHE_KEY_BINDINGS or name.endswith("router")


def cache_price_multipliers(model: str | None) -> tuple[float, float]:
    """Return ``(cache_read, cache_write)`` multipliers on the input price.

    Anthropic: writes 1.25×, reads 0.1×. OpenAI cached input is typically 0.5×
    with no separate write surcharge. Unknown families keep 1.0 / 1.0 so we
    never under-report cost.
    """
    family = cache_family(model)
    if family == "claude":
        return 0.1, 1.25
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
    new_messages = list(messages)
    if new_messages and new_messages[0].get("role") == "system":
        first = dict(new_messages[0])
        first["content"] = _mark_content(first.get("content"), first_part=True)
        new_messages[0] = first
    if len(new_messages) >= 3:
        near_last = dict(new_messages[-2])
        near_last["content"] = _mark_content(near_last.get("content"), first_part=False)
        new_messages[-2] = near_last

    new_tools = tools
    if tools:
        new_tools = list(tools)
        for idx in LLMProvider._tool_cache_marker_indices(new_tools):
            new_tools[idx] = {**new_tools[idx], "cache_control": dict(_CACHE_MARKER)}
    return new_messages, new_tools


def mark_anthropic_payload(
    system: str | list[dict[str, Any]],
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
) -> tuple[str | list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]] | None]:
    """Copy Anthropic system/messages/tools with at most 4 breakpoints."""
    marker = dict(_CACHE_MARKER)
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
    "apply_to_completion_kwargs",
    "cache_family",
    "cache_price_multipliers",
    "mark_anthropic_payload",
    "mark_openai_messages",
    "session_cache_key",
    "wants_cache_control",
    "wants_prompt_cache_key",
]
