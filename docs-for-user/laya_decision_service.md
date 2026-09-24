# Laya System 1 Decision Service

## Overview

DeepTutor integrates **Laya** (an open-weights System 1 decision model based on ModernBERT-large 421M and mmBERT-base 322M) as an automated, low-latency router to decide whether user requests require retrieving context from attached Knowledge Bases (**KB Preseed Gating**).

```
User Turn
   │
   ▼
Attached KBs? ──(No)──► Skip Preseed (0ms)
   │ (Yes)
   ▼
┌───────────────────────────────┐
│     Laya Decision Router      │  ◄── ~30ms Local ONNX Inference
│   (Predict: needs_kb_preseed) │
└──────────────┬────────────────┘
               │
       ┌───────┴───────┐
   (Score >= 0.7)   (Score < 0.7)
       │               │
       ▼               ▼
  Preseed KB      Skip Preseed (Direct Loop)
(Hybrid Search)        │
       │               │
       └───────┬───────┘
               ▼
      Agentic Loop (LLM)
  (RAG tool remains available as fallback)
```

---

## Key Benefits

| Scenario | Legacy Static (`ENABLE_KB_PRESEED=false`) | Legacy Static (`ENABLE_KB_PRESEED=true`) | With Laya (`KB_PRESEED_MODE=auto`) |
| :--- | :--- | :--- | :--- |
| **Casual chat / greetings** | ~1.5s (Direct response) | **~3.5s** (Unnecessary 2s KB hybrid search) | **~1.53s** (30ms Laya bypasses preseed) |
| **Domain KB question** | **~5.5s** (2 LLM rounds: tool call + response) | ~2.5s (Preseeded, 1 LLM round) | **~2.53s** (30ms Laya + Preseed, 1 LLM round) |

---

## Configuration

Settings can be specified in `data/user/settings/system.json` or via environment variables in `.env`:

```json
{
  "kb_preseed_mode": "auto",
  "laya_service_url": "http://deeptutor-laya:8000/v1/decide",
  "laya_threshold": 0.70
}
```

Environment variable equivalents:
- `KB_PRESEED_MODE`: `off` (default), `always` (legacy true), or `auto` / `laya`.
- `LAYA_SERVICE_URL`: URL of the Laya HTTP decision API (default: `http://deeptutor-laya:8000/v1/decide`).
- `LAYA_THRESHOLD`: Confidence threshold to trigger preseed (default: `0.70`).

---

## Deployment via Docker Compose

Laya is packaged as a standalone microservice that attaches to DeepTutor's container network.

### 1. Launch Laya Service

**With Docker:**
```bash
docker compose -f docker-compose.laya.yml up -d
```

**With Podman (`study` network):**
```bash
DEEPTUTOR_NETWORK=study podman compose -f docker-compose.laya.yml up -d
```

### 2. Verify Health

```bash
curl http://127.0.0.1:8002/health
```

Output:
```json
{"status": "ok", "model": "convai/laya-modernbert-en", "onnx_ready": true}
```

### 3. Test Decision Endpoint

```bash
curl -X POST http://127.0.0.1:8002/v1/decide \
  -H "Content-Type: application/json" \
  -d '{"user_message": "Hello, how are you?", "knowledge_bases": ["course_kb"]}'
```

Output:
```json
{
  "should_preseed": false,
  "confidence": 0.01,
  "decision_primitive": "boolean",
  "latency_ms": 1.2,
  "model": "convai/laya-modernbert-en"
}
```

---

## Model Weights & INT8 Quantization

To export and quantize model weights for minimal CPU footprint (~400MB RAM, <35ms latency):

```bash
python -m deeptutor.services.laya.export_onnx \
  --model-id convai/laya-modernbert-en \
  --output-dir data/models/laya \
  --quantize-int8
```

---

## Resiliency & Fail-Soft Architecture

1. **In-Memory Circuit Breaker**: If the Laya service is down, after 3 consecutive failures the circuit opens for 30 seconds. Inquiries are immediately bypassed to standard chat without waiting for HTTP timeouts.
2. **500ms Fast-Path Timeout**: The client enforces a strict 500ms timeout. If Laya does not reply in time, the turn proceeds normally.
3. **Safety Net**: If Laya predicts `False` on an ambiguous query, the `rag` tool remains mounted in the LLM tool surface so the agent can still query the KB if needed.
