import pytest
from deeptutor.core.observability.metrics import (
    record_remote_request,
    record_server_reported,
    record_network_latency,
    record_payload_bytes,
    record_rag_search,
    record_turn_duration,
    record_tool_duration,
    LIGHTRAG_REMOTE_REQUEST_DURATION,
    LIGHTRAG_SERVER_REPORTED_DURATION,
    LIGHTRAG_NETWORK_LATENCY,
    LIGHTRAG_PAYLOAD_BYTES,
    RAG_SEARCH_DURATION,
    TURN_DURATION,
    TOOL_DURATION,
)

def test_record_remote_request():
    before = LIGHTRAG_REMOTE_REQUEST_DURATION.labels(
        endpoint="/query", mode="mix", status_code="200"
    )._sum.get()
    record_remote_request("/query", "mix", "200", 1.25)
    after = LIGHTRAG_REMOTE_REQUEST_DURATION.labels(
        endpoint="/query", mode="mix", status_code="200"
    )._sum.get()
    assert after >= before + 1.25

def test_record_server_reported_and_network_latency():
    record_server_reported("mix", 0.95)
    record_network_latency("mix", 0.30)
    assert LIGHTRAG_SERVER_REPORTED_DURATION.labels(mode="mix")._sum.get() >= 0.95
    assert LIGHTRAG_NETWORK_LATENCY.labels(mode="mix")._sum.get() >= 0.30

def test_record_payload_bytes():
    record_payload_bytes("request", "mix", 1024)
    record_payload_bytes("response", "mix", 4096)
    assert LIGHTRAG_PAYLOAD_BYTES.labels(direction="request", mode="mix")._sum.get() >= 1024
    assert LIGHTRAG_PAYLOAD_BYTES.labels(direction="response", mode="mix")._sum.get() >= 4096

def test_metrics_never_crash_on_invalid_input():
    # Pass bad types; function must catch exceptions and not raise
    record_remote_request(None, None, None, "invalid")  # type: ignore
