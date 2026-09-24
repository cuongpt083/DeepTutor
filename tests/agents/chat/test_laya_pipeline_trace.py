import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline
from deeptutor.core.context import UnifiedContext
from deeptutor.runtime.stream_bus import StreamBus


@pytest.mark.asyncio
async def test_pipeline_emits_laya_decision_trace(monkeypatch):
    monkeypatch.setenv("KB_PRESEED_MODE", "auto")
    pipe = AgenticChatPipeline(language="en")
    bus = StreamBus()

    received_events = []

    async def collect_events():
        async for event in bus.subscribe():
            received_events.append(event)
            if getattr(event, "metadata", {}).get("trace_role") == "laya_router":
                break

    collector_task = asyncio.create_task(collect_events())

    with patch("deeptutor.services.laya.client.should_preseed_with_laya", new_callable=AsyncMock) as mock_laya:
        mock_laya.return_value = False
        ctx = UnifiedContext(user_message="Hello", knowledge_bases=["kb1"])
        should_preseed = await pipe._should_preseed_kb(ctx, ["kb1"], "Hello", stream=bus)
        assert should_preseed is False

        await asyncio.wait_for(collector_task, timeout=1.0)
        trace_events = [e for e in received_events if getattr(e, "metadata", {}).get("trace_role") == "laya_router"]
        assert len(trace_events) == 1
        assert trace_events[0].metadata["decision"] is False
