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

MODEL_NAME = os.getenv("LAYA_MODEL_NAME_OR_PATH", "convai/laya-modernbert-en")
ONNX_MODEL_FILE = os.getenv("LAYA_ONNX_FILE", "model.onnx")
NUM_THREADS = int(os.getenv("ONNX_NUM_THREADS", "2"))

tokenizer = None
ort_session = None


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global tokenizer, ort_session
    logger.info("Initializing Laya ONNX inference service...")
    try:
        # Load tokenizer from HuggingFace / local path
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        logger.info("Loaded tokenizer for %s", MODEL_NAME)

        # Setup ONNX Runtime session options
        sess_options = ort.SessionOptions()
        sess_options.intra_op_num_threads = NUM_THREADS
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        # Check for local onnx file or load via optimum/download
        model_path = os.path.join(MODEL_NAME, ONNX_MODEL_FILE) if os.path.isdir(MODEL_NAME) else ONNX_MODEL_FILE
        if os.path.exists(model_path):
            ort_session = ort.InferenceSession(model_path, sess_options, providers=["CPUExecutionProvider"])
            logger.info("Loaded ONNX session from %s", model_path)
        else:
            logger.warning(
                "ONNX model file %s not found on disk. Initializing in standby/stub mode. "
                "Mount or export ONNX weights to activate full local model.",
                model_path,
            )
            ort_session = None
    except Exception as exc:
        logger.error("Failed to load Laya model: %s", exc, exc_info=True)

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

    # If ONNX session is ready, perform model inference
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
            # Assuming binary classification head: index 1 is probability of True
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

    # Standby fallback: if model is not yet loaded, return safe default
    elapsed = (time.perf_counter() - start_time) * 1000
    return DecideResponse(
        should_preseed=False,
        confidence=0.5,
        decision_primitive="boolean",
        latency_ms=round(elapsed, 2),
        model=f"{MODEL_NAME} (standby)",
    )
