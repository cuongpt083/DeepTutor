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


def test_turn_usage_summary_includes_cache_write_reported_calls() -> None:
    from deeptutor.services.llm.metrics import TurnUsage

    usage = TurnUsage()
    usage.calls.append(
        {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "cache_read_input_tokens": 80,
            "cache_creation_input_tokens": 20,
            "estimated": False,
        }
    )
    summary = usage.summary()
    assert summary is not None
    assert summary["cache_reported_calls"] == 1
    assert summary["cache_write_reported_calls"] == 1



def test_resolve_cache_ttl_policy_claude() -> None:
    from deeptutor.services.llm.prompt_cache import resolve_cache_ttl_policy, supports_ttl1h

    assert supports_ttl1h("anthropic", "anthropic")
    assert not supports_ttl1h("anthropic-oauth", "anthropic-oauth")
    assert not supports_ttl1h("openrouter", "openrouter")

    # Short retention default: 300s
    policy_short = resolve_cache_ttl_policy("claude-sonnet-4", "anthropic", "anthropic")
    assert policy_short is not None
    assert policy_short.ttl_s == 300.0
    assert policy_short.ping_cap == 6
    assert policy_short.guaranteed is True

    # Long retention with direct anthropic: 3600s
    policy_long = resolve_cache_ttl_policy(
        "claude-sonnet-4", "anthropic", "anthropic", retention="long"
    )
    assert policy_long is not None
    assert policy_long.ttl_s == 3600.0

    # Long retention with non-direct anthropic (e.g. oauth or openrouter) remains 300s
    policy_oauth = resolve_cache_ttl_policy(
        "claude-sonnet-4", "anthropic-oauth", "anthropic-oauth", retention="long"
    )
    assert policy_oauth is not None
    assert policy_oauth.ttl_s == 300.0
    assert policy_oauth.guaranteed is False


def test_resolve_cache_ttl_policy_other_families() -> None:
    from deeptutor.services.llm.prompt_cache import resolve_cache_ttl_policy

    # OpenAI
    p_openai = resolve_cache_ttl_policy("gpt-5", "openai", "openai")
    assert p_openai is not None
    assert p_openai.ttl_s == 300.0
    assert p_openai.lead_s == 60.0
    assert p_openai.ping_cap == 4

    # Gemini / Antigravity
    p_gemini = resolve_cache_ttl_policy("gemini-2.5-flash", "gemini", "gemini")
    assert p_gemini is not None
    assert p_gemini.ttl_s == 240.0
    assert p_gemini.lead_s == 45.0
    assert p_gemini.ping_cap == 2

    p_anti = resolve_cache_ttl_policy("google-antigravity/gemini-3-pro", "antigravity", "google_antigravity")
    assert p_anti is not None
    assert p_anti.ttl_s == 240.0

    # xAI / Grok
    p_grok = resolve_cache_ttl_policy("grok-3", "xai", "xai")
    assert p_grok is not None
    assert p_grok.ttl_s == 240.0


def test_mark_anthropic_payload_with_custom_ttl() -> None:
    system = [{"type": "text", "text": "SYS"}]
    messages = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
    ]
    marked_sys, marked_msgs, _ = mark_anthropic_payload(system, messages, None, cache_ttl="1h")
    assert marked_sys[0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert marked_msgs[-2]["content"][-1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


def test_cache_price_multipliers_with_1h() -> None:
    read_std, write_std = cache_price_multipliers("claude-sonnet-4")
    assert read_std == 0.1
    assert write_std == 1.25

    read_1h, write_1h = cache_price_multipliers("claude-sonnet-4", ttl="1h")
    assert read_1h == 0.1
    assert write_1h == 2.0

    read_1h_sec, write_1h_sec = cache_price_multipliers("claude-sonnet-4", ttl_s=3600.0)
    assert read_1h_sec == 0.1
    assert write_1h_sec == 2.0
