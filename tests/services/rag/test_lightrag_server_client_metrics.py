import pytest
import httpx
from deeptutor.services.rag.pipelines.lightrag_server.client import LightRagServerClient
from deeptutor.services.rag.pipelines.lightrag_server.config import LightRagServerConfig
from deeptutor.core.observability.metrics import (
    LIGHTRAG_REMOTE_REQUEST_DURATION,
    LIGHTRAG_SERVER_REPORTED_DURATION,
    LIGHTRAG_NETWORK_LATENCY,
    LIGHTRAG_PAYLOAD_BYTES,
)
def _get_count(metric_child):
    return [s.value for s in metric_child._samples() if s.name.endswith("_count")][0]

@pytest.mark.asyncio
async def test_query_context_records_metrics():
    config = LightRagServerConfig(base_url="http://mock-lightrag:9621", api_key="")
    client = LightRagServerClient(config)

    mock_resp = httpx.Response(
        status_code=200,
        json={"response": "test context", "references": [], "response_time": 0.85},
        request=httpx.Request("POST", "http://mock-lightrag:9621/query"),
    )

    transport = httpx.MockTransport(lambda req: mock_resp)
    client._transport = transport

    before_count = _get_count(
        LIGHTRAG_REMOTE_REQUEST_DURATION.labels(
            endpoint="/query", mode="hybrid", status_code="200"
        )
    )

    result = await client.query_context("test query", "hybrid")

    assert result["content"] == "test context"
    after_count = _get_count(
        LIGHTRAG_REMOTE_REQUEST_DURATION.labels(
            endpoint="/query", mode="hybrid", status_code="200"
        )
    )
    assert after_count == before_count + 1

    # Verify server reported time was recorded
    server_reported = LIGHTRAG_SERVER_REPORTED_DURATION.labels(mode="hybrid")._sum.get()
    assert server_reported >= 0.85

    # Verify network latency was recorded
    net_lat_count = _get_count(LIGHTRAG_NETWORK_LATENCY.labels(mode="hybrid"))
    assert net_lat_count >= 1

    # Verify payload bytes recorded
    req_bytes = _get_count(LIGHTRAG_PAYLOAD_BYTES.labels(direction="request", mode="hybrid"))
    resp_bytes = _get_count(LIGHTRAG_PAYLOAD_BYTES.labels(direction="response", mode="hybrid"))
    assert req_bytes >= 1
    assert resp_bytes >= 1
