"""Unit tests for OpenAICompatImagegenAdapter with agy2api features."""

from __future__ import annotations

import base64
import pytest

from deeptutor.services.imagegen.adapters.openai_compat import (
    OpenAICompatImagegenAdapter,
    _ASPECT_RATIO_SIZES,
)
from deeptutor.services.imagegen.config import ImagegenConfig
from deeptutor.services.generation_http import GenerationProviderError


@pytest.mark.asyncio
async def test_openai_compat_aspect_ratio_and_reference_images(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_payload = {}

    class MockResponse:
        status_code = 200

        def json(self):
            dummy_b64 = base64.b64encode(b"fake_image_bytes").decode("ascii")
            return {"data": [{"b64_json": dummy_b64}]}

        def raise_for_status(self):
            pass

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def post(self, url, headers=None, json=None):
            nonlocal captured_payload
            captured_payload = json
            return MockResponse()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", MockClient)

    adapter = OpenAICompatImagegenAdapter()
    config = ImagegenConfig(
        model="agy-image-model",
        base_url="http://192.168.100.17:8000/v1",
        aspect_ratio="16:9",
        reference_images=["data:image/png;base64,abc1234"],
        response_format="b64_json",
    )

    images = await adapter.generate("draw a cute robot", config)
    assert len(images) == 1
    assert images[0][0] == b"fake_image_bytes"

    # Validate aspect_ratio converted to size
    assert captured_payload["size"] == "1792x1024"
    # Validate reference_images forwarded to payload
    assert captured_payload["reference_images"] == ["data:image/png;base64,abc1234"]


@pytest.mark.asyncio
async def test_openai_compat_reference_images_limit() -> None:
    adapter = OpenAICompatImagegenAdapter()
    config = ImagegenConfig(
        model="agy-image-model",
        base_url="http://192.168.100.17:8000/v1",
        reference_images=["ref1", "ref2", "ref3", "ref4"],
    )
    with pytest.raises(GenerationProviderError, match="At most 3 reference images"):
        await adapter.generate("test prompt", config)
