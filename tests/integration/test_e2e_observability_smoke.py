import pytest
import httpx
from fastapi.testclient import TestClient
from deeptutor.api.main import app
from deeptutor.services.rag.pipelines.lightrag_server.client import LightRagServerClient
from deeptutor.services.rag.pipelines.lightrag_server.config import LightRagServerConfig
from deeptutor.core.observability.metrics import (
    record_rag_search,
    record_turn_duration,
    record_tool_duration,
)


@pytest.mark.asyncio
async def test_end_to_end_metrics_collection_and_scrape():
    # 1. Scrape DeepTutor /metrics initial state
    client = TestClient(app)
    initial_metrics = client.get("/metrics").text
    assert "deeptutor_lightrag_remote_request_duration_seconds" in initial_metrics
    assert "deeptutor_turn_duration_seconds" in initial_metrics

    # 2. Simulate turn and tool metrics
    record_turn_duration(capability="chat", status="success", duration=3.45)
    record_tool_duration(tool_name="rag", status="ok", duration=1.82)
    record_rag_search(provider="lightrag-server", mode="mix", status="success", duration=1.80)

    # 3. Simulate a query through LightRagServerClient with mocked server response
    config = LightRagServerConfig(base_url="http://mock-lightrag:9621", api_key="")
    lr_client = LightRagServerClient(config)

    mock_resp = httpx.Response(
        status_code=200,
        json={
            "response": "Synthesized grounded knowledge context",
            "references": [{"reference_id": "1", "file_path": "test.pdf"}],
            "response_time": 1.45,
        },
        request=httpx.Request("POST", "http://mock-lightrag:9621/query"),
    )
    lr_client._transport = httpx.MockTransport(lambda req: mock_resp)

    res = await lr_client.query_context("Explain quantization", "hybrid")
    assert res["content"] == "Synthesized grounded knowledge context"

    # 4. Scrape DeepTutor /metrics after query and assert metrics were recorded
    updated_metrics = client.get("/metrics").text
    assert 'deeptutor_lightrag_remote_request_duration_seconds_count{endpoint="/query",mode="hybrid",status_code="200"}' in updated_metrics
    assert 'deeptutor_lightrag_server_reported_duration_seconds_count{mode="hybrid"}' in updated_metrics
    assert 'deeptutor_lightrag_network_latency_seconds_count{mode="hybrid"}' in updated_metrics
    assert 'deeptutor_turn_duration_seconds_count{capability="chat",status="success"}' in updated_metrics
    assert 'deeptutor_tool_execution_duration_seconds_count{status="ok",tool_name="rag"}' in updated_metrics
    assert 'deeptutor_rag_search_duration_seconds_count{mode="mix",provider="lightrag-server",status="success"}' in updated_metrics
