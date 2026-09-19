# Prometheus Observability & Performance Tuning Specification for DeepTutor and LightRAG

## 1. Overview & Goals

This specification defines the architecture, instrumentation points, metrics catalog, and tuning procedures for end-to-end observability across **DeepTutor** and **LightRAG Server** (`~\Workspaces\LightRAG`).

### Problem Statement
During queries against a remote LightRAG server, response times are excessively long (often 10s–30s+), causing sluggish chat turns and degraded user experience. Because both systems currently lack granular metric collection and timing breakdowns, operators cannot reliably identify whether the latency bottleneck stems from:
1. Network transfer latency and serialization between DeepTutor and the remote LightRAG server.
2. Server-side keyword extraction (LLM call in `get_keywords_from_query`).
3. Vector storage searches across chunks, entities, and relationships.
4. Graph traversal over the knowledge graph (NetworkX / Neo4j / PGGraph).
5. Context token truncation, pruning, and chunk merging.
6. DeepTutor orchestration overhead, tool dispatch, or local prompt assembly.

### Goals
- Implement a standardized Prometheus observability layer (`prometheus_client`) in both **DeepTutor** and **LightRAG Server**.
- Expose standard `GET /metrics` endpoints on both HTTP servers.
- Isolate network round-trip overhead from internal RAG processing time.
- Deconstruct LightRAG's internal execution pipeline (`kg_query` and `naive_query`) into observable stages via lightweight, non-fatal context managers.
- Provide a clear PromQL diagnostic playbook and tuning guidelines to optimize system parameters (`mode`, `top_k`, `chunk_top_k`, keyword extraction models, caching, connection pooling).
- Guarantee zero application crashes from metric recording failures (fail-safe / non-fatal contract).

---

## 2. Architecture & Data Flow

```
[User / Client]
       │
       ▼ (1) Send message / turn
┌────────────────────────────────────────────────────────────────────────┐
│ DeepTutor (Port 8001)                                                  │
│                                                                        │
│  ├─ ChatOrchestrator (`deeptutor/runtime/orchestrator.py`)             │
│  │   └─ Records: `deeptutor_turn_duration_seconds`                    │
│  │                                                                     │
│  ├─ Tool Dispatch (`deeptutor/tools/builtin/`)                         │
│  │   └─ Records: `deeptutor_tool_execution_duration_seconds`          │
│  │                                                                     │
│  ├─ RAGService (`deeptutor/services/rag/service.py`)                   │
│  │   └─ Records: `deeptutor_rag_search_duration_seconds`               │
│  │                                                                     │
│  ├─ LightRagServerClient (`pipelines/lightrag_server/client.py`)       │
│  │   ├─ Client RTT: `deeptutor_lightrag_remote_request_duration_seconds│
│  │   ├─ Server reported: `deeptutor_lightrag_server_reported_duration_seconds`
│  │   ├─ Net latency: `deeptutor_lightrag_network_latency_seconds`     │
│  │   └─ Payload bytes: `deeptutor_lightrag_payload_bytes`              │
│  │                                                                     │
│  └─ FastAPI Exporter: `GET /metrics`                                   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ (2) HTTP POST /query
                                    │     {"query": "...", "mode": "...", "only_need_context": True}
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ LightRAG Server (Port 9621 - `~\Workspaces\LightRAG`)                  │
│                                                                        │
│  ├─ API Route (`lightrag/api/routers/query_routes.py`)                 │
│  │   ├─ Records: `lightrag_query_requests_total`                       │
│  │   └─ Records: `lightrag_query_duration_seconds`                    │
│  │                                                                     │
│  ├─ Execution Pipeline (`lightrag/operate.py`):                        │
│  │   ├─ Stage 1: `extract_keywords_llm` (High-level & Low-level)       │
│  │   ├─ Stage 2: `perform_kg_search` (Vector DB + Graph search)        │
│  │   ├─ Stage 3: `token_truncation` (Token budget fitting)             │
│  │   ├─ Stage 4: `merge_chunks` (Related chunks mapping)               │
│  │   └─ Stage 5: `format_context` / `llm_generation` (if applicable)   │
│  │   └─ Records: `lightrag_query_stage_duration_seconds`              │
│  │                                                                     │
│  ├─ LLM Calls (`lightrag/operate.py`):                                 │
│  │   └─ Records: `lightrag_llm_call_duration_seconds`                  │
│  │                                                                     │
│  └─ FastAPI Exporter: `GET /metrics` (Supports single & multi-worker)  │
└────────────────────────────────────────────────────────────────────────┘
       ▲                                                 ▲
       └────────────────────────┬────────────────────────┘
                                │ (3) Periodic scrape
                       [Prometheus Server]
                                │
                                ▼
                       [Grafana Dashboard]
```

### Latency Decomposition Formula
$$\text{Client Turn Time} = T_{\text{turn}}$$
$$\text{Client Observed RTT} = T_{\text{client\_rtt}}$$
$$\text{Server Reported Time} = T_{\text{server\_reported}} \quad (\text{from LightRAG response payload})$$
$$\text{Network Latency} = \max(0.0, T_{\text{client\_rtt}} - T_{\text{server\_reported}})$$
$$T_{\text{server\_reported}} \approx T_{\text{extract\_keywords\_llm}} + T_{\text{perform\_kg\_search}} + T_{\text{token\_truncation}} + T_{\text{merge\_chunks}}$$

---

## 3. DeepTutor Observability Specification

### 3.1 Module: `deeptutor/core/observability/metrics.py`
Provides thread-safe, non-fatal Prometheus metrics instrumentation:

```python
from prometheus_client import Counter, Histogram, REGISTRY

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
    "Payload size of requests and responses exchanged with LightRAG",
    ["direction", "mode"],
    buckets=[128, 512, 1024, 4096, 16384, 65536, 262144, 1048576],
)
```

### 3.2 FastAPI Endpoint: `deeptutor/api/routers/metrics.py`
- Route: `GET /metrics`
- Handler:
  ```python
  from fastapi import APIRouter, Response
  from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

  router = APIRouter(tags=["metrics"])

  @router.get("/metrics")
  async def metrics_endpoint():
      return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
  ```
- Mounted in `deeptutor/api/main.py`: `app.include_router(metrics.router)`.

### 3.3 Client Instrumentation: `deeptutor/services/rag/pipelines/lightrag_server/client.py`
In `query_context(self, query: str, mode: str)`:
```python
start_time = time.perf_counter()
status_code = "error"
server_reported_time = None
req_bytes = len(query.encode("utf-8"))

try:
    async with self._open() as client:
        resp = await client.post(
            "/query",
            json={"query": query, "mode": mode, "only_need_context": True},
        )
    status_code = str(resp.status_code)
    data = self._json(resp)
    resp_bytes = len(resp.content)
    server_reported_time = data.get("response_time")
    ...
finally:
    client_rtt = time.perf_counter() - start_time
    record_remote_request(endpoint="/query", mode=mode, status_code=status_code, duration=client_rtt)
    record_payload_bytes(req_bytes=req_bytes, resp_bytes=resp_bytes, mode=mode)
    if server_reported_time is not None:
        record_server_reported(mode=mode, duration=float(server_reported_time))
        net_latency = max(0.0, client_rtt - float(server_reported_time))
        record_network_latency(mode=mode, duration=net_latency)
```

---

## 4. LightRAG Server Observability Specification (`~\Workspaces\LightRAG`)

### 4.1 Module: `lightrag/query_metrics.py`
Defines metrics and safe stage execution context managers:

```python
from prometheus_client import Counter, Histogram, CollectorRegistry, REGISTRY
import os
import time
from contextlib import contextmanager

QUERY_REQUESTS = Histogram(
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

@contextmanager
def record_query_stage(mode: str, stage: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start
        try:
            QUERY_STAGE_DURATION.labels(mode=mode, stage=stage).observe(duration)
        except Exception:
            pass
```

### 4.2 Instrumentation in `lightrag/operate.py`
1. **Keyword Extraction:**
   ```python
   with record_query_stage(query_param.mode, "extract_keywords_llm"):
       hl_keywords, ll_keywords = await get_keywords_from_query(...)
   ```
2. **Knowledge Graph Search:**
   In `_build_query_context()`:
   ```python
   with record_query_stage(query_param.mode, "perform_kg_search"):
       search_result = await _perform_kg_search(...)
   ```
3. **Token Truncation:**
   ```python
   with record_query_stage(query_param.mode, "token_truncation"):
       truncation_result = await _apply_token_truncation(...)
   ```
4. **Chunk Merging:**
   ```python
   with record_query_stage(query_param.mode, "merge_chunks"):
       merged_chunks = await _merge_all_chunks(...)
   ```
5. **Naive Query:**
   In `naive_query()`:
   ```python
   with record_query_stage("naive", "vector_search_chunks"):
       chunks = await chunks_vdb.query(...)
   ```

### 4.3 Multi-Worker Gunicorn & Uvicorn Support in `lightrag_server.py`
In `lightrag/api/lightrag_server.py`:
```python
@app.get("/metrics")
def metrics_endpoint():
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest, CollectorRegistry, multiprocess

    if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        data = generate_latest(registry)
    else:
        data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
```

---

## 5. Performance Tuning Decision Playbook

Using Prometheus/Grafana metrics to make grounded performance tuning choices:

| Metric Pattern | Root Cause | Tuning Action |
|---|---|---|
| `deeptutor_lightrag_network_latency_seconds` > 1.0s (or > 30% of total RTT) | High network latency between DeepTutor and remote LightRAG host. | 1. Enable HTTP connection pooling / keep-alive in `LightRagServerClient`.<br>2. Enable gzip content encoding on large context payloads.<br>3. Co-locate servers on the same local network or Kubernetes cluster. |
| `lightrag_query_stage_duration_seconds{stage="extract_keywords_llm"}` > 5.0s | Keyword extraction LLM model is slow or rate-limited. | 1. Configure a faster model for the `query` role (e.g. `gpt-4o-mini`, `claude-3-5-haiku`, or local `vllm/qwen2.5-7b`).<br>2. Enable keyword cache in LightRAG (`llm_response_cache`).<br>3. Allow DeepTutor to pass pre-computed `hl_keywords` / `ll_keywords`. |
| `lightrag_query_stage_duration_seconds{stage="perform_kg_search"}` > 3.0s | Vector search or Graph traversal bottleneck. | 1. Reduce `top_k` and `chunk_top_k` in query parameters.<br>2. Switch from in-memory / brute-force vector search to indexed vector store (Qdrant, Milvus, PGVector with HNSW).<br>3. Optimize graph storage (ensure Neo4j/Memgraph indices on entity names). |
| `lightrag_query_stage_duration_seconds{stage="merge_chunks"}` or `token_truncation` high | Too many chunks retrieved, excessive token serialization. | 1. Reduce `max_total_tokens`, `max_entity_tokens`, `max_relation_tokens`.<br>2. Lower `related_chunk_number`. |
| DeepTutor turn time high but `deeptutor_rag_search_duration_seconds` is low | Bottleneck is not RAG; it is the reasoning LLM generation or orchestrator prompt building. | 1. Tune DeepTutor LLM provider / streaming params.<br>2. Inspect capability prompt overhead. |

---

## 6. Verification & Test Plan

### 6.1 Unit Tests
- **DeepTutor Metrics Module:** Test metric registration, recording functions, bucket ranges, and graceful exception handling.
- **DeepTutor LightRagServerClient Test:** Mock HTTP responses with and without `response_time`; verify network latency computation and payload size recording.
- **DeepTutor `/metrics` Route Test:** Assert HTTP 200 and text payload contains `deeptutor_` prefixed metrics.
- **LightRAG Query Metrics Module:** Verify `record_query_stage` accurately measures durations and ignores exceptions.
- **LightRAG `/metrics` Route Test:** Assert HTTP 200 and text payload contains `lightrag_` prefixed metrics.

### 6.2 Smoke Test & End-to-End Validation
1. Start DeepTutor API server (`deeptutor serve --port 8001`).
2. Start LightRAG server on port 9621.
3. Query `GET http://localhost:8001/metrics` and `GET http://localhost:9621/metrics` (baseline count = 0).
4. Execute a RAG search through DeepTutor against a LightRAG knowledge base.
5. Re-query both `/metrics` endpoints:
   - Verify `deeptutor_lightrag_remote_request_duration_seconds_count >= 1`.
   - Verify `deeptutor_lightrag_server_reported_duration_seconds_count >= 1`.
   - Verify `lightrag_query_stage_duration_seconds_count{stage="extract_keywords_llm"} >= 1`.
   - Verify `lightrag_query_stage_duration_seconds_count{stage="perform_kg_search"} >= 1`.
