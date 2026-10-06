"""Google Antigravity LLM provider — Cloud Code Assist client.

Speaks the v1internal Gemini protocol directly with OAuth Bearer tokens,
converting OpenAI messages to Gemini contents with tool call support,
handling Gemini 3 thoughtSignature requirements, and streaming SSE responses.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import json
import logging
import re
import secrets
import time
from typing import Any

import httpx

from deeptutor.services.antigravity_auth.constants import DEFAULT_ENDPOINT, DEFAULT_PROJECT_ID
from deeptutor.services.antigravity_auth.contracts import AntigravityReauthRequiredError, AntigravityToken
from deeptutor.services.llm.provider_core.base import LLMProvider, LLMResponse, ToolCallRequest

logger = logging.getLogger(__name__)

_STREAM_PATH = "/v1internal:streamGenerateContent?alt=sse"
_SKIP_THOUGHT_SIGNATURE = "skip_thought_signature_validator"


def _is_gemini3(model: str) -> bool:
    return "gemini-3" in model.lower()


def _is_gemini3_pro(model: str) -> bool:
    return bool(re.search(r"gemini-3(?:\.1)?-pro", model.lower()))


def _thinking_config(model: str, reasoning_effort: str | None) -> dict[str, Any] | None:
    effort = (reasoning_effort or "").lower()
    if effort in ("", "none"):
        return {"thinkingLevel": "LOW"} if _is_gemini3(model) else None

    config: dict[str, Any] = {"includeThoughts": True}
    if _is_gemini3(model):
        config["thinkingLevel"] = "LOW" if effort in ("minimal", "low") else "HIGH"
    else:
        budgets = {"minimal": 1024, "low": 2048, "medium": 8192, "high": 16384}
        config["thinkingBudget"] = budgets.get(effort, 4096)
    return config


class AntigravityProvider(LLMProvider):
    """LLM Provider executing against Cloud Code Assist API."""

    def __init__(
        self,
        token_getter: Any,
        default_model: str = "google-antigravity/gemini-3-pro-low",
        endpoint: str = DEFAULT_ENDPOINT,
    ) -> None:
        super().__init__()
        self._token_getter = token_getter
        self.default_model = default_model
        self.endpoint = endpoint
        self.provider_name = "google_antigravity"

    def _strip_prefix(self, model: str) -> str:
        if "/" in model:
            return model.split("/", 1)[1]
        return model

    def _convert_messages(
        self,
        messages: list[dict[str, Any]],
        model: str,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """Convert OpenAI format messages to Gemini systemInstruction and contents."""
        system_instruction: dict[str, Any] | None = None
        contents: list[dict[str, Any]] = []

        system_parts: list[dict[str, str]] = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            if role == "system":
                if isinstance(content, str) and content:
                    system_parts.append({"text": content})
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("text"):
                            system_parts.append({"text": part["text"]})
            elif role == "user":
                parts: list[dict[str, Any]] = []
                if isinstance(content, str):
                    parts.append({"text": content})
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and "text" in part:
                            parts.append({"text": part["text"]})
                if parts:
                    contents.append({"role": "user", "parts": parts})
            elif role == "assistant":
                parts = []
                if isinstance(content, str) and content:
                    parts.append({"text": content})
                tool_calls = msg.get("tool_calls") or ()
                for tc in tool_calls:
                    fn = tc.get("function") or {}
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            parsed_args = json.loads(args)
                        except Exception:
                            parsed_args = {}
                    else:
                        parsed_args = args or {}
                    fc_part: dict[str, Any] = {
                        "functionCall": {
                            "name": fn.get("name", ""),
                            "args": parsed_args,
                        }
                    }
                    if _is_gemini3(model):
                        fc_part["thoughtSignature"] = _SKIP_THOUGHT_SIGNATURE
                    parts.append(fc_part)
                if parts:
                    contents.append({"role": "model", "parts": parts})
            elif role == "tool":
                tool_content = content if isinstance(content, str) else json.dumps(content)
                try:
                    response_json = json.loads(tool_content)
                except Exception:
                    response_json = {"response": tool_content}

                part = {
                    "functionResponse": {
                        "name": msg.get("name") or "tool",
                        "response": response_json if isinstance(response_json, dict) else {"output": response_json},
                    }
                }
                contents.append({"role": "user", "parts": [part]})

        if system_parts:
            system_instruction = {"parts": system_parts}

        return system_instruction, contents

    def _convert_tools(self, tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        declarations: list[dict[str, Any]] = []
        for t in tools:
            fn = t.get("function") or t
            declarations.append(
                {
                    "name": fn.get("name"),
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
                }
            )
        return [{"functionDeclarations": declarations}]

    async def _get_auth_context(self) -> tuple[str, str]:
        if callable(self._token_getter):
            token = self._token_getter()
            if asyncio.iscoroutine(token):
                token = await token
        else:
            token = self._token_getter

        if isinstance(token, AntigravityToken):
            return token.access_token, token.project_id or DEFAULT_PROJECT_ID
        elif isinstance(token, str):
            return token, DEFAULT_PROJECT_ID
        raise AntigravityReauthRequiredError("No valid Antigravity authentication token available.")

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        return await self.chat_stream(
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
            **kwargs,
        )

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
        on_reasoning_delta: Callable[[str], Awaitable[None]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        raw_model = model or self.default_model
        bare_model = self._strip_prefix(raw_model)

        access_token, project_id = await self._get_auth_context()
        system_instruction, contents = self._convert_messages(messages, bare_model)
        gemini_tools = self._convert_tools(tools)

        gen_config: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        thinking = _thinking_config(bare_model, reasoning_effort)
        if thinking:
            gen_config["thinkingConfig"] = thinking

        request_body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": gen_config,
        }
        if system_instruction:
            request_body["systemInstruction"] = system_instruction
        if gemini_tools:
            request_body["tools"] = gemini_tools

        wrapped_payload = {
            "project": project_id,
            "model": bare_model,
            "request": request_body,
        }

        url = f"{self.endpoint}{_STREAM_PATH}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": "Antigravity/1.21.9",
        }

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        collected_tool_calls: list[ToolCallRequest] = []
        final_usage: dict[str, int] = {}
        finish_reason = "stop"

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, headers=headers, json=wrapped_payload) as resp:
                if resp.status_code != 200:
                    text = await resp.aread()
                    raise RuntimeError(f"Antigravity API error {resp.status_code}: {text.decode('utf-8', errors='replace')}")

                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            item = json.loads(data_str)
                        except Exception:
                            continue

                        response_obj = item.get("response") or item
                        candidates = response_obj.get("candidates") or []
                        if not candidates:
                            continue
                        candidate = candidates[0]
                        parts = candidate.get("content", {}).get("parts") or []

                        for p in parts:
                            if "thought" in p and p["thought"]:
                                th_text = str(p.get("text") or "")
                                if th_text:
                                    reasoning_parts.append(th_text)
                                    if on_reasoning_delta:
                                        await on_reasoning_delta(th_text)
                            elif "text" in p and p["text"]:
                                t_text = str(p["text"])
                                content_parts.append(t_text)
                                if on_content_delta:
                                    await on_content_delta(t_text)
                            if "functionCall" in p:
                                fc = p["functionCall"]
                                name = fc.get("name", "")
                                args_obj = fc.get("args") or {}
                                collected_tool_calls.append(
                                    ToolCallRequest(
                                        id=f"call_{secrets.token_hex(8)}",
                                        name=name,
                                        arguments=args_obj if isinstance(args_obj, dict) else {},
                                    )
                                )

                        usage = response_obj.get("usageMetadata")
                        if usage:
                            final_usage = {
                                "prompt_tokens": usage.get("promptTokenCount", 0),
                                "completion_tokens": usage.get("candidatesTokenCount", 0),
                                "total_tokens": usage.get("totalTokenCount", 0),
                                "cachedContentTokenCount": usage.get("cachedContentTokenCount", 0),
                                "cache_read_input_tokens": usage.get("cachedContentTokenCount", 0),
                            }

                        fr = candidate.get("finishReason")
                        if fr:
                            finish_reason = "stop" if fr == "STOP" else fr.lower()

        return LLMResponse(
            content="".join(content_parts) if content_parts else None,
            tool_calls=collected_tool_calls,
            finish_reason=finish_reason,
            usage=final_usage,
            reasoning_content="".join(reasoning_parts) if reasoning_parts else None,
        )

    def get_default_model(self) -> str:
        return self.default_model
