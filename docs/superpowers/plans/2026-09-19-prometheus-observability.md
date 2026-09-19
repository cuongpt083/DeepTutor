# Prometheus Observability for DeepTutor & LightRAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide end-to-end observability across DeepTutor and LightRAG Server (`~\Workspaces\LightRAG`) using Prometheus metrics and `/metrics` exposition endpoints to diagnose and tune remote query latency bottlenecks.

**Architecture:** A standardized `prometheus_client` collector layer is introduced in both codebases. DeepTutor exposes `GET /metrics` on port 8001 and instruments client RTT, server-reported latency, and inferred network latency in `LightRagServerClient`. LightRAG Server exposes `GET /metrics` on port 9621 and instruments its internal execution stages (`extract_keywords_llm`, `perform_kg_search`, `token_truncation`, `merge_chunks`) in `operate.py` via safe, non-fatal context managers.

**Tech Stack:** Python 3.11+, FastAPI, `prometheus-client>=0.20.0`, `httpx`, `pytest`, `pytest-asyncio`.

**Spec:** `docs/superpowers/specs/2026-09-19-prometheus-observability-design.md`

## Global Constraints

- **Non-fatal error contract:** Metrics collection operations must never raise unhandled exceptions or crash request handling in either DeepTutor or LightRAG.
- **Dependency minimum:** `prometheus-client>=0.20.0` added to dependencies.
- **Metric naming standard:** Snake_case prefixed with `deeptutor_` for DeepTutor and `lightrag_` for LightRAG server.
- **Multi-worker safety:** In LightRAG server, `/metrics` must handle both single-worker `uvicorn` and multi-worker `gunicorn` (via `PROMETHEUS_MULTIPROC_DIR` fallback).
- **TDD requirement:** Every step must begin with a failing test before implementation.

---

## File Structure & Responsibilities

### DeepTutor (`C:/Users/Admin/Workspaces/DeepTutor`)
- `pyproject.toml`: Declares `prometheus-client>=0.20.0` dependency.
- `deeptutor/core/observability/__init__.py`: Package entry point for observability.
- `deeptutor/core/observability/metrics.py`: Defines Prometheus metric definitions, registry wrappers, and helper recording functions with fail-safe error handling.
- `deeptutor/api/routers/metrics.py`: FastAPI router exposing `GET /metrics`.
- `deeptutor/api/main.py`: Mounts the metrics router onto the main application.
- `deeptutor/services/rag/pipelines/lightrag_server/client.py`: Instruments `query_context` to measure client RTT, read `response_time`, calculate network latency, and record payload sizes.
- `tests/core/test_observability_metrics.py`: Unit tests for metric definitions and recording functions.
- `tests/api/test_metrics_endpoint.py`: Unit tests for the `/metrics` endpoint.
- `tests/services/rag/test_lightrag_server_client_metrics.py`: Unit tests for `LightRagServerClient` metric recording.

### LightRAG Server (`C:/Users/Admin/Workspaces/LightRAG`)
- `pyproject.toml`: Declares `prometheus-client>=0.20.0` dependency.
- `lightrag/query_metrics.py`: Defines query metrics, counters, histograms, and the `record_query_stage` context manager.
- `lightrag/operate.py`: Instruments `kg_query`, `_build_query_context`, and `naive_query` with stage timers.
- `lightrag/api/routers/query_routes.py`: Instruments `/query` route request counter and overall duration.
- `lightrag/api/lightrag_server.py`: Exposes `GET /metrics` supporting single and multi-process collectors.
- `tests/test_query_metrics.py`: Unit tests for `query_metrics.py` and stage timers.
- `tests/test_lightrag_metrics_endpoint.py`: Unit tests for `/metrics` route on LightRAG server.

---

### Task 1: Add `prometheus-client` and Build DeepTutor Metrics Core Module

**Files:**
- Modify: `pyproject.toml`
- Create: `deeptutor/core/observability/__init__.py`
- Create: `deeptutor/core/observability/metrics.py`
- Test: `tests/core/test_observability_metrics.py`

**Interfaces:**
- Produces:
  ```python
  def record_remote_request(endpoint: str, mode: str, status_code: str, duration: float) -> None
  def record_server_reported(mode: str, duration: float) -> None
  def record_network_latency(mode: str, duration: float) -> None
  def record_payload_bytes(direction: str, mode: str, num_bytes: int) -> None
  def record_rag_search(provider: str, mode: str, status: str, duration: float) -> None
  def record_turn_duration(capability: str, status: str, duration: float) -> None
  def record_tool_duration(tool_name: str, status: str, duration: float) -> None
  ```

- [ ] **Step 1: Write the failing test for metrics recording**

Create `tests/core/test_observability_metrics.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_observability_metrics.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'deeptutor.core.observability')

- [ ] **Step 3: Update `pyproject.toml`, install `prometheus-client`, and write implementation**

In `pyproject.toml`, add `"prometheus-client>=0.20.0"` under `dependencies`.
Install: `pip install "prometheus-client>=0.20.0"`

Create `deeptutor/core/observability/__init__.py`:
```python
"""Observability and metrics subsystem for DeepTutor."""
```

Create `deeptutor/core/observability/metrics.py`:
```python
"""Prometheus metrics definitions and safe recording functions."""

from __future__ import annotations

import logging
from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

# Turn level
TURN_DURATION = Histogram(
    "deeptutor_turn_duration_seconds",
    "End-to-end conversation turn duration in seconds",
    ["capability", "status"],
    buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0],
)

# Tool execution
TOOL_DURATION = Histogram(
    "deeptutor_tool_execution_duration_seconds",
    "Tool execution duration in seconds",
    ["tool_name", "status"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0],
)

# RAG search overall
RAG_SEARCH_DURATION = Histogram(
    "deeptutor_rag_search_duration_seconds",
    "RAG service search duration in seconds",
    ["provider", "mode", "status"],
    buckets=[0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 40.0, 60.0],
)

# Remote LightRAG client request RTT
LIGHTRAG_REMOTE_REQUEST_DURATION = Histogram(
    "deeptutor_lightrag_remote_request_duration_seconds",
    "Total HTTP round-trip time for remote LightRAG query in seconds",
    ["endpoint", "mode", "status_code"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0],
)

# Remote LightRAG server-reported processing time
LIGHTRAG_SERVER_REPORTED_DURATION = Histogram(
    "deeptutor_lightrag_server_reported_duration_seconds",
    "Processing time reported inside LightRAG response payload in seconds",
    ["mode"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0],
)

# Inferred network overhead
LIGHTRAG_NETWORK_LATENCY = Histogram(
    "deeptutor_lightrag_network_latency_seconds",
    "Inferred network transfer and serialization latency in seconds (client RTT - server reported)",
    ["mode"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# Payload bytes
LIGHTRAG_PAYLOAD_BYTES = Histogram(
    "deeptutor_lightrag_payload_bytes",
    "Payload size of requests and responses exchanged with LightRAG in bytes",
    ["direction", "mode"],
    buckets=[128, 512, 1024, 4096, 16384, 65536, 262144, 1048576],
)


def record_remote_request(endpoint: str, mode: str, status_code: str, duration: float) -> None:
    try:
        LIGHTRAG_REMOTE_REQUEST_DURATION.labels(
            endpoint=str(endpoint or "/query"),
            mode=str(mode or "default"),
            status_code=str(status_code or "unknown"),
        ).observe(max(0.0, float(duration)))
    except Exception as exc:
        logger.debug(f"Failed to record remote request metric: {exc}")


def record_server_reported(mode: str, duration: float) -> None:
    try:
        LIGHTRAG_SERVER_REPORTED_DURATION.labels(
            mode=str(mode or "default"),
        ).observe(max(0.0, float(duration)))
    except Exception as exc:
        logger.debug(f"Failed to record server reported metric: {exc}")


def record_network_latency(mode: str, duration: float) -> None:
    try:
        LIGHTRAG_NETWORK_LATENCY.labels(
            mode=str(mode or "default"),
        ).observe(max(0.0, float(duration)))
    except Exception as exc:
        logger.debug(f"Failed to record network latency metric: {exc}")


def record_payload_bytes(direction: str, mode: str, num_bytes: int) -> None:
    try:
        LIGHTRAG_PAYLOAD_BYTES.labels(
            direction=str(direction),
            mode=str(mode or "default"),
        ).observe(max(0.0, float(num_bytes)))
    except Exception as exc:
        logger.debug(f"Failed to record payload bytes metric: {exc}")


def record_rag_search(provider: str, mode: str, status: str, duration: float) -> None:
    try:
        RAG_SEARCH_DURATION.labels(
            provider=str(provider or "unknown"),
            mode=str(mode or "default"),
            status=str(status or "unknown"),
        ).observe(max(0.0, float(duration)))
    except Exception as exc:
        logger.debug(f"Failed to record rag search metric: {exc}")


def record_turn_duration(capability: str, status: str, duration: float) -> None:
    try:
        TURN_DURATION.labels(
            capability=str(capability or "unknown"),
            status=str(status or "unknown"),
        ).observe(max(0.0, float(duration)))
    except Exception as exc:
        logger.debug(f"Failed to record turn duration metric: {exc}")


def record_tool_duration(tool_name: str, status: str, duration: float) -> None:
    try:
        TOOL_DURATION.labels(
            tool_name=str(tool_name or "unknown"),
            status=str(status or "unknown"),
        ).observe(max(0.0, float(duration)))
    except Exception as exc:
        logger.debug(f"Failed to record tool duration metric: {exc}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_observability_metrics.py -v`
Expected: PASS (all 4 tests pass)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml deeptutor/core/observability/ tests/core/test_observability_metrics.py
git commit -m "feat(observability): add Prometheus metrics core module for DeepTutor"
```

---

### Task 2: Implement FastAPI `/metrics` Exporter Route in DeepTutor

**Files:**
- Create: `deeptutor/api/routers/metrics.py`
- Modify: `deeptutor/api/main.py:520-530`
- Test: `tests/api/test_metrics_endpoint.py`

**Interfaces:**
- Consumes: `prometheus_client.generate_latest`, `CONTENT_TYPE_LATEST`
- Produces: `GET /metrics` returning `Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)`

- [ ] **Step 1: Write the failing test for `/metrics` endpoint**

Create `tests/api/test_metrics_endpoint.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_metrics_endpoint.py -v`
Expected: FAIL (404 Not Found)

- [ ] **Step 3: Implement metrics router and mount in `main.py`**

Create `deeptutor/api/routers/metrics.py`:
```python
"""Prometheus metrics exposition endpoint."""

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def metrics() -> Response:
    """Expose Prometheus metrics for scraping."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

In `deeptutor/api/main.py`, import `metrics` router and mount:
```python
from deeptutor.api.routers import metrics as metrics_router

# Mount metrics endpoint without auth requirements (standard Prometheus scrape path)
app.include_router(metrics_router.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_metrics_endpoint.py -v`
Expected: PASS (status_code == 200, metrics present)

- [ ] **Step 5: Commit**

```bash
git add deeptutor/api/routers/metrics.py deeptutor/api/main.py tests/api/test_metrics_endpoint.py
git commit -m "feat(api): expose GET /metrics endpoint for Prometheus scraping"
```

---

### Task 3: Instrument `LightRagServerClient` in DeepTutor

**Files:**
- Modify: `deeptutor/services/rag/pipelines/lightrag_server/client.py:90-110`
- Test: `tests/services/rag/test_lightrag_server_client_metrics.py`

**Interfaces:**
- Consumes: `record_remote_request`, `record_server_reported`, `record_network_latency`, `record_payload_bytes` from `deeptutor.core.observability.metrics`
- Produces: Instrumented `LightRagServerClient.query_context()` recording metrics on every call.

- [ ] **Step 1: Write the failing test for client instrumentation**

Create `tests/services/rag/test_lightrag_server_client_metrics.py`:
```python
import pytest
import httpx
from unittest.mock import AsyncMock
from deeptutor.services.rag.pipelines.lightrag_server.client import LightRagServerClient
from deeptutor.services.rag.pipelines.lightrag_server.config import LightRagServerConfig
from deeptutor.core.observability.metrics import (
    LIGHTRAG_REMOTE_REQUEST_DURATION,
    LIGHTRAG_SERVER_REPORTED_DURATION,
    LIGHTRAG_NETWORK_LATENCY,
)

@pytest.mark.asyncio
async def test_query_context_records_metrics(monkeypatch):
    config = LightRagServerConfig(base_url="http://mock-lightrag:9621")
    client = LightRagServerClient(config)

    mock_resp = httpx.Response(
        status_code=200,
        json={"response": "test context", "references": [], "response_time": 0.85},
        request=httpx.Request("POST", "http://mock-lightrag:9621/query"),
    )

    transport = httpx.MockTransport(lambda req: mock_resp)
    client._transport = transport

    before_count = LIGHTRAG_REMOTE_REQUEST_DURATION.labels(
        endpoint="/query", mode="hybrid", status_code="200"
    )._count.get()

    result = await client.query_context("test query", "hybrid")

    assert result["content"] == "test context"
    after_count = LIGHTRAG_REMOTE_REQUEST_DURATION.labels(
        endpoint="/query", mode="hybrid", status_code="200"
    )._count.get()
    assert after_count == before_count + 1

    # Verify server reported time was recorded
    server_reported = LIGHTRAG_SERVER_REPORTED_DURATION.labels(mode="hybrid")._sum.get()
    assert server_reported >= 0.85

    # Verify network latency was recorded
    net_lat_count = LIGHTRAG_NETWORK_LATENCY.labels(mode="hybrid")._count.get()
    assert net_lat_count >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/rag/test_lightrag_server_client_metrics.py -v`
Expected: FAIL (after_count == before_count because metrics are not recorded yet)

- [ ] **Step 3: Update `LightRagServerClient.query_context`**

In `deeptutor/services/rag/pipelines/lightrag_server/client.py`:
```python
import time
from deeptutor.core.observability.metrics import (
    record_network_latency,
    record_payload_bytes,
    record_remote_request,
    record_server_reported,
)

    async def query_context(self, query: str, mode: str) -> dict[str, Any]:
        """Retrieve grounded context for ``query`` without server-side generation."""
        start_time = time.perf_counter()
        status_code = "error"
        server_reported_time: Optional[float] = None
        req_payload = {"query": query, "mode": mode, "only_need_context": True}
        req_bytes = len(str(query).encode("utf-8"))
        resp_bytes = 0

        try:
            async with self._open() as client:
                resp = await client.post("/query", json=req_payload)
            status_code = str(resp.status_code)
            resp_bytes = len(resp.content)
            data = self._json(resp)
            content = str(data.get("response") or "")
            sources = _sources_from_references(data.get("references"))

            raw_time = data.get("response_time")
            if raw_time is not None:
                try:
                    server_reported_time = float(raw_time)
                except (ValueError, TypeError):
                    server_reported_time = None

            return {"content": content, "sources": sources}
        finally:
            rtt = time.perf_counter() - start_time
            record_remote_request(
                endpoint="/query",
                mode=mode,
                status_code=status_code,
                duration=rtt,
            )
            record_payload_bytes(direction="request", mode=mode, num_bytes=req_bytes)
            if resp_bytes > 0:
                record_payload_bytes(direction="response", mode=mode, num_bytes=resp_bytes)
            if server_reported_time is not None:
                record_server_reported(mode=mode, duration=server_reported_time)
                net_latency = max(0.0, rtt - server_reported_time)
                record_network_latency(mode=mode, duration=net_latency)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/services/rag/test_lightrag_server_client_metrics.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add deeptutor/services/rag/pipelines/lightrag_server/client.py tests/services/rag/test_lightrag_server_client_metrics.py
git commit -m "feat(rag): instrument LightRagServerClient with latency breakdown and payload size metrics"
```

---

### Task 4: Build LightRAG Server Query Metrics Module (`~\Workspaces\LightRAG`)

**Files:**
- Modify: `../LightRAG/pyproject.toml`
- Create: `../LightRAG/lightrag/query_metrics.py`
- Test: `../LightRAG/tests/test_query_metrics.py`

**Interfaces:**
- Produces:
  ```python
  def record_query_duration(mode: str, status: str, duration: float) -> None
  def record_query_total(mode: str, status: str) -> None
  def record_llm_call(role: str, duration: float) -> None
  @contextmanager
  def record_query_stage(mode: str, stage: str): ...
  ```

- [ ] **Step 1: Write the failing test for LightRAG `query_metrics`**

Create `../LightRAG/tests/test_query_metrics.py`:
```python
import pytest
import time
from lightrag.query_metrics import (
    record_query_duration,
    record_query_total,
    record_llm_call,
    record_query_stage,
    QUERY_DURATION,
    QUERY_TOTAL,
    QUERY_STAGE_DURATION,
    LLM_CALL_DURATION,
)

def test_record_query_metrics():
    record_query_total("mix", "success")
    record_query_duration("mix", "success", 2.3)
    assert QUERY_TOTAL.labels(mode="mix", status="success")._value.get() >= 1
    assert QUERY_DURATION.labels(mode="mix", status="success")._sum.get() >= 2.3

def test_record_query_stage_context_manager():
    before = QUERY_STAGE_DURATION.labels(mode="mix", stage="extract_keywords_llm")._sum.get()
    with record_query_stage("mix", "extract_keywords_llm"):
        time.sleep(0.05)
    after = QUERY_STAGE_DURATION.labels(mode="mix", stage="extract_keywords_llm")._sum.get()
    assert after >= before + 0.04

def test_record_query_stage_catches_exception_safely():
    with pytest.raises(ValueError):
        with record_query_stage("mix", "perform_kg_search"):
            raise ValueError("Test error inside stage")
    # Verify observation was still recorded in finally block
    assert QUERY_STAGE_DURATION.labels(mode="mix", stage="perform_kg_search")._count.get() >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest ../LightRAG/tests/test_query_metrics.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'lightrag.query_metrics')

- [ ] **Step 3: Update `pyproject.toml` in LightRAG and implement `query_metrics.py`**

Add `prometheus-client>=0.20.0` to `../LightRAG/pyproject.toml` dependencies.
Install: `pip install "prometheus-client>=0.20.0"`

Create `../LightRAG/lightrag/query_metrics.py`:
```python
"""Prometheus metrics definitions and stage instrumentation for LightRAG queries."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

QUERY_DURATION = Histogram(
    "lightrag_query_duration_seconds",
    "Total LightRAG query request latency in seconds",
    ["mode", "status"],
    buckets=[0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0],
)

QUERY_TOTAL = Counter(
    "lightrag_query_requests_total",
    "Total LightRAG query requests count",
    ["mode", "status"],
)

QUERY_STAGE_DURATION = Histogram(
    "lightrag_query_stage_duration_seconds",
    "Duration of individual query processing stages in seconds",
    ["mode", "stage"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 40.0, 60.0],
)

LLM_CALL_DURATION = Histogram(
    "lightrag_llm_call_duration_seconds",
    "Duration of LLM calls made by LightRAG in seconds",
    ["role"],
    buckets=[0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0],
)


def record_query_duration(mode: str, status: str, duration: float) -> None:
    try:
        QUERY_DURATION.labels(mode=str(mode or "default"), status=str(status or "unknown")).observe(
            max(0.0, float(duration))
        )
    except Exception as exc:
        logger.debug(f"Failed to record query duration: {exc}")


def record_query_total(mode: str, status: str) -> None:
    try:
        QUERY_TOTAL.labels(mode=str(mode or "default"), status=str(status or "unknown")).inc()
    except Exception as exc:
        logger.debug(f"Failed to record query total: {exc}")


def record_llm_call(role: str, duration: float) -> None:
    try:
        LLM_CALL_DURATION.labels(role=str(role or "default")).observe(max(0.0, float(duration)))
    except Exception as exc:
        logger.debug(f"Failed to record llm call metric: {exc}")


@contextmanager
def record_query_stage(mode: str, stage: str):
    """Safely record the execution duration of a query processing stage."""
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start
        try:
            QUERY_STAGE_DURATION.labels(
                mode=str(mode or "default"),
                stage=str(stage or "unknown"),
            ).observe(max(0.0, duration))
        except Exception as exc:
            logger.debug(f"Failed to observe query stage '{stage}': {exc}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest ../LightRAG/tests/test_query_metrics.py -v`
Expected: PASS (all 3 tests pass)

- [ ] **Step 5: Commit in LightRAG repo**

```bash
cd ../LightRAG
git add pyproject.toml lightrag/query_metrics.py tests/test_query_metrics.py
git commit -m "feat(metrics): add Prometheus query metrics module and stage context managers"
cd ../DeepTutor
```

---

### Task 5: Instrument LightRAG Execution Stages in `operate.py` and `query_routes.py`

**Files:**
- Modify: `../LightRAG/lightrag/operate.py`
- Modify: `../LightRAG/lightrag/api/routers/query_routes.py`
- Test: `../LightRAG/tests/test_operate_metrics_integration.py`

**Interfaces:**
- Consumes: `record_query_stage`, `record_query_duration`, `record_query_total` from `lightrag.query_metrics`
- Produces: Execution timing records for `extract_keywords_llm`, `perform_kg_search`, `token_truncation`, `merge_chunks`, and total query duration.

- [ ] **Step 1: Write integration test for stage recording**

Create `../LightRAG/tests/test_operate_metrics_integration.py`:
```python
import pytest
from lightrag.query_metrics import QUERY_STAGE_DURATION

def test_query_stage_definitions():
    stages = ["extract_keywords_llm", "perform_kg_search", "token_truncation", "merge_chunks", "vector_search_chunks"]
    for s in stages:
        metric = QUERY_STAGE_DURATION.labels(mode="mix", stage=s)
        assert metric is not None
```

- [ ] **Step 2: Run test to verify it passes basic definition**

Run: `pytest ../LightRAG/tests/test_operate_metrics_integration.py -v`
Expected: PASS

- [ ] **Step 3: Instrument `kg_query` and `_build_query_context` in `operate.py`**

In `../LightRAG/lightrag/operate.py`:
Import `from lightrag.query_metrics import record_query_stage`
1. In `kg_query()` around keyword extraction:
```python
    with record_query_stage(query_param.mode, "extract_keywords_llm"):
        hl_keywords, ll_keywords = await get_keywords_from_query(
            query, query_param, global_config, hashing_kv
        )
```
2. In `_build_query_context()`:
```python
    # Stage 1: Pure search
    with record_query_stage(query_param.mode, "perform_kg_search"):
        search_result = await _perform_kg_search(
            query,
            ll_keywords,
            hl_keywords,
            knowledge_graph_inst,
            entities_vdb,
            relationships_vdb,
            text_chunks_db,
            query_param,
            chunks_vdb,
            progress_callback=progress_callback,
        )

    # Stage 2: Token truncation
    with record_query_stage(query_param.mode, "token_truncation"):
        truncation_result = await _apply_token_truncation(
            search_result,
            query_param,
            text_chunks_db.global_config,
        )

    # Stage 3: Merge chunks
    with record_query_stage(query_param.mode, "merge_chunks"):
        merged_chunks = await _merge_all_chunks(
            filtered_entities=truncation_result["filtered_entities"],
            filtered_relations=truncation_result["filtered_relations"],
            vector_chunks=search_result["vector_chunks"],
            query=query,
            knowledge_graph_inst=knowledge_graph_inst,
            text_chunks_db=text_chunks_db,
            query_param=query_param,
            progress_callback=progress_callback,
        )
```
3. In `naive_query()`:
```python
    with record_query_stage("naive", "vector_search_chunks"):
        results = await chunks_vdb.query(query, top_k=query_param.top_k)
```

In `../LightRAG/lightrag/api/routers/query_routes.py`:
In `query_text()` endpoint handler:
```python
from lightrag.query_metrics import record_query_duration, record_query_total

        start_time = time.perf_counter()
        query_status = "error"
        try:
            ...
            result = await rag.aquery_llm(request.query, param=param)
            query_status = "success"
            ...
        finally:
            total_duration = time.perf_counter() - start_time
            record_query_total(request.mode, query_status)
            record_query_duration(request.mode, query_status, total_duration)
```

- [ ] **Step 4: Run tests to verify no regressions**

Run: `pytest ../LightRAG/tests/test_operate_metrics_integration.py -v`
Expected: PASS

- [ ] **Step 5: Commit in LightRAG repo**

```bash
cd ../LightRAG
git add lightrag/operate.py lightrag/api/routers/query_routes.py tests/test_operate_metrics_integration.py
git commit -m "feat(metrics): instrument kg_query stages and /query route in LightRAG"
cd ../DeepTutor
```

---

### Task 6: Expose `/metrics` on LightRAG FastAPI Server with Multi-Worker Support

**Files:**
- Modify: `../LightRAG/lightrag/api/lightrag_server.py`
- Test: `../LightRAG/tests/test_lightrag_metrics_endpoint.py`

**Interfaces:**
- Produces: `GET /metrics` route on LightRAG server.

- [ ] **Step 1: Write test for `/metrics` endpoint on LightRAG server**

Create `../LightRAG/tests/test_lightrag_metrics_endpoint.py`:
```python
import pytest
from fastapi.testclient import TestClient
from lightrag.api.lightrag_server import app

def test_lightrag_metrics_endpoint():
    client = TestClient(app)
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "lightrag_query_duration_seconds" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest ../LightRAG/tests/test_lightrag_metrics_endpoint.py -v`
Expected: FAIL (404 Not Found)

- [ ] **Step 3: Implement `/metrics` in `lightrag_server.py`**

In `../LightRAG/lightrag/api/lightrag_server.py`:
```python
@app.get("/metrics", tags=["metrics"])
def get_metrics():
    """Prometheus metrics scraping endpoint."""
    import os
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        generate_latest,
        CollectorRegistry,
        multiprocess,
        REGISTRY,
    )

    if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        data = generate_latest(registry)
    else:
        data = generate_latest(REGISTRY)

    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest ../LightRAG/tests/test_lightrag_metrics_endpoint.py -v`
Expected: PASS (status_code == 200)

- [ ] **Step 5: Commit in LightRAG repo**

```bash
cd ../LightRAG
git add lightrag/api/lightrag_server.py tests/test_lightrag_metrics_endpoint.py
git commit -m "feat(api): add GET /metrics endpoint to LightRAG server"
cd ../DeepTutor
```

---

### Task 7: End-to-End Integration Smoke Test & Verification

**Files:**
- Create: `tests/integration/test_e2e_observability_smoke.py`

**Interfaces:**
- Exercises: DeepTutor `LightRagServerClient` -> simulated/mocked LightRAG Server -> scraping both `/metrics` endpoints.

- [ ] **Step 1: Write the end-to-end smoke test**

Create `tests/integration/test_e2e_observability_smoke.py`:
```python
import pytest
import httpx
from fastapi.testclient import TestClient
from deeptutor.api.main import app
from deeptutor.services.rag.pipelines.lightrag_server.client import LightRagServerClient
from deeptutor.services.rag.pipelines.lightrag_server.config import LightRagServerConfig

@pytest.mark.asyncio
async def test_end_to_end_metrics_collection_and_scrape():
    # 1. Scrape DeepTutor /metrics initial state
    client = TestClient(app)
    initial_metrics = client.get("/metrics").text
    assert "deeptutor_lightrag_remote_request_duration_seconds" in initial_metrics

    # 2. Simulate a query through LightRagServerClient with mocked server response
    config = LightRagServerConfig(base_url="http://mock-lightrag:9621")
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

    # 3. Scrape DeepTutor /metrics after query
    updated_metrics = client.get("/metrics").text
    assert 'deeptutor_lightrag_remote_request_duration_seconds_count{endpoint="/query",mode="hybrid",status_code="200"}' in updated_metrics
    assert 'deeptutor_lightrag_server_reported_duration_seconds_count{mode="hybrid"}' in updated_metrics
    assert 'deeptutor_lightrag_network_latency_seconds_count{mode="hybrid"}' in updated_metrics
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/integration/test_e2e_observability_smoke.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_e2e_observability_smoke.py
git commit -m "test(observability): add end-to-end smoke test verifying metrics scrape flow"
```
