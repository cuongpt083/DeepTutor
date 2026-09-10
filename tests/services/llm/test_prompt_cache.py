"""Prompt-cache family detection, wire markers, and completion-kwargs attach."""

from __future__ import annotations

from deeptutor.services.llm.prompt_cache import (
    apply_to_completion_kwargs,
    cache_family,
    cache_price_multipliers,
    mark_anthropic_payload,
    mark_openai_messages,
    wants_cache_control,
    wants_prompt_cache_key,
)


def test_cache_family_classifies_common_slugs() -> None:
    assert cache_family("anthropic/claude-sonnet-4") == "claude"
    assert cache_family("claude-opus-4-6") == "claude"
    assert cache_family("google/gemini-2.5-pro") == "gemini"
    assert cache_family("gpt-5.6") == "openai"
    assert cache_family("openai/gpt-4.1") == "openai"
    assert cache_family("deepseek-chat") == "none"


def test_cache_control_is_family_not_prefix() -> None:
    assert wants_cache_control("claude-sonnet-4")
    assert wants_cache_control("google/gemini-2.5-flash", "openrouter")
    assert not wants_cache_control("google/gemini-2.5-flash", "gemini")
    assert not wants_cache_control("gpt-5")
    assert not wants_cache_control("qwen2.5")


def test_prompt_cache_key_skipped_on_native_anthropic() -> None:
    assert not wants_prompt_cache_key("anthropic", "claude-sonnet-4")
    assert wants_prompt_cache_key("openrouter", "anthropic/claude-sonnet-4")
    assert wants_prompt_cache_key("openai", "gpt-5")
    assert wants_prompt_cache_key("openai_codex", "gpt-5.3-codex")


def test_mark_openai_messages_marks_first_system_part() -> None:
    messages = [
        {
            "role": "system",
            "content": [
                {"type": "text", "text": "STABLE"},
                {"type": "text", "text": "VOLATILE"},
            ],
        },
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "c"},
    ]
    marked, tools = mark_openai_messages(messages, [{"function": {"name": "t"}}])
    system = marked[0]["content"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in system[1]
    assert marked[-2]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    assert tools[0]["cache_control"] == {"type": "ephemeral"}
    # Original list is not rewritten — the loop reuses it across rounds.
    assert "cache_control" not in messages[0]["content"][0]


def test_mark_anthropic_payload_marks_first_system_block() -> None:
    system = [
        {"type": "text", "text": "STABLE"},
        {"type": "text", "text": "SUMMARY"},
    ]
    messages = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "c"},
    ]
    marked_system, marked_msgs, _tools = mark_anthropic_payload(system, messages, None)
    assert marked_system[0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in marked_system[1]
    assert marked_msgs[-2]["content"][-1]["cache_control"] == {"type": "ephemeral"}


def test_apply_to_completion_kwargs_claude_openrouter() -> None:
    kwargs = {
        "model": "anthropic/claude-sonnet-4",
        "messages": [
            {"role": "system", "content": "You are DeepTutor."},
            {"role": "user", "content": "hi"},
        ],
    }
    apply_to_completion_kwargs(
        kwargs,
        model="anthropic/claude-sonnet-4",
        binding="openrouter",
        session_id="sess-1",
    )
    system = kwargs["messages"][0]["content"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert kwargs["prompt_cache_key"] == "sess-1"


def test_apply_to_completion_kwargs_skips_cache_control_for_gpt() -> None:
    kwargs = {
        "model": "gpt-5",
        "messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
    }
    apply_to_completion_kwargs(kwargs, model="gpt-5", binding="openai", session_id="s1")
    assert kwargs["messages"][0]["content"] == "sys"
    assert kwargs["prompt_cache_key"] == "s1"


def test_claude_cache_read_is_cheaper_than_full_input() -> None:
    read, write = cache_price_multipliers("claude-sonnet-4")
    assert read == 0.1
    assert write == 1.25
