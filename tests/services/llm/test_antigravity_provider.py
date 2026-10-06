"""Unit tests for AntigravityProvider message and payload conversion."""

from __future__ import annotations

import asyncio
import json
import pytest

from deeptutor.services.llm.provider_core.antigravity_provider import (
    AntigravityProvider,
    _thinking_config,
)


def test_thinking_config_gemini3() -> None:
    c_low = _thinking_config("gemini-3-pro", "low")
    assert c_low == {"includeThoughts": True, "thinkingLevel": "LOW"}

    c_high = _thinking_config("gemini-3-pro", "high")
    assert c_high == {"includeThoughts": True, "thinkingLevel": "HIGH"}

    c_none = _thinking_config("gemini-3-pro", None)
    assert c_none == {"thinkingLevel": "LOW"}


def test_convert_messages_gemini3_thought_signature() -> None:
    provider = AntigravityProvider(token_getter=lambda: "token")
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Calculate 2+2"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "function": {"name": "calc", "arguments": json.dumps({"expr": "2+2"})},
                }
            ],
        },
        {
            "role": "tool",
            "name": "calc",
            "tool_call_id": "c1",
            "content": "4",
        },
    ]
    sys_inst, contents = provider._convert_messages(messages, "gemini-3-pro-low")
    assert sys_inst is not None
    assert sys_inst["parts"][0]["text"] == "You are a helpful assistant."

    assert len(contents) == 3
    # user
    assert contents[0]["role"] == "user"
    assert contents[0]["parts"][0]["text"] == "Calculate 2+2"

    # model tool call with thoughtSignature
    assert contents[1]["role"] == "model"
    part = contents[1]["parts"][0]
    assert "functionCall" in part
    assert part["functionCall"]["name"] == "calc"
    assert part["functionCall"]["args"] == {"expr": "2+2"}
    assert part.get("thoughtSignature") == "skip_thought_signature_validator"

    # tool response
    assert contents[2]["role"] == "user"
    assert "functionResponse" in contents[2]["parts"][0]
    assert contents[2]["parts"][0]["functionResponse"]["name"] == "calc"


@pytest.mark.asyncio
async def test_antigravity_stream_chat_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    sse_lines = [
        b'data: {"response": {"candidates": [{"content": {"parts": [{"thought": true, "text": "let me think"}, {"text": "Hello world"}]}, "finishReason": "STOP"}], "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 10, "totalTokenCount": 60, "cachedContentTokenCount": 30}}}\n\n',
        b"data: [DONE]\n\n",
    ]

    class MockStreamResponse:
        status_code = 200

        async def aiter_lines(self):
            for line in sse_lines:
                yield line.decode("utf-8")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        def stream(self, method, url, **kwargs):
            return MockStreamResponse()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    provider = AntigravityProvider(token_getter=lambda: "dummy_token")
    deltas = []
    reasoning = []
    resp = await provider.chat_stream(
        messages=[{"role": "user", "content": "hi"}],
        on_content_delta=lambda d: deltas.append(d) or asyncio.sleep(0),
        on_reasoning_delta=lambda d: reasoning.append(d) or asyncio.sleep(0),
    )
    assert resp.content == "Hello world"
    assert resp.reasoning_content == "let me think"
    assert resp.finish_reason == "stop"
    assert resp.usage["cachedContentTokenCount"] == 30
    assert deltas == ["Hello world"]
    assert reasoning == ["let me think"]


@pytest.mark.asyncio
async def test_antigravity_gemini3_thought_signature_roundtrip() -> None:
    provider = AntigravityProvider(token_getter=lambda: "dummy")
    
    # 1. Simulate tool call with thoughtSignature from SSE
    tool_call = {
        "id": "tc-1",
        "type": "function",
        "function": {"name": "search", "arguments": json.dumps({"q": "test"})},
    }
    messages = [
        {"role": "user", "content": "search test"},
        {"role": "assistant", "content": "", "tool_calls": [tool_call]},
        {"role": "tool", "name": "search", "tool_call_id": "tc-1", "content": "result 1"},
    ]
    sys_inst, contents = provider._convert_messages(messages, "gemini-3-pro-low")
    
    assert len(contents) == 3
    # Model turn must carry thoughtSignature for Gemini 3
    model_turn = contents[1]
    assert model_turn["role"] == "model"
    fc = model_turn["parts"][0]
    assert "functionCall" in fc
    assert fc.get("thoughtSignature") == "skip_thought_signature_validator"
    
    # Tool response must be role "user" with "functionResponse"
    tool_turn = contents[2]
    assert tool_turn["role"] == "user"
    fr = tool_turn["parts"][0]
    assert "functionResponse" in fr
    assert fr["functionResponse"]["name"] == "search"
    assert fr["functionResponse"]["response"] == {"response": "result 1"}


@pytest.mark.asyncio
async def test_empty_token_does_not_open_http(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_args, **_kwargs):
        raise AssertionError("HTTP client must not be constructed without a token")

    monkeypatch.setattr("httpx.AsyncClient", _boom)
    provider = AntigravityProvider(token_getter=lambda: "")
    with pytest.raises(Exception, match="No valid Antigravity"):
        await provider.chat_stream(messages=[{"role": "user", "content": "hi"}])


def test_factory_refuses_missing_owner_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    constructed = {"provider": False}

    class _Store:
        def load_credentials(self):
            return None

    class _Auth:
        def __init__(self, _root):
            self.store = _Store()

        async def get_valid_token(self):
            raise AssertionError("token fetch")

    class _Provider:
        def __init__(self, *_args, **_kwargs):
            constructed["provider"] = True

    monkeypatch.setattr(
        "deeptutor.services.antigravity_auth.service.AntigravityAuthService",
        _Auth,
    )
    monkeypatch.setattr(
        "deeptutor.services.llm.provider_core.antigravity_provider.AntigravityProvider",
        _Provider,
    )
    monkeypatch.setattr(
        "httpx.AsyncClient",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("http")),
    )

    from deeptutor.services.llm.config import LLMConfig
    from deeptutor.services.llm.exceptions import LLMConfigError
    from deeptutor.services.llm.provider_factory import _build_runtime_provider

    config = LLMConfig(
        model="google-antigravity/gemini-3-pro-low",
        api_key="",
        binding="google_antigravity",
        provider_name="google_antigravity",
    )
    with pytest.raises(LLMConfigError):
        _build_runtime_provider(config, configure_env=False)
    assert constructed["provider"] is False
