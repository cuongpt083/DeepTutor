import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from transformers import AutoTokenizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("laya-service")

MODEL_NAME = os.getenv("LAYA_MODEL_NAME_OR_PATH", "convaiinnovations/laya")
ONNX_MODEL_FILE = os.getenv("LAYA_ONNX_FILE", "model.onnx")
NUM_THREADS = int(os.getenv("ONNX_NUM_THREADS", "2"))
HF_TOKEN = os.getenv("HF_TOKEN") or None

tokenizer = None
ort_session = None


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global tokenizer, ort_session
    logger.info("Initializing Laya ONNX inference service...")

    # 1. Setup ONNX Runtime session options
    sess_options = ort.SessionOptions()
    sess_options.intra_op_num_threads = NUM_THREADS
    sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

    # 2. Check for candidate local ONNX model paths
    candidate_paths = [
        os.path.join("/app/models", ONNX_MODEL_FILE),
        os.path.join(MODEL_NAME, ONNX_MODEL_FILE) if os.path.isdir(MODEL_NAME) else "",
        ONNX_MODEL_FILE,
        "/app/model.onnx",
    ]
    model_path = next((p for p in candidate_paths if p and os.path.exists(p)), None)

    if model_path:
        try:
            ort_session = ort.InferenceSession(model_path, sess_options, providers=["CPUExecutionProvider"])
            logger.info("Successfully loaded ONNX session from %s", model_path)
        except Exception as exc:
            logger.error("Failed to load ONNX model from %s: %s", model_path, exc)
            ort_session = None
    else:
        logger.warning(
            "ONNX model file not found in /app/models/%s. Running in standby heuristic mode. "
            "To activate full neural inference, export weights using 'python -m deeptutor.services.laya.export_onnx' "
            "and mount to ./data/models/laya.",
            ONNX_MODEL_FILE,
        )
        ort_session = None

    # 3. Load tokenizer (local dir or Hugging Face)
    tokenizer_sources = []
    if os.path.isdir("/app/models") and os.path.exists("/app/models/tokenizer_config.json"):
        tokenizer_sources.append("/app/models")
    tokenizer_sources.append(MODEL_NAME)
    # ModernBERT fallback tokenizer if the model repo is not yet mirrored
    tokenizer_sources.append("answerdotai/ModernBERT-base")

    for src in tokenizer_sources:
        try:
            tokenizer = AutoTokenizer.from_pretrained(src, token=HF_TOKEN, trust_remote_code=True)
            logger.info("Loaded tokenizer from %s", src)
            break
        except Exception as exc1:
            try:
                tokenizer = AutoTokenizer.from_pretrained(src, token=HF_TOKEN, use_fast=False, trust_remote_code=True)
                logger.info("Loaded tokenizer (slow fallback) from %s", src)
                break
            except Exception as exc2:
                logger.debug("Could not load tokenizer from %s: fast=%s, slow=%s", src, exc1, exc2)

    if tokenizer is None:
        logger.warning(
            "Could not load tokenizer from HuggingFace (offline or requires auth). "
            "Standby heuristic mode is active."
        )

    yield
    logger.info("Shutting down Laya service...")


app = FastAPI(title="Laya Decision Service", version="1.0.0", lifespan=lifespan)


class DecideRequest(BaseModel):
    user_message: str = Field(..., description="User input message")
    knowledge_bases: list[str] = Field(default_factory=list, description="Names of attached knowledge bases")
    threshold: float = Field(default=0.70, ge=0.0, le=1.0, description="Confidence threshold for should_preseed")


class DecideResponse(BaseModel):
    should_preseed: bool
    confidence: float
    decision_primitive: str = "boolean"
    latency_ms: float
    model: str


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "onnx_ready": ort_session is not None,
        "tokenizer_ready": tokenizer is not None,
    }


@app.post("/v1/decide", response_model=DecideResponse)
async def decide(req: DecideRequest):
    start_time = time.perf_counter()

    # Rule-based fast bypass: if user message is empty or no KBs attached
    if not req.user_message.strip() or not req.knowledge_bases:
        elapsed = (time.perf_counter() - start_time) * 1000
        return DecideResponse(
            should_preseed=False,
            confidence=0.0,
            decision_primitive="boolean",
            latency_ms=round(elapsed, 2),
            model=MODEL_NAME,
        )

    # Fast heuristic check for greeting/gratitude casual conversation
    normalized_msg = req.user_message.strip().lower()
    casual_patterns = {
        "hi", "hello", "hey", "chào", "chào bạn", "cảm ơn", "thanks", "thank you",
        "bye", "tạm biệt", "ok", "okay", "good morning", "good evening",
        "how are you", "who are you", "bạn là ai",
    }
    if normalized_msg in casual_patterns:
        elapsed = (time.perf_counter() - start_time) * 1000
        return DecideResponse(
            should_preseed=False,
            confidence=0.01,
            decision_primitive="boolean",
            latency_ms=round(elapsed, 2),
            model=MODEL_NAME,
        )

    # If ONNX session and tokenizer are ready, perform model inference
    if ort_session is not None and tokenizer is not None:
        try:
            kbs_str = ", ".join(req.knowledge_bases)
            prompt = (
                f"User Message: {req.user_message}\n"
                f"Attached Knowledge Bases: {kbs_str}\n"
                f"Question: Does answering this request require retrieving domain-specific documents from the attached knowledge bases?"
            )
            inputs = tokenizer(
                prompt,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="np",
            )
            ort_inputs = {
                "input_ids": inputs["input_ids"].astype(np.int64),
                "attention_mask": inputs["attention_mask"].astype(np.int64),
            }
            outputs = ort_session.run(None, ort_inputs)
            logits = outputs[0]
            probs = sigmoid(logits)
            prob_true = float(probs[0][1]) if probs.shape[-1] > 1 else float(probs[0][0])
            should_preseed = prob_true >= req.threshold

            elapsed = (time.perf_counter() - start_time) * 1000
            return DecideResponse(
                should_preseed=should_preseed,
                confidence=round(prob_true, 4),
                decision_primitive="boolean",
                latency_ms=round(elapsed, 2),
                model=MODEL_NAME,
            )
        except Exception as exc:
            logger.error("Inference error: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))

    # Standby fallback heuristic mode:
    # If the message contains domain indicators (e.g. mentions KB, document, tài liệu, sách, file, theo...), preseed.
    domain_keywords = {
        "tài liệu", "sách", "giáo trình", "document", "file", "kb", "knowledge base",
        "theo", "theo như", "trang", "chương", "bài giảng", "định lý", "pdf",
    }
    has_domain_hint = any(kw in normalized_msg for kw in domain_keywords)
    elapsed = (time.perf_counter() - start_time) * 1000
    return DecideResponse(
        should_preseed=has_domain_hint,
        confidence=0.75 if has_domain_hint else 0.30,
        decision_primitive="boolean",
        latency_ms=round(elapsed, 2),
        model=f"{MODEL_NAME} (standby-heuristic)",
    )
