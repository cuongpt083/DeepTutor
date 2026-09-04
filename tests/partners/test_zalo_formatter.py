"""Unit tests for Zalo markdown formatting and styles extraction."""

from deeptutor.partners.channels.zalo_formatter import format_for_zalo, utf16_len


def test_format_empty():
    text, styles = format_for_zalo("")
    assert text == ""
    assert styles == []


def test_format_headings():
    md = "# Heading 1\n## Heading 2\n### Heading 3"
    text, styles = format_for_zalo(md)

    assert "📌 Heading 1" in text
    assert "📌 Heading 2" in text
    assert "🔹 Heading 3" in text

    # Verify styles contain bold and big for h1, bold for h2/h3
    b_styles = [s for s in styles if s["st"] == "b"]
    assert len(b_styles) == 3
    big_styles = [s for s in styles if s["st"] == "f_18"]
    assert len(big_styles) == 1


def test_format_bold_italic_strike():
    md = "Đây là **đậm** và *nghiêng* cùng ~~gạch~~ và ***cả hai***."
    text, styles = format_for_zalo(md)

    assert "**" not in text
    assert "~~" not in text
    assert "Đây là đậm và nghiêng cùng gạch và cả hai." == text

    # Check bold style for "đậm"
    bold_spans = [s for s in styles if s["st"] == "b"]
    assert any(s["len"] == utf16_len("đậm") for s in bold_spans)

    # Check italic style for "nghiêng"
    italic_spans = [s for s in styles if s["st"] == "i"]
    assert any(s["len"] == utf16_len("nghiêng") for s in italic_spans)

    # Check strike style for "gạch"
    strike_spans = [s for s in styles if s["st"] == "s"]
    assert any(s["len"] == utf16_len("gạch") for s in strike_spans)


def test_format_lists_and_blockquotes():
    md = "- Item 1\n* Item 2\n+ Item 3\n\n> Trích dẫn quan trọng"
    text, styles = format_for_zalo(md)

    assert "• Item 1" in text
    assert "• Item 2" in text
    assert "• Item 3" in text
    assert "▎ Trích dẫn quan trọng" in text

    # Blockquote should have italic style
    i_styles = [s for s in styles if s["st"] == "i"]
    assert len(i_styles) >= 1


def test_format_tables():
    md = """| Sản phẩm | Giá trị |
| --- | --- |
| Protein | 25g |
| BCAA | 5g |"""
    text, styles = format_for_zalo(md)

    assert "• Sản phẩm: Protein · Giá trị: 25g" in text
    assert "• Sản phẩm: BCAA · Giá trị: 5g" in text
    assert "|" not in text


def test_format_code_block():
    md = "```python\ndef hello():\n    return 'world'\n```"
    text, styles = format_for_zalo(md)

    assert "[Mã nguồn: python]" in text
    assert "  def hello():" in text
    assert "  return 'world'" in text
    assert "```" not in text


def test_format_links_and_images():
    md = "Xem tại [NutriTech](https://nutritech.vn) hoặc [https://link.com](https://link.com) và ![Logo](https://img.png)"
    text, styles = format_for_zalo(md)

    assert "NutriTech (https://nutritech.vn)" in text
    assert "https://link.com" in text
    assert "[Hình ảnh: Logo] (https://img.png)" in text


def test_utf16_offsets_with_emojis():
    # Emojis take 2 UTF-16 code units
    md = "📌 Chào **bạn**"
    text, styles = format_for_zalo(md)

    assert text == "📌 Chào bạn"
    # '📌' (2) + ' ' (1) + 'Chào' (4) + ' ' (1) = 8 UTF-16 code units
    b_style = next(s for s in styles if s["st"] == "b")
    assert b_style["start"] == 8
    assert b_style["len"] == utf16_len("bạn")


def test_format_br_tags():
    # 1. Plain text with <br>, <br/>, <br /> and case insensitivity
    md = "Dòng 1<br>Dòng 2<br/>Dòng 3<br />Dòng 4<BR>Dòng 5"
    text, styles = format_for_zalo(md)
    assert text == "Dòng 1\nDòng 2\nDòng 3\nDòng 4\nDòng 5"

    # 2. Consecutive <br><br> creates empty line separation
    md_consecutive = "Đoạn 1<br><br>Đoạn 2"
    text_c, _ = format_for_zalo(md_consecutive)
    assert text_c == "Đoạn 1\n\nĐoạn 2"

    # 3. <br> inside lists
    md_list = "- Mục 1<br>- Mục 2"
    text_l, _ = format_for_zalo(md_list)
    assert "• Mục 1\n• Mục 2" in text_l

    # 4. <br> inside tables
    md_table = """| Cột A | Cột B |
| --- | --- |
| Giá trị 1 | Chi tiết A<br>Chi tiết B |"""
    text_t, _ = format_for_zalo(md_table)
    assert "• Cột A: Giá trị 1 · Cột B: Chi tiết A\n  Chi tiết B" in text_t
    assert "<br>" not in text_t

    # 5. <br> inside code block should remain verbatim
    md_code = "```html\n<div><br>Nội dung</div>\n```"
    text_code, _ = format_for_zalo(md_code)
    assert "<div><br>Nội dung</div>" in text_code

