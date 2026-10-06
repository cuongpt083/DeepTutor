"""Turn-attachment resolution for imagegen reference images."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from deeptutor.core.context import Attachment, UnifiedContext
from deeptutor.services.subagent.images import reference_data_uris


def _png_b64() -> str:
    return base64.b64encode(b"png-bytes").decode("ascii")


def test_inline_data_uri_and_raw_base64() -> None:
    raw = _png_b64()
    uris = reference_data_uris(
        [
            Attachment(type="image", base64=f"data:image/png;base64,{raw}", mime_type="image/png"),
            Attachment(type="image", base64=raw, mime_type="image/jpeg"),
        ]
    )
    assert uris[0] == f"data:image/png;base64,{raw}"
    assert uris[1] == f"data:image/jpeg;base64,{raw}"


def test_store_path_is_resolved_and_external_url_skipped(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "shot.png"
    target.write_bytes(b"from-store")

    class _Store:
        def resolve_path(self, *, session_id: str, attachment_id: str, filename: str) -> Path:
            assert (session_id, attachment_id, filename) == ("s1", "a1", "shot.png")
            return target

    monkeypatch.setattr("deeptutor.services.storage.get_attachment_store", lambda: _Store())
    uris = reference_data_uris(
        [
            Attachment(type="image", url="/files/attachments/s1/a1/shot.png", mime_type="image/png"),
            Attachment(type="image", url="https://example.invalid/secret.png", mime_type="image/png"),
            Attachment(type="file", url="/files/attachments/s1/a1/notes.pdf"),
        ]
    )
    assert uris == [f"data:image/png;base64,{base64.b64encode(b'from-store').decode('ascii')}"]


def test_fourth_image_is_dropped() -> None:
    raw = _png_b64()
    uris = reference_data_uris(
        [Attachment(type="image", base64=raw, mime_type="image/png") for _ in range(4)]
    )
    assert len(uris) == 3


def test_augment_injects_refs_without_overriding_explicit() -> None:
    from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline

    pipeline = AgenticChatPipeline.__new__(AgenticChatPipeline)
    context = UnifiedContext(
        attachments=[Attachment(type="image", base64=_png_b64(), mime_type="image/png")]
    )
    injected = pipeline._augment_tool_kwargs("imagegen", {"prompt": "diagram"}, context)
    assert injected["reference_images"][0].startswith("data:image/png;base64,")
    explicit = pipeline._augment_tool_kwargs(
        "imagegen",
        {"prompt": "diagram", "reference_images": ["data:image/png;base64,abc"]},
        context,
    )
    assert explicit["reference_images"] == ["data:image/png;base64,abc"]


@pytest.mark.asyncio
async def test_imagegen_tool_forwards_data_uris_only(tmp_path: Path, monkeypatch) -> None:
    import deeptutor.services.imagegen as imagegen_mod
    from deeptutor.services.workspace import get_content_workspace_service
    from deeptutor.tools.media_gen_tool import ImagegenTool

    captured: dict = {}

    async def _generate(prompt, **kwargs):
        captured["prompt"] = prompt
        captured.update(kwargs)
        return [(b"png", "image/png")]

    monkeypatch.setattr(imagegen_mod, "generate_image", _generate)
    selected = tmp_path / "selected-workspace"
    selected.mkdir()
    monkeypatch.setenv("DEEPTUTOR_WORKSPACE_ROOT", str(selected))
    runtime = get_content_workspace_service().create_runtime_context(
        capability="chat", session_id="session-a", turn_id="turn-a"
    )
    result = await ImagegenTool().execute(
        prompt="a cat",
        reference_images=[
            "data:image/png;base64,abc",
            "https://example.invalid/x.png",
            "not-a-uri",
        ],
        _workspace_dir=str(Path(runtime.output_dir) / "media"),
        _workspace_id=runtime.workspace_id,
    )
    assert result.success
    assert captured["reference_images"] == ["data:image/png;base64,abc"]
