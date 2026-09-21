"""Unit tests for local VieNEU TTS adapter and streaming pipeline."""

from __future__ import annotations

import asyncio
import io
import sys
import types
import wave
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from deeptutor.services.voice.adapters.vieneu_local import (
    VieneuLocalTTSAdapter,
    VieneuModelManager,
    _float32_to_pcm16_wav,
    _model_cache_dir,
    get_model_manager,
)
from deeptutor.services.voice.base import VoiceProviderError
from deeptutor.services.voice.config import TTSConfig
from deeptutor.services.voice.stream_tts import _chunk_to_pcm16, _make_wav_header, stream_tts_chunks


class FakeVieneuEngine:
    """Mock for the vieneu.Vieneu engine."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.precision = kwargs.get("precision", "fp32")

    def infer(self, text: str, voice: str = "Phạm Tuyên") -> np.ndarray:
        # Generate 0.1s of a 440Hz sine wave @ 48kHz
        sample_rate = 48_000
        duration = 0.1
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        return (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

    def infer_stream(self, text: str, voice: str = "Phạm Tuyên"):
        for _ in range(3):
            yield np.zeros(4800, dtype=np.float32)

    def list_preset_voices(self) -> list[tuple[str, str]]:
        return [("Phạm Tuyên (Chuẩn)", "Phạm Tuyên"), ("Mai Phương", "Mai Phương")]


@pytest.fixture
def fake_vieneu_module(monkeypatch: pytest.MonkeyPatch):
    """Inject a fake ``vieneu`` module into sys.modules."""
    module = types.ModuleType("vieneu")
    module.Vieneu = FakeVieneuEngine  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "vieneu", module)
    return module


@pytest.mark.asyncio
async def test_float32_to_pcm16_wav():
    """Verify WAV conversion produces valid 48kHz mono 16-bit PCM audio."""
    sample_rate = 48_000
    samples = np.array([-1.5, -0.5, 0.0, 0.5, 1.5], dtype=np.float32)
    wav_bytes = _float32_to_pcm16_wav(samples)

    assert wav_bytes.startswith(b"RIFF")
    with wave.open(io.BytesIO(wav_bytes), "rb") as r:
        assert r.getnchannels() == 1
        assert r.getsampwidth() == 2
        assert r.getframerate() == sample_rate
        assert r.getnframes() == len(samples)


@pytest.mark.asyncio
async def test_synthesize_success(fake_vieneu_module):
    """Test standard synthesis with mocked VieNEU engine."""
    adapter = VieneuLocalTTSAdapter()
    config = TTSConfig(
        model="VieNeu-TTS-v3-Turbo",
        provider_name="vieneu_local",
        adapter="vieneu_local",
        voice="Phạm Tuyên",
    )
    wav_bytes, content_type = await adapter.synthesize("Xin chào Việt Nam", config)

    assert content_type == "audio/wav"
    assert len(wav_bytes) > 44  # Has WAV header + data
    with wave.open(io.BytesIO(wav_bytes), "rb") as r:
        assert r.getframerate() == 48_000
        assert r.getnchannels() == 1


@pytest.mark.asyncio
async def test_synthesize_missing_vieneu_raises(monkeypatch: pytest.MonkeyPatch):
    """When vieneu is not installed, adapter raises informative VoiceProviderError."""
    monkeypatch.setitem(sys.modules, "vieneu", None)
    adapter = VieneuLocalTTSAdapter()
    adapter._engine = None

    config = TTSConfig(
        model="VieNeu-TTS-v3-Turbo",
        provider_name="vieneu_local",
        adapter="vieneu_local",
    )
    with pytest.raises(VoiceProviderError, match="vieneu.*not installed"):
        await adapter.synthesize("Xin chào", config)


@pytest.mark.asyncio
async def test_synthesize_empty_audio_raises(monkeypatch: pytest.MonkeyPatch):
    """When infer() returns empty audio, adapter raises VoiceProviderError."""
    class EmptyEngine(FakeVieneuEngine):
        def infer(self, text: str, voice: str = "Phạm Tuyên") -> np.ndarray:
            return np.array([], dtype=np.float32)

    module = types.ModuleType("vieneu")
    module.Vieneu = EmptyEngine  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "vieneu", module)

    adapter = VieneuLocalTTSAdapter()
    adapter._engine = None

    config = TTSConfig(
        model="VieNeu-TTS-v3-Turbo",
        provider_name="vieneu_local",
        adapter="vieneu_local",
    )
    with pytest.raises(VoiceProviderError, match="empty audio"):
        await adapter.synthesize("Xin chào", config)


def test_list_preset_voices(fake_vieneu_module):
    """Verify preset voices list is extracted from engine."""
    adapter = VieneuLocalTTSAdapter()
    config = TTSConfig(
        model="VieNeu-TTS-v3-Turbo",
        provider_name="vieneu_local",
        adapter="vieneu_local",
    )
    voices = adapter.list_preset_voices(config)
    assert len(voices) == 2
    assert voices[0] == ("Phạm Tuyên (Chuẩn)", "Phạm Tuyên")


@pytest.mark.asyncio
async def test_stream_tts_chunks_framing(fake_vieneu_module, monkeypatch: pytest.MonkeyPatch):
    """Verify stream_tts_chunks yields WAV header in first chunk, PCM thereafter."""
    adapter = VieneuLocalTTSAdapter()
    monkeypatch.setattr("deeptutor.services.voice.adapters.get_tts_adapter", lambda _: adapter)

    config = TTSConfig(
        model="VieNeu-TTS-v3-Turbo",
        provider_name="vieneu_local",
        adapter="vieneu_local",
    )

    chunks: list[bytes] = []
    async for chunk in stream_tts_chunks("Thử nghiệm phát âm trực tiếp", config, wrap_wav=True):
        chunks.append(chunk)

    assert len(chunks) == 3
    # First chunk contains WAV header (starts with RIFF)
    assert chunks[0].startswith(b"RIFF")
    # Remaining chunks are raw PCM frames
    assert not chunks[1].startswith(b"RIFF")
    assert not chunks[2].startswith(b"RIFF")


@pytest.mark.asyncio
async def test_stream_tts_chunks_raw_pcm(fake_vieneu_module, monkeypatch: pytest.MonkeyPatch):
    """When wrap_wav=False, even the first chunk has no WAV header."""
    adapter = VieneuLocalTTSAdapter()
    monkeypatch.setattr("deeptutor.services.voice.adapters.get_tts_adapter", lambda _: adapter)

    config = TTSConfig(
        model="VieNeu-TTS-v3-Turbo",
        provider_name="vieneu_local",
        adapter="vieneu_local",
    )

    chunks: list[bytes] = []
    async for chunk in stream_tts_chunks("Thử nghiệm raw", config, wrap_wav=False):
        chunks.append(chunk)

    assert len(chunks) == 3
    assert not chunks[0].startswith(b"RIFF")


@pytest.mark.asyncio
async def test_stream_tts_non_streaming_adapter_raises():
    """Adapters without infer_stream raise VoiceProviderError when streaming requested."""
    config = TTSConfig(
        model="gpt-4o-audio",
        provider_name="openai_compat",
        adapter="openai_compat",
    )
    with pytest.raises(VoiceProviderError, match="does not support streaming"):
        async for _ in stream_tts_chunks("Hello", config):
            pass


@pytest.mark.asyncio
async def test_vieneu_model_manager_status_and_download(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Verify VieneuModelManager status tracking and download simulation."""
    manager = VieneuModelManager()
    monkeypatch.setattr(manager, "cache_dir", str(tmp_path))

    # Initially empty
    assert not manager.is_model_cached()
    status = manager.get_status()
    assert status["status"] == "idle"
    assert status["cached"] is False

    # Simulate download
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    manager.add_listener(queue)

    # Monkeypatch the background downloader to write a dummy file
    def fake_download():
        (tmp_path / "model.onnx").write_bytes(b"dummy model weights")

    with patch.object(manager, "download_model") as mock_dl:
        async def mock_download_impl(force=False):
            fake_download()
            manager.status = "ready"
            manager.progress = 100.0
            manager._broadcast(manager.get_status())
            return True

        mock_dl.side_effect = mock_download_impl
        success = await manager.download_model()
        assert success is True

    # Listeners received progress
    event = await queue.get()
    assert event["status"] == "ready"
    assert manager.is_model_cached()
    manager.remove_listener(queue)


def test_strip_markdown_extracts_tts_summary():
    """Verify strip_markdown_for_speech prioritizes <tts_summary> when present."""
    from deeptutor.services.voice.base import strip_markdown_for_speech

    text = (
        "<tts_summary>\n"
        "Phương trình bậc hai có hai nghiệm là 2 và -2.\n"
        "</tts_summary>\n\n"
        "### Chi tiết giải thuật\n"
        "$$x^2 = 4 \\implies x = \\pm 2$$\n"
        "```python\nx = 2\n```"
    )
    cleaned = strip_markdown_for_speech(text)
    assert cleaned == "Phương trình bậc hai có hai nghiệm là 2 và -2."
    assert "Chi tiết giải thuật" not in cleaned
    assert "python" not in cleaned

