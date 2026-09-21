"""Streaming TTS helpers for on-device VieNEU inference.

Provides an async generator that wraps ``VieneuLocalTTSAdapter.infer_stream()``
so the WebSocket/SSE API router can push audio chunks to the client as they
are produced — first audio arrives in ~140 ms (CPU int8) or ~115 ms (GPU).

Usage from the API router::

    from deeptutor.services.voice.stream_tts import stream_tts_chunks

    async for wav_chunk in stream_tts_chunks(text, config):
        await websocket.send_bytes(wav_chunk)
"""

from __future__ import annotations

import asyncio
import io
import logging
import struct
import wave
from typing import TYPE_CHECKING, Any, AsyncIterator

import numpy as np

from deeptutor.services.voice.base import VoiceProviderError
from deeptutor.services.voice.config import TTSConfig

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 48_000
_NUM_CHANNELS = 1
_SAMPLE_WIDTH = 2  # 16-bit PCM


def _chunk_to_pcm16(audio_np: np.ndarray) -> bytes:
    """Convert a float32 numpy chunk to raw PCM16 bytes (no WAV header)."""
    clipped = np.clip(audio_np, -1.0, 1.0)
    return (clipped * 32767).astype(np.int16).tobytes()


def _make_wav_header(data_length: int) -> bytes:
    """Build a minimal WAV header for PCM16 mono @ 48 kHz.

    This creates a self-contained WAV header that can be prepended to PCM
    data. ``data_length`` is the number of **PCM bytes** that will follow.
    """
    byte_rate = _SAMPLE_RATE * _NUM_CHANNELS * _SAMPLE_WIDTH
    block_align = _NUM_CHANNELS * _SAMPLE_WIDTH
    buf = io.BytesIO()
    buf.write(b"RIFF")
    riff_size = min(36 + data_length, 0xFFFFFFFF)
    buf.write(struct.pack("<I", riff_size))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))  # chunk size
    buf.write(struct.pack("<H", 1))  # PCM format
    buf.write(struct.pack("<H", _NUM_CHANNELS))
    buf.write(struct.pack("<I", _SAMPLE_RATE))
    buf.write(struct.pack("<I", byte_rate))
    buf.write(struct.pack("<H", block_align))
    buf.write(struct.pack("<H", _SAMPLE_WIDTH * 8))
    buf.write(b"data")
    data_size = min(data_length, 0xFFFFFFFF - 36)
    buf.write(struct.pack("<I", data_size))
    return buf.getvalue()



async def stream_tts_chunks(
    text: str,
    config: TTSConfig,
    *,
    wrap_wav: bool = True,
) -> AsyncIterator[bytes]:
    """Async generator that yields audio chunks from VieNEU local TTS.

    Each chunk is either:
    - A self-contained WAV file fragment (``wrap_wav=True``, default) —
      the very first chunk includes the WAV header with a placeholder
      length; subsequent chunks are raw PCM16 bytes.  Clients that
      understand streaming WAV (or just concatenate chunks) get valid
      audio.
    - Raw PCM16 bytes (``wrap_wav=False``) for clients that handle
      their own framing (e.g. WebRTC, Pipecat).

    Args:
        text: The text to synthesize.
        config: Resolved TTS config (must use ``adapter="vieneu_local"``).
        wrap_wav: Whether to prepend a WAV header on the first chunk.

    Yields:
        ``bytes`` — audio data chunks.
    """
    from deeptutor.services.voice.adapters import get_tts_adapter

    adapter = get_tts_adapter(config.adapter)

    # Only the VieNEU adapter supports frame-by-frame streaming.
    if not hasattr(adapter, "infer_stream"):
        raise VoiceProviderError(
            f"Adapter {config.adapter!r} does not support streaming TTS. "
            "Streaming is only available with the vieneu_local adapter."
        )

    loop = asyncio.get_running_loop()

    # Run the synchronous infer_stream generator in a background thread.
    # We use a queue to bridge the sync iterator ↔ async generator gap.
    queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=32)

    async def _producer() -> None:
        """Run the sync infer_stream in a thread and push chunks to the queue."""
        def _run() -> None:
            try:
                for chunk_np in adapter.infer_stream(text, config):
                    pcm = _chunk_to_pcm16(chunk_np)
                    # Use call_soon_threadsafe to put items from the background thread.
                    asyncio.run_coroutine_threadsafe(
                        queue.put(pcm), loop
                    ).result(timeout=30)
            except Exception as exc:
                logger.error("VieNEU streaming TTS error: %s", exc, exc_info=True)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop).result(timeout=5)

        await loop.run_in_executor(None, _run)

    # Start the producer concurrently.
    producer_task = asyncio.create_task(_producer())

    first_chunk = True
    try:
        while True:
            data = await queue.get()
            if data is None:
                break

            if first_chunk and wrap_wav:
                # We don't know total length upfront; use 0xFFFFFFFF as
                # placeholder (streaming WAV convention).
                header = _make_wav_header(0xFFFFFFFF)
                yield header + data
            else:
                yield data

            first_chunk = False
    finally:
        # Ensure producer is cleaned up.
        if not producer_task.done():
            producer_task.cancel()
            try:
                await producer_task
            except (asyncio.CancelledError, Exception):
                pass


__all__ = ["stream_tts_chunks"]
