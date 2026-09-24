import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from deeptutor.services.laya.client import should_preseed_with_laya
from deeptutor.core.context import UnifiedContext
from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline


@pytest.mark.asyncio
async def test_should_preseed_with_laya_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "should_preseed": True,
        "confidence": 0.88,
        "latency_ms": 32.5,
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        decision = await should_preseed_with_laya("What is calculus?", ["math_kb"])
        assert decision is True


@pytest.mark.asyncio
async def test_should_preseed_with_laya_timeout_fails_soft():
    import httpx

    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("timed out")):
        decision = await should_preseed_with_laya("What is calculus?", ["math_kb"])
        assert decision is False


@pytest.mark.asyncio
async def test_circuit_breaker_trips_after_consecutive_failures():
    from deeptutor.services.laya.client import LayaClient
    import httpx

    client = LayaClient(failure_threshold=3, cooldown_seconds=30.0)
    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("refused")):
        for _ in range(3):
            res = await client.should_preseed("test query", ["kb1"], service_url="http://mock-service")
            assert res is False

        assert client.is_circuit_open() is True

        # When circuit is open, it should immediately return False without calling HTTP
        with patch("httpx.AsyncClient.post") as mock_post:
            res = await client.should_preseed("test query", ["kb1"], service_url="http://mock-service")
            assert res is False
            mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_circuit_breaker_resets_after_success():
    from deeptutor.services.laya.client import LayaClient
    import httpx

    client = LayaClient(failure_threshold=3, cooldown_seconds=0.01)
    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("refused")):
        for _ in range(3):
            await client.should_preseed("test query", ["kb1"], service_url="http://mock-service")
        assert client.is_circuit_open() is True

    # Wait for cooldown to expire
    import asyncio
    await asyncio.sleep(0.02)
    assert client.is_circuit_open() is False

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"should_preseed": True}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await client.should_preseed("test query", ["kb1"], service_url="http://mock-service")
        assert res is True
        assert client.consecutive_failures == 0


@pytest.mark.asyncio
async def test_pipeline_should_preseed_kb(monkeypatch):
    pipe = AgenticChatPipeline(language="en")
    ctx = UnifiedContext(user_message="hello", knowledge_bases=["kb1"])

    # Test mode off
    monkeypatch.setenv("KB_PRESEED_MODE", "off")
    assert await pipe._should_preseed_kb(ctx, ["kb1"], "hello") is False

    # Test mode always
    monkeypatch.setenv("KB_PRESEED_MODE", "always")
    assert await pipe._should_preseed_kb(ctx, ["kb1"], "hello") is True

    # Test mode auto (calling laya mock)
    monkeypatch.setenv("KB_PRESEED_MODE", "auto")
    with patch("deeptutor.services.laya.client.should_preseed_with_laya", new_callable=AsyncMock) as mock_laya:
        mock_laya.return_value = True
        assert await pipe._should_preseed_kb(ctx, ["kb1"], "hello") is True
        mock_laya.assert_awaited_once_with(
            "hello",
            ["kb1"],
            service_url="http://deeptutor-laya:8000/v1/decide",
            threshold=0.7,
        )
