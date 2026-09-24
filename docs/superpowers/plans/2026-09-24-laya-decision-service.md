# Laya Decision Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate Laya (a System 1 decision model) as an automated, low-latency gatekeeper that decides whether to preseed Knowledge Base context into user requests, complete with runtime configuration, resilient circuit breaker, trace reporting, and an ONNX export script.

**Architecture:** A standalone containerized microservice running Laya via ONNX Runtime communicates with DeepTutor over a shared Docker/Podman network. DeepTutor's `AgenticLoopPipeline` queries the Laya client during `_retrieve_kb_seed_block` with an in-memory circuit breaker and strict 500ms timeout, falling back gracefully to runtime RAG tool dispatch if the service is unreachable.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, ONNX Runtime, Hugging Face Transformers/Optimum, Pytest, Docker Compose.

**Spec:** Dynamic gating of `_retrieve_kb_seed_block` in `deeptutor/agents/loop/pipeline.py` replacing static `ENABLE_KB_PRESEED` flag with `KB_PRESEED_MODE` (`off` | `always` | `auto`).

## Global Constraints

- Must maintain 100% backward compatibility with existing `ENABLE_KB_PRESEED` environment variable.
- Must fail-soft on any network error or timeout (<500ms) without disrupting user chat turns.
- Must honor DeepTutor's runtime settings hierarchy (`data/user/settings/system.json` > process env > defaults).
- No floating-point or unstructured text parsing from Laya; only typed boolean/confidence output.

---

### Task 1: Runtime Settings Integration for Laya

**Files:**
- Modify: `deeptutor/services/config/runtime_settings.py:50-70`
- Test: `tests/services/test_laya_settings.py`

**Interfaces:**
- Consumes: `get_system_settings()`, `system.json`.
- Produces: `kb_preseed_mode: str` ("off" | "always" | "auto"), `laya_service_url: str`, `laya_threshold: float`.

- [x] **Step 1: Write the failing test**

```python
# tests/services/test_laya_settings.py
from deeptutor.services.config.runtime_settings import (
    DEFAULT_SYSTEM_SETTINGS,
    get_system_settings,
    normalize_system_settings,
)


def test_default_system_settings_include_laya_config():
    assert "kb_preseed_mode" in DEFAULT_SYSTEM_SETTINGS
    assert DEFAULT_SYSTEM_SETTINGS["kb_preseed_mode"] == "off"
    assert "laya_service_url" in DEFAULT_SYSTEM_SETTINGS
    assert DEFAULT_SYSTEM_SETTINGS["laya_service_url"] == "http://deeptutor-laya:8000/v1/decide"
    assert "laya_threshold" in DEFAULT_SYSTEM_SETTINGS
    assert DEFAULT_SYSTEM_SETTINGS["laya_threshold"] == 0.70


def test_normalize_system_settings_validates_laya():
    raw = {
        "kb_preseed_mode": "AUTO",
        "laya_service_url": "http://localhost:8002/v1/decide",
        "laya_threshold": 1.5,  # should clamp to 1.0
    }
    normalized = normalize_system_settings(raw)
    assert normalized["kb_preseed_mode"] == "auto"
    assert normalized["laya_service_url"] == "http://localhost:8002/v1/decide"
    assert normalized["laya_threshold"] == 1.0
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/services/test_laya_settings.py -v`
Expected: FAIL with `AssertionError: assert 'kb_preseed_mode' in DEFAULT_SYSTEM_SETTINGS`

- [x] **Step 3: Implement minimal code to make test pass**

In `deeptutor/services/config/runtime_settings.py`, add to `DEFAULT_SYSTEM_SETTINGS`:
```python
    "kb_preseed_mode": "off",  # "off" | "always" | "auto"
    "laya_service_url": "http://deeptutor-laya:8000/v1/decide",
    "laya_threshold": 0.70,
```
And inside `normalize_system_settings(raw: dict[str, Any])`:
```python
    mode = str(raw.get("kb_preseed_mode", DEFAULT_SYSTEM_SETTINGS["kb_preseed_mode"]) or "off").lower().strip()
    if mode not in ("off", "always", "auto", "laya"):
        mode = "off"
    normalized["kb_preseed_mode"] = mode

    url = str(raw.get("laya_service_url", DEFAULT_SYSTEM_SETTINGS["laya_service_url"]) or "").strip()
    normalized["laya_service_url"] = url or DEFAULT_SYSTEM_SETTINGS["laya_service_url"]

    try:
        thresh = float(raw.get("laya_threshold", DEFAULT_SYSTEM_SETTINGS["laya_threshold"]))
    except (TypeError, ValueError):
        thresh = DEFAULT_SYSTEM_SETTINGS["laya_threshold"]
    normalized["laya_threshold"] = max(0.0, min(1.0, thresh))
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/services/test_laya_settings.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add deeptutor/services/config/runtime_settings.py tests/services/test_laya_settings.py
git commit -m "feat(settings): add kb_preseed_mode and laya settings configuration"
```

---

### Task 2: Circuit Breaker & Resilient HTTP Client

**Files:**
- Modify: `deeptutor/services/laya/client.py`
- Test: `tests/services/test_laya.py`

**Interfaces:**
- Consumes: `laya_service_url: str`, `laya_threshold: float`, `user_message: str`, `knowledge_bases: list[str]`.
- Produces: `should_preseed_with_laya(...) -> bool` with fast failure rejection when circuit is open.

- [x] **Step 1: Write the failing test for Circuit Breaker**

Add to `tests/services/test_laya.py`:
```python
@pytest.mark.asyncio
async def test_circuit_breaker_trips_after_consecutive_failures():
    from deeptutor.services.laya.client import LayaClient, should_preseed_with_laya
    import httpx

    client = LayaClient()
    # Mock 3 consecutive failures
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
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/services/test_laya.py -k test_circuit_breaker_trips_after_consecutive_failures -v`
Expected: FAIL with `ImportError: cannot import name 'LayaClient'`

- [x] **Step 3: Implement minimal code to make test pass**

Update `deeptutor/services/laya/client.py` with `LayaClient` class:
```python
import time
from typing import Any
import httpx
import logging

logger = logging.getLogger(__name__)

class LayaClient:
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 30.0):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.consecutive_failures = 0
        self.last_failure_time = 0.0

    def is_circuit_open(self) -> bool:
        if self.consecutive_failures >= self.failure_threshold:
            if time.time() - self.last_failure_time < self.cooldown_seconds:
                return True
            # Cooldown expired, half-open
            self.consecutive_failures = 0
        return False

    def record_success(self):
        self.consecutive_failures = 0

    def record_failure(self):
        self.consecutive_failures += 1
        self.last_failure_time = time.time()

    async def should_preseed(
        self,
        user_message: str,
        knowledge_bases: list[str],
        *,
        threshold: float = 0.70,
        service_url: str = "http://deeptutor-laya:8000/v1/decide",
        timeout: float = 0.50,
    ) -> bool:
        if not user_message or not knowledge_bases or self.is_circuit_open():
            return False

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    service_url,
                    json={"user_message": user_message, "knowledge_bases": knowledge_bases, "threshold": threshold},
                )
                if resp.status_code == 200:
                    self.record_success()
                    return bool(resp.json().get("should_preseed", False))
                self.record_failure()
        except Exception:
            self.record_failure()
        return False

_default_client = LayaClient()

async def should_preseed_with_laya(user_message: str, knowledge_bases: list[str], **kwargs) -> bool:
    return await _default_client.should_preseed(user_message, knowledge_bases, **kwargs)
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/services/test_laya.py -v`
Expected: ALL PASS

- [x] **Step 5: Commit**

```bash
git add deeptutor/services/laya/client.py tests/services/test_laya.py
git commit -m "feat(laya): add circuit breaker to prevent repeated timeouts on service outage"
```

---

### Task 3: Pipeline Tracing & Stream Event Reporting

**Files:**
- Modify: `deeptutor/agents/loop/pipeline.py:1468-1510`
- Test: `tests/agents/chat/test_laya_pipeline_trace.py`

**Interfaces:**
- Consumes: `StreamBus`, `context.user_message`, `context.knowledge_bases`.
- Produces: Trace event emitted on `StreamBus` reporting Laya's decision and confidence.

- [x] **Step 1: Write the failing test**

```python
# tests/agents/chat/test_laya_pipeline_trace.py
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
    events = []
    bus.subscribe(lambda event: events.append(event))

    with patch("deeptutor.services.laya.client.should_preseed_with_laya", new_callable=AsyncMock) as mock_laya:
        mock_laya.return_value = False
        ctx = UnifiedContext(user_message="Hello", knowledge_bases=["kb1"])
        should_preseed = await pipe._should_preseed_kb(ctx, ["kb1"], "Hello", stream=bus)
        assert should_preseed is False

        # Verify trace event was emitted
        trace_events = [e for e in events if getattr(e, "metadata", {}).get("trace_role") == "laya_router"]
        assert len(trace_events) == 1
        assert trace_events[0].metadata["decision"] is False
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/agents/chat/test_laya_pipeline_trace.py -v`
Expected: FAIL with `TypeError: _should_preseed_kb() got an unexpected keyword argument 'stream'`

- [x] **Step 3: Implement minimal code to make test pass**

Update `_should_preseed_kb` in `deeptutor/agents/loop/pipeline.py`:
```python
    async def _should_preseed_kb(
        self,
        context: UnifiedContext,
        kbs: list[str],
        query: str,
        stream: StreamBus | None = None,
    ) -> bool:
        mode = os.getenv("KB_PRESEED_MODE", "").strip().lower()
        if mode in ("auto", "laya"):
            from deeptutor.services.laya.client import should_preseed_with_laya

            decision = await should_preseed_with_laya(query, kbs)
            if stream is not None:
                await stream.emit(
                    "trace",
                    source=self.event_source,
                    stage=self.event_stage,
                    metadata={
                        "trace_role": "laya_router",
                        "label": "Laya Decision",
                        "decision": decision,
                        "query": query,
                        "kbs": kbs,
                    },
                )
            return decision
        if mode in ("true", "always", "1", "yes"):
            return True
        if mode in ("false", "off", "0", "no"):
            return False
        return os.getenv("ENABLE_KB_PRESEED", "false").lower() in ("true", "1", "yes")
```
And pass `stream=stream` inside `_retrieve_kb_seed_block`.

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/agents/chat/test_laya_pipeline_trace.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add deeptutor/agents/loop/pipeline.py tests/agents/chat/test_laya_pipeline_trace.py
git commit -m "feat(pipeline): emit trace event for Laya preseed decision"
```

---

### Task 4: ONNX Export & Quantization Script

**Files:**
- Create: `services/laya/export_onnx.py`
- Modify: `services/laya/requirements.txt`
- Test: `tests/services/test_laya_export.py`

**Interfaces:**
- Consumes: CLI options `--model-id`, `--output-dir`, `--quantize-int8`.
- Produces: `model.onnx` optimized and ready for deployment.

- [x] **Step 1: Write test for export utility argument parsing**

```python
# tests/services/test_laya_export.py
from services.laya.export_onnx import parse_args


def test_parse_args_defaults():
    args = parse_args(["--model-id", "convai/laya-modernbert-en"])
    assert args.model_id == "convai/laya-modernbert-en"
    assert args.output_dir == "data/models/laya"
    assert args.quantize_int8 is False


def test_parse_args_quantize():
    args = parse_args(["--model-id", "convai/laya-modernbert-en", "--quantize-int8", "--output-dir", "custom/dir"])
    assert args.output_dir == "custom/dir"
    assert args.quantize_int8 is True
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/services/test_laya_export.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.laya.export_onnx'`

- [x] **Step 3: Implement minimal code for export script**

Create `services/laya/export_onnx.py`:
```python
"""Script to export Laya PyTorch weights to ONNX / INT8 format."""

import argparse
import os
import sys


def parse_args(args=None):
    parser = argparse.ArgumentParser(description="Export Laya to ONNX format")
    parser.add_argument("--model-id", default="convai/laya-modernbert-en", help="Hugging Face Model ID or local path")
    parser.add_argument("--output-dir", default="data/models/laya", help="Directory to save ONNX weights")
    parser.add_argument("--quantize-int8", action="store_true", help="Quantize exported model to INT8")
    return parser.parse_args(args)


def main():
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)
    print(f"Exporting {args.model_id} to {args.output_dir} (INT8={args.quantize_int8})...")
    # Uses optimum.exporters.onnx if installed
    try:
        from optimum.exporters.onnx import main_export
        main_export(model_name_or_path=args.model_id, output=args.output_dir, task="text-classification")
        if args.quantize_int8:
            from onnxruntime.quantization import quantize_dynamic, QuantType
            onnx_path = os.path.join(args.output_dir, "model.onnx")
            quant_path = os.path.join(args.output_dir, "model_quant.onnx")
            quantize_dynamic(onnx_path, quant_path, weight_type=QuantType.QInt8)
            os.replace(quant_path, onnx_path)
            print("Quantization to INT8 complete.")
    except ImportError:
        print("Please install optimum[onnxruntime] to run export.")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/services/test_laya_export.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add services/laya/export_onnx.py tests/services/test_laya_export.py
git commit -m "feat(laya): add ONNX and INT8 model export utility"
```

---

### Task 5: Documentation & Compose Orchestration

**Files:**
- Create: `docs/features/laya_decision_service.md`
- Modify: `docker-compose.laya.yml`
- Test: Manual verification with `curl` / Docker test.

- [x] **Step 1: Write documentation**

Create `docs/features/laya_decision_service.md` with:
- Architecture diagram (Gatekeeper between User & Pipeline).
- Setup commands (`docker compose -f docker-compose.laya.yml up -d`).
- Runtime settings documentation (`kb_preseed_mode=auto`).
- Benchmark performance comparison.

- [x] **Step 2: Commit**

```bash
git add docs/features/laya_decision_service.md
git commit -m "docs: add guide and architecture spec for Laya decision service"
```

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-24-laya-decision-service.md`. Two execution options:

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
