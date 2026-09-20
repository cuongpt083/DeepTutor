"""Unit tests for Discord markdown and LaTeX math formatting."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from deeptutor.partners.bus.events import OutboundMessage
from deeptutor.partners.channels.discord import DiscordChannel, DiscordConfig
from deeptutor.partners.channels.discord_formatter import (
    format_and_split_for_discord,
    format_for_discord,
)


def test_format_empty():
    assert format_for_discord("") == ""
    assert format_for_discord("   ") == ""


def test_format_math_latex_cleaned():
    md = "Mức calo mục tiêu (ước tính): $\\sim 1150 - 1250\\text{ kcal/ngày}$"
    text = format_for_discord(md)
    assert "\\sim" not in text
    assert "\\text" not in text
    assert "~ 1150 - 1250 kcal/ngày" in text


def test_format_inequalities_and_percentages():
    md = "Kéo tỷ lệ nước lên $\\ge 50\\%$, duy trì $\\le 9.5$ và tăng nhẹ $0.5 - 1\\text{ kg}$ cơ nạc."
    text = format_for_discord(md)
    assert "\\ge" not in text
    assert "\\le" not in text
    assert "\\%" not in text
    assert "≥ 50%" in text
    assert "≤ 9.5" in text
    assert "0.5 - 1 kg cơ nạc" in text


def test_format_math_symbols_and_greek():
    md = "Phương trình: $x^2 + y^2 = r^2$, $\\alpha = 30^\\circ$, $a \\times b \\pm c \\approx d$, $\\frac{x}{y}$"
    text = format_for_discord(md)
    assert "x² + y² = r²" in text
    assert "α = 30°" in text
    assert "a × b ± c ≈ d" in text
    assert "(x)/(y)" in text or "x/y" in text


def test_format_display_math_and_fractions():
    md = "$$x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}$$"
    text = format_for_discord(md)
    assert "$$" not in text
    assert "\\frac" not in text
    assert "\\sqrt" not in text
    assert "\\pm" not in text
    assert "x = (-b ± √(b² - 4ac))/(2a)" in text


def test_format_latex_brackets_delimiters():
    md = "\\[ \\sum_{i=1}^n x_i = S \\] và \\( \\lambda = 5 \\)"
    text = format_for_discord(md)
    assert "\\[" not in text
    assert "\\]" not in text
    assert "\\(" not in text
    assert "\\)" not in text
    assert "∑" in text
    assert "λ = 5" in text


def test_format_subscripts_and_superscripts():
    md = "Phân tử $H_2O$, $CO_2$ và biến $x_{10}$, $x_i$, lũy thừa $2^3$."
    text = format_for_discord(md)
    assert "H₂O" in text
    assert "CO₂" in text
    assert "x₁₀" in text
    assert "xᵢ" in text
    assert "2³" in text


def test_format_preserves_markdown():
    md = """# Tiêu đề 1
## Tiêu đề 2
### Tiêu đề 3

Đây là **in đậm**, *in nghiêng*, ~~gạch ngang~~.

> Trích dẫn quan trọng

- Mục danh sách 1
- Mục danh sách 2

[Trang chủ DeepTutor](https://deeptutor.ai)"""
    text = format_for_discord(md)
    assert "# Tiêu đề 1" in text
    assert "## Tiêu đề 2" in text
    assert "### Tiêu đề 3" in text
    assert "**in đậm**" in text
    assert "*in nghiêng*" in text
    assert "~~gạch ngang~~" in text
    assert "> Trích dẫn quan trọng" in text
    assert "- Mục danh sách 1" in text
    assert "[Trang chủ DeepTutor](https://deeptutor.ai)" in text


def test_format_html_tags():
    md = "Xin chào <b>bạn</b> và <i>đồng nghiệp</i> <span class='highlight'>lưu ý</span>.<br>Dòng tiếp theo <code>len(x)</code>."
    text = format_for_discord(md)
    assert "<b>" not in text
    assert "</b>" not in text
    assert "<i>" not in text
    assert "</i>" not in text
    assert "<span" not in text
    assert "<br>" not in text
    assert "**bạn**" in text
    assert "*đồng nghiệp*" in text
    assert "`len(x)`" in text
    assert "\nDòng tiếp theo" in text


def test_code_blocks_preserve_latex_verbatim():
    md = "```python\nval = '\\text{do not touch}'\n```\nNgoài mã: $\\ge 50\\%$"
    text = format_for_discord(md)
    assert "val = '\\text{do not touch}'" in text
    assert "\\text" in text  # preserved inside code block
    assert "≥ 50%" in text  # cleaned outside code block


def test_inline_code_preserves_latex():
    md = "Dùng lệnh `\\ge 50\\%` trong mã nguồn. Ngoài mã: $\\le 10$."
    text = format_for_discord(md)
    assert "`\\ge 50\\%`" in text
    assert "≤ 10" in text


def test_format_markdown_tables():
    md = """| Sản phẩm | Giá trị |
| --- | --- |
| Sữa chua | 15k |
| Bánh mì | 20k |"""
    text = format_for_discord(md)
    assert "|" not in text
    assert "Sản phẩm" in text
    assert "Sữa chua" in text
    assert "15k" in text


def test_format_and_split_for_discord():
    md = "# Tiêu đề\n" + ("Nội dung một dòng dài. " * 120)
    chunks = format_and_split_for_discord(md, max_len=500)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 500


@pytest.mark.asyncio
async def test_discord_channel_send_formats_content():
    bus = MagicMock()
    config = DiscordConfig(enabled=True, token="fake-token")
    channel = DiscordChannel(config, bus)
    channel._http = MagicMock()

    msg = OutboundMessage(
        channel="discord",
        chat_id="123456789",
        content="Mức calo: $\\sim 1200\\text{ kcal}$ với $\\ge 50\\%$",
    )

    with patch.object(channel, "_send_payload", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        await channel.send(msg)

        assert mock_send.called
        payload = mock_send.call_args[0][2]
        sent_content = payload.get("content", "")
        assert "\\sim" not in sent_content
        assert "\\text" not in sent_content
        assert "\\ge" not in sent_content
        assert "~ 1200 kcal" in sent_content
        assert "≥ 50%" in sent_content


@pytest.mark.asyncio
async def test_discord_channel_send_delta_formats_content_at_end():
    bus = MagicMock()
    config = DiscordConfig(enabled=True, token="fake-token")
    channel = DiscordChannel(config, bus)
    channel._http = MagicMock()

    chat_id = "123456789"
    # Setup active buffer
    channel._stream_bufs[chat_id] = MagicMock(
        message_id="msg_999",
        text="Công thức: $x = \\frac{1}{2}$",
        stream_id="stream_1",
    )

    with patch.object(channel, "_api_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"id": "msg_999"}
        await channel.send_delta(
            chat_id=chat_id,
            delta="",
            metadata={"_stream_id": "stream_1", "_stream_end": True},
        )

        assert mock_req.called
        # Check call arguments
        method, url, payload = mock_req.call_args[0]
        assert method == "PATCH"
        sent_content = payload.get("content", "")
        assert "\\frac" not in sent_content
        assert "x = (1)/(2)" in sent_content or "x = 1/2" in sent_content
