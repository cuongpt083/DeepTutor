import pytest
from fastapi.testclient import TestClient
from deeptutor.api.main import app

def test_get_metrics_endpoint_returns_200():
    client = TestClient(app)
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    text = response.text
    assert "deeptutor_lightrag_remote_request_duration_seconds" in text
    assert "deeptutor_turn_duration_seconds" in text
    assert "deeptutor_laya_request_duration_seconds" in text
    assert "deeptutor_laya_requests_total" in text
