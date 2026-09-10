"""Chat system prefix stays byte-stable across volatile per-turn blocks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline
from deeptutor.agents.loop import prompt_blocks as prompt_blocks_module
from deeptutor.agents.loop.prompt_blocks import ChatPromptAssembler
from deeptutor.core.context import UnifiedContext

PROMPTS = {
    "general": "You are DeepTutor.",
    "runtime_policy": "policy",
    "loop": {"system": "loop"},
    "runtime_context": "Current date: {datetime}.",
}

FIXED_NOW = datetime(2026, 9, 10, 12, tzinfo=timezone(timedelta(hours=7)))


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return FIXED_NOW
        return FIXED_NOW.astimezone(tz)


@pytest.fixture(autouse=True)
def _freeze_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompt_blocks_module, "datetime", FrozenDateTime)
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


def test_sources_do_not_change_stable_prefix() -> None:
    assembler = ChatPromptAssembler(prompts=PROMPTS, language="en")
    base = UnifiedContext(user_message="q1", memory_context="remember X")
    with_sources = UnifiedContext(
        user_message="q1",
        memory_context="remember X",
        source_manifest="- note.pdf",
        sidebar_context="selected passage",
    )
    stable_a, volatile_a = assembler.render_parts(
        assembler.blocks(context=base, tool_manifest="- none")
    )
    stable_b, volatile_b = assembler.render_parts(
        assembler.blocks(context=with_sources, tool_manifest="- none")
    )
    assert stable_a == stable_b
    assert "remember X" in stable_a
    assert volatile_a == ""
    assert "note.pdf" in volatile_b
    assert "selected passage" in volatile_b


def test_loop_messages_put_sources_after_stable_prefix() -> None:
    pipeline = AgenticChatPipeline(language="en")
    context = UnifiedContext(
        session_id="s1",
        user_message="what does the pdf say?",
        source_manifest="- homework.pdf",
        memory_context="prefers short answers",
    )
    messages = pipeline._build_loop_messages(context=context, enabled_tools=[])
    system = messages[0]["content"]
    assert isinstance(system, list)
    assert "prefers short answers" in system[0]["text"]
    assert "homework.pdf" not in system[0]["text"]
    assert "homework.pdf" in system[1]["text"]


def test_workspace_key_prefers_session_over_turn() -> None:
    context = UnifiedContext(
        session_id="session-abc",
        metadata={"turn_id": "turn-xyz"},
    )
    assert AgenticChatPipeline._workspace_key(context) == "session-abc"
