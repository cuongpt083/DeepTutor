"""The compressed-history summary must reach the final LLM messages.

Regression test: ``ContextBuilder`` emits the summary as a leading
``role: "system"`` entry in ``conversation_history``; the agentic pipeline
used to filter history to user/assistant roles, silently dropping it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline
from deeptutor.core.context import UnifiedContext


@pytest.fixture(autouse=True)
def _fake_llm_config(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = SimpleNamespace(
        binding="openai",
        model="gpt-test",
        api_key="sk-test",
        base_url="https://example.test/v1",
        api_version=None,
    )
    monkeypatch.setattr(
        "deeptutor.agents.loop.pipeline.get_llm_config",
        lambda: cfg,
    )


def test_summary_system_message_reaches_messages() -> None:
    pipeline = AgenticChatPipeline(language="en")
    context = UnifiedContext(
        session_id="s1",
        user_message="next question",
        conversation_history=[
            {"role": "system", "content": "earlier turns summary"},
            {"role": "user", "content": "old question"},
            {"role": "assistant", "content": "old answer"},
        ],
    )

    messages = pipeline._build_loop_messages(
        context=context,
        enabled_tools=[],
    )

    # The summary is the last block of the single system payload, after the
    # cache breakpoint — a second role=system row would overwrite the tutor
    # prefix on Anthropic and bust the cached identity/tools bytes.
    assert messages[0]["role"] == "system"
    system = messages[0]["content"]
    assert isinstance(system, list)
    assert "earlier turns summary" in system[-1]["text"]
    assert "old question" not in system[-1]["text"]
    assert messages[1] == {"role": "user", "content": "old question"}
    assert sum(1 for m in messages if m["role"] == "system") == 1


def test_empty_system_entries_still_filtered() -> None:
    pipeline = AgenticChatPipeline(language="en")
    context = UnifiedContext(
        session_id="s1",
        user_message="q",
        conversation_history=[
            {"role": "system", "content": "   "},
            {"role": "user", "content": "old question"},
        ],
    )

    messages = pipeline._build_loop_messages(
        context=context,
        enabled_tools=[],
    )

    assert messages[1] == {"role": "user", "content": "old question"}
