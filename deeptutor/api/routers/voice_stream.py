"""Streaming TTS WebSocket endpoint for on-device VieNEU inference.

Provides a WebSocket endpoint at ``/api/voice/tts/stream`` that accepts a
JSON message with the text to synthesize and streams back audio chunks as
binary WebSocket frames.

Protocol
--------

1. Client opens ``ws://.../api/voice/tts/stream``
2. Client sends a JSON text frame::

       {"text": "Xin chào!", "voice": "Phạm Tuyên"}

3. Server streams binary frames (PCM16 WAV chunks @ 48 kHz mono)
4. Server sends a JSON text frame ``{"done": true}`` when finished
5. Connection can be reused for subsequent requests

Also provides an SSE endpoint at ``/api/voice/tts/stream`` (GET) for
clients that prefer Server-Sent Events over WebSocket.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from deeptutor.services.voice import VoiceProviderError, strip_markdown_for_speech
from deeptutor.services.voice.stream_tts import stream_tts_chunks

logger = logging.getLogger(__name__)

router = APIRouter()


class StreamTTSParams(BaseModel):
    """Query parameters / JSON body for streaming TTS."""

    text: str = Field(..., min_length=1)
    voice: str | None = None
    strip_markdown: bool = True


def _resolve_stream_config(voice: str | None = None):
    """Resolve the VieNEU local TTS config from the catalog.

    Falls back to defaults if the catalog isn't configured for VieNEU.
    """
    from deeptutor.services.voice.config import TTSConfig

    try:
        from deeptutor.services.config.provider_runtime import resolve_tts_runtime_config

        config = resolve_tts_runtime_config()
    except (ValueError, Exception):
        # Fallback to VieNEU defaults when no TTS catalog is configured.
        config = TTSConfig(
            model="VieNeu-TTS-v3-Turbo",
            provider_name="vieneu_local",
            adapter="vieneu_local",
        )

    # Override voice if provided.
    if voice:
        config.voice = voice

    # Ensure we're using the local adapter for streaming.
    if config.adapter != "vieneu_local":
        logger.info(
            "Streaming TTS requested but active adapter is %r; "
            "switching to vieneu_local for streaming.",
            config.adapter,
        )
        config.adapter = "vieneu_local"

    return config


# -----------------------------------------------------------------------
# WebSocket endpoint
# -----------------------------------------------------------------------


@router.websocket("/tts/stream")
async def tts_stream_ws(websocket: WebSocket) -> None:
    """Stream synthesised audio over a WebSocket connection.

    Accepts repeated JSON text frames with ``{"text": ..., "voice": ...}``
    and responds with binary WAV chunk frames followed by a JSON
    ``{"done": true}`` text frame.
    """
    await websocket.accept()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON"})
                continue

            text = (msg.get("text") or "").strip()
            if not text:
                await websocket.send_json({"error": "Empty text"})
                continue

            voice = msg.get("voice")
            strip_md = msg.get("strip_markdown", True)

            if strip_md:
                text = strip_markdown_for_speech(text)
                if not text:
                    await websocket.send_json({"error": "Nothing to speak after cleaning."})
                    continue

            config = _resolve_stream_config(voice=voice)

            try:
                async for chunk in stream_tts_chunks(text, config, wrap_wav=True):
                    await websocket.send_bytes(chunk)
            except VoiceProviderError as exc:
                await websocket.send_json({"error": str(exc)})
                continue

            await websocket.send_json({"done": True})

    except WebSocketDisconnect:
        logger.debug("TTS stream WebSocket disconnected.")
    except Exception:
        logger.exception("Unexpected error in TTS stream WebSocket.")


# -----------------------------------------------------------------------
# SSE / chunked-transfer endpoint (fallback for non-WS clients)
# -----------------------------------------------------------------------


@router.get("/tts/stream")
async def tts_stream_sse(
    text: str = Query(..., min_length=1, description="Text to synthesize"),
    voice: str | None = Query(default=None, description="VieNEU voice preset name"),
    strip_markdown: bool = Query(default=True, description="Clean markdown before synthesis"),
) -> StreamingResponse:
    """Stream synthesised audio via chunked HTTP transfer.

    Returns ``audio/wav`` with chunked transfer-encoding. The first chunk
    includes the WAV header; subsequent chunks are raw PCM16.
    """
    prepared = strip_markdown_for_speech(text) if strip_markdown else text.strip()
    if not prepared:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nothing to speak after cleaning the text.",
        )

    config = _resolve_stream_config(voice=voice)

    async def _generate():
        try:
            async for chunk in stream_tts_chunks(prepared, config, wrap_wav=True):
                yield chunk
        except VoiceProviderError as exc:
            logger.warning("TTS streaming error: %s", exc)

    return StreamingResponse(
        _generate(),
        media_type="audio/wav",
        headers={
            "Cache-Control": "no-store",
            "Transfer-Encoding": "chunked",
        },
    )


# -----------------------------------------------------------------------
# Preset voices listing
# -----------------------------------------------------------------------


@router.get("/tts/voices")
async def list_tts_voices() -> dict:
    """Return the list of available VieNEU preset voices."""
    config = _resolve_stream_config()

    from deeptutor.services.voice.adapters import get_tts_adapter

    adapter = get_tts_adapter(config.adapter)
    if hasattr(adapter, "list_preset_voices"):
        voices = adapter.list_preset_voices(config)
        return {
            "voices": [{"label": label, "id": vid} for label, vid in voices],
        }
    return {"voices": []}


# -----------------------------------------------------------------------
# Model management & progress reporting
# -----------------------------------------------------------------------


@router.get("/tts/model-status")
async def get_model_status() -> dict:
    """Return current VieNEU weights cache and download status."""
    from deeptutor.services.voice.adapters.vieneu_local import get_model_manager

    return get_model_manager().get_status()


@router.post("/tts/model-download")
async def trigger_model_download() -> dict:
    """Trigger background download of VieNEU weights."""
    import asyncio
    from deeptutor.services.voice.adapters.vieneu_local import get_model_manager

    manager = get_model_manager()
    status_info = manager.get_status()
    if status_info["status"] == "downloading":
        return {"status": "already_downloading", "detail": "Download already in progress"}

    asyncio.create_task(manager.download_model())
    return {"status": "download_started", "detail": "Model download initiated in background"}


@router.get("/tts/model-progress")
async def stream_model_progress() -> StreamingResponse:
    """Stream model download progress events via Server-Sent Events (SSE)."""
    import asyncio
    from deeptutor.services.voice.adapters.vieneu_local import get_model_manager

    manager = get_model_manager()
    queue: asyncio.Queue[dict] = asyncio.Queue()
    manager.add_listener(queue)

    async def _event_generator():
        try:
            # Yield initial status immediately
            init_status = manager.get_status()
            yield f"data: {json.dumps(init_status)}\n\n"

            while True:
                data = await queue.get()
                yield f"data: {json.dumps(data)}\n\n"
                if data.get("status") in {"ready", "failed"}:
                    break
        finally:
            manager.remove_listener(queue)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

