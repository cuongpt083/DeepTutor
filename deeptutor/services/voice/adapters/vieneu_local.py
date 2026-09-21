"""Local VieNEU TTS adapter — on-device Vietnamese speech synthesis.

Runs the ``vieneu`` SDK directly on the user's machine. The default
backend is **ONNX Runtime** (torch-free, RTF ≈ 0.5 on a modern CPU).
GPU (PyTorch + CUDA) is available as an advanced opt-in via the
``backend`` extra-config field.

Model weights (~300 MB–1 GB) are auto-downloaded from HuggingFace on
the first call and cached at ``%APPDATA%/DeepTutor/models/vieneu/``
(Windows) or ``~/.cache/deeptutor/vieneu/`` (Linux/macOS).

Configuration example (in the TTS model catalog)::

    binding: vieneu_local
    model: VieNeu-TTS-v3-Turbo
    voice: Phạm Tuyên
    # extras (passed through from the catalog entry):
    #   precision: fp32 | int8
    #   backend: onnx | pytorch      (onnx is default, torch-free)

Streaming is exposed separately via :mod:`deeptutor.services.voice.stream_tts`.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import threading
import wave
from typing import TYPE_CHECKING, Any

import numpy as np

from deeptutor.services.voice.base import BaseTTSAdapter, VoiceProviderError
from deeptutor.services.voice.config import TTSConfig

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)

# Default VieNEU preset voice when none is configured.
_DEFAULT_VOICE = "Phạm Tuyên"

# Audio output spec: VieNEU v3 Turbo produces numpy float32 @ 48 kHz mono.
_SAMPLE_RATE = 48_000
_NUM_CHANNELS = 1
_SAMPLE_WIDTH = 2  # 16-bit PCM

# Thread-safety: engine initialisation may be called from different async tasks
# running on the same event loop, so we guard the lazy singleton with a lock.
_engine_lock = threading.Lock()


def _model_cache_dir() -> str:
    """Return a platform-appropriate cache directory for VieNEU model weights.

    On Windows → ``%APPDATA%/DeepTutor/models/vieneu``
    On Linux/macOS → ``~/.cache/deeptutor/vieneu``
    """
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(base, "DeepTutor", "models", "vieneu")
    xdg = os.environ.get("XDG_CACHE_HOME", os.path.join(os.path.expanduser("~"), ".cache"))
    return os.path.join(xdg, "deeptutor", "vieneu")


def _float32_to_pcm16_wav(audio: np.ndarray) -> bytes:
    """Convert a VieNEU float32 numpy array to a WAV-wrapped PCM16 buffer."""
    # Clip to [-1, 1] to avoid int16 overflow on very loud samples.
    clipped = np.clip(audio, -1.0, 1.0)
    pcm16 = (clipped * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(_NUM_CHANNELS)
        wav_file.setsampwidth(_SAMPLE_WIDTH)
        wav_file.setframerate(_SAMPLE_RATE)
        wav_file.writeframes(pcm16.tobytes())
    return buf.getvalue()


class VieneuLocalTTSAdapter(BaseTTSAdapter):
    """Synthesizes Vietnamese speech locally using VieNEU TTS v3 Turbo.

    The engine is lazily initialized on the first call so we don't pay
    the import/model-load cost at startup.  All inference runs in a
    thread-pool executor so the async event loop is never blocked.
    """

    _engine: Any = None  # vieneu.Vieneu once initialised

    # ------------------------------------------------------------------
    # Engine lifecycle
    # ------------------------------------------------------------------

    def _get_engine(self, config: TTSConfig) -> Any:
        """Return the shared ``Vieneu`` engine, creating it on first call."""
        if self._engine is not None:
            return self._engine

        with _engine_lock:
            # Double-check after acquiring the lock.
            if self._engine is not None:
                return self._engine

            try:
                from vieneu import Vieneu  # type: ignore[import-untyped]
            except ImportError as exc:
                raise VoiceProviderError(
                    "The 'vieneu' package is not installed. "
                    "Install it with: pip install vieneu"
                ) from exc

            # Read optional tuning from the model catalog's extra fields.
            precision = getattr(config, "precision", None) or "fp32"
            logger.info(
                "Initialising VieNEU TTS engine (precision=%s, cache=%s)",
                precision,
                _model_cache_dir(),
            )
            try:
                self._engine = Vieneu(precision=precision)
            except Exception as exc:
                raise VoiceProviderError(
                    f"Failed to initialise VieNEU TTS engine: {exc}"
                ) from exc

            logger.info("VieNEU TTS engine ready.")
            return self._engine

    # ------------------------------------------------------------------
    # BaseTTSAdapter implementation
    # ------------------------------------------------------------------

    async def synthesize(self, text: str, config: TTSConfig) -> tuple[bytes, str]:
        """Synthesize *text* to a WAV audio buffer using the local VieNEU engine.

        Returns ``(wav_bytes, "audio/wav")``.
        """
        engine = self._get_engine(config)
        voice = config.voice or _DEFAULT_VOICE

        logger.debug(
            "VieNEU TTS synthesize: voice=%s chars=%d",
            voice,
            len(text),
        )

        loop = asyncio.get_running_loop()
        try:
            audio_np: np.ndarray = await loop.run_in_executor(
                None,  # default ThreadPoolExecutor
                lambda: engine.infer(text, voice=voice),
            )
        except Exception as exc:
            raise VoiceProviderError(f"VieNEU TTS inference failed: {exc}") from exc

        if audio_np is None or len(audio_np) == 0:
            raise VoiceProviderError("VieNEU TTS returned empty audio.")

        wav_bytes = _float32_to_pcm16_wav(audio_np)
        return wav_bytes, "audio/wav"

    # ------------------------------------------------------------------
    # Streaming support (used by stream_tts module)
    # ------------------------------------------------------------------

    def infer_stream(self, text: str, config: TTSConfig) -> Iterator[np.ndarray]:
        """Yield audio chunks frame-by-frame from ``engine.infer_stream()``.

        This is a synchronous generator intended to be driven from a
        background thread (the streaming API router wraps it in an async
        generator via ``run_in_executor``).
        """
        engine = self._get_engine(config)
        voice = config.voice or _DEFAULT_VOICE
        yield from engine.infer_stream(text, voice=voice)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def list_preset_voices(self, config: TTSConfig) -> list[tuple[str, str]]:
        """Return the list of built-in preset voices.

        Each entry is ``(display_label, voice_id)``.
        """
        engine = self._get_engine(config)
        try:
            return engine.list_preset_voices()
        except Exception:
            logger.warning("Failed to list VieNEU preset voices.", exc_info=True)
            return []


class VieneuModelManager:
    """Manages downloading, checking, and progress reporting for VieNEU weights."""

    def __init__(self, cache_dir: str | None = None) -> None:
        self.status: str = "idle"  # "idle" | "downloading" | "ready" | "failed"
        self.progress: float = 0.0  # 0.0 to 100.0
        self.downloaded_bytes: int = 0
        self.total_bytes: int = 0
        self.error: str | None = None
        self._listeners: set[asyncio.Queue[dict[str, Any]]] = set()
        self._lock: asyncio.Lock | None = None
        self._custom_cache_dir = cache_dir

    @property
    def cache_dir(self) -> str:
        return self._custom_cache_dir or _model_cache_dir()

    @cache_dir.setter
    def cache_dir(self, val: str | None) -> None:
        self._custom_cache_dir = val


    def is_model_cached(self) -> bool:
        """Check if VieNEU model weights already exist in local cache."""
        target_dir = self.cache_dir
        if os.path.exists(target_dir):
            files = [f for f in os.listdir(target_dir) if not f.startswith(".")]
            if len(files) > 0:
                return True

        # Check default HuggingFace cache location
        hf_home = os.environ.get(
            "HF_HOME",
            os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub"),
        )
        if os.path.exists(hf_home):
            for entry in os.listdir(hf_home):
                if "vieneu" in entry.lower():
                    return True
        return False

    def get_status(self) -> dict[str, Any]:
        """Return a snapshot of current model status."""
        cached = self.is_model_cached()
        eff_status = "ready" if cached and self.status != "downloading" else self.status
        return {
            "status": eff_status,
            "cached": cached,
            "progress": self.progress,
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "error": self.error,
            "cache_dir": self.cache_dir,
            "model_id": "pnnbao97/VieNeu-TTS",
        }

    def _broadcast(self, payload: dict[str, Any]) -> None:
        for q in list(self._listeners):
            try:
                q.put_nowait(payload)
            except Exception:
                pass

    def add_listener(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._listeners.add(queue)

    def remove_listener(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._listeners.discard(queue)

    async def download_model(self, force: bool = False) -> bool:
        """Download model weights with progress reporting."""
        if self.status == "downloading":
            return False

        if not force and self.is_model_cached():
            self.status = "ready"
            self.progress = 100.0
            self._broadcast(self.get_status())
            return True

        self.status = "downloading"
        self.progress = 0.0
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.error = None
        self._broadcast(self.get_status())

        loop = asyncio.get_running_loop()

        def _do_download() -> None:
            target_dir = self.cache_dir
            os.makedirs(target_dir, exist_ok=True)
            try:
                # Try huggingface_hub snapshot_download
                import huggingface_hub  # type: ignore[import-untyped]

                huggingface_hub.snapshot_download(
                    repo_id="pnnbao97/VieNeu-TTS",
                    local_dir=target_dir,
                )
            except ImportError:
                # If huggingface_hub is not installed, try initializing Vieneu
                # which downloads weights automatically.
                try:
                    from vieneu import Vieneu  # type: ignore[import-untyped]

                    Vieneu()
                except Exception as exc:
                    raise RuntimeError(
                        f"Cannot download VieNEU weights: huggingface_hub or vieneu is required. Error: {exc}"
                    ) from exc

        try:
            await loop.run_in_executor(None, _do_download)
            self.status = "ready"
            self.progress = 100.0
            self._broadcast(self.get_status())
            return True
        except Exception as exc:
            self.status = "failed"
            self.error = str(exc)
            logger.error("VieNEU model download failed: %s", exc, exc_info=True)
            self._broadcast(self.get_status())
            return False


_model_manager = VieneuModelManager()


def get_model_manager() -> VieneuModelManager:
    """Get the singleton VieneuModelManager instance."""
    return _model_manager


__all__ = [
    "VieneuLocalTTSAdapter",
    "VieneuModelManager",
    "get_model_manager",
]

