"""Markdown to Zalo text and style formatter."""

from __future__ import annotations

import re
from typing import Any

from deeptutor.partners.helpers import convert_markdown_table_to_labeled_rows

_INLINE_RE = re.compile(
    r"(?P<bold_italic>(?:\*\*\*|___)(?P<bi_txt1>.+?)(?:\*\*\*|___)|(?:\*\*_|__\*)(?P<bi_txt2>.+?)(?:_\*\*|\*__))"
    r"|(?P<bold>(?:\*\*|__)(?P<b_txt1>.+?)(?:\*\*|__))"
    r"|(?P<italic>\*(?P<i_txt1>[^\*\n]+?)\*|(?<!\w)_(?!\s)(?P<i_txt2>[^_\n]+?)(?<!\s)_(?!\w))"
    r"|(?P<strike>~~(?P<s_txt>.+?)~~)"
    r"|(?P<code>`(?P<c_txt>[^`\n]+)`)"
)


def utf16_len(text: str) -> int:
    """Calculate the length of a string in UTF-16 code units (as expected by Zalo)."""
    return len(text.encode("utf-16-le")) // 2


def _parse_lines(content: str) -> list[dict[str, Any]]:
    """Parse Markdown content into structured lines with table and code expansions."""
    text = content.replace("\r\n", "\n").replace("\r", "\n")

    # Clean images: ![alt](url) -> [Hình ảnh: alt] (url) or [Hình ảnh] (url)
    text = re.sub(
        r"!\[([^\]]*)\]\((https?://[^\s)]+)\)",
        lambda m: f"[Hình ảnh: {m.group(1)}] ({m.group(2)})"
        if m.group(1)
        else f"[Hình ảnh] ({m.group(2)})",
        text,
    )

    # Convert hyperlinks: [label](url) -> label (url) or url if label == url
    def _sub_link(m: re.Match) -> str:
        label = m.group(1).strip()
        url = m.group(2).strip()
        return url if label == url else f"{label} ({url})"

    text = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", _sub_link, text)

    # Clean math delimiters: $$...$$ and $...$
    text = re.sub(r"\$\$([^\$]+)\$\$", r"\1", text)
    text = re.sub(r"\$([^\$\n]+)\$", r"\1", text)

    raw_lines = text.split("\n")
    processed_lines: list[dict[str, Any]] = []

    in_code = False
    table_buffer: list[str] = []

    def flush_table() -> None:
        nonlocal table_buffer
        if not table_buffer:
            return
        tbl_text = "\n".join(table_buffer)
        table_buffer = []
        converted = convert_markdown_table_to_labeled_rows(tbl_text)
        for row in converted.split("\n"):
            if row.strip():
                clean_row = re.sub(r"(?i)[ \t]*<br\s*/?>[ \t]*", "\n  ", row.strip())
                for subline in clean_row.split("\n"):
                    if subline.strip():
                        if not subline.startswith("  ") and not subline.startswith("•"):
                            processed_lines.append(
                                {"text": f"• {subline.strip()}", "line_styles": [], "verbatim": False}
                            )
                        else:
                            processed_lines.append(
                                {"text": subline, "line_styles": [], "verbatim": False}
                            )

    for line in raw_lines:
        stripped = line.strip()

        # Fenced code block delimiter
        if stripped.startswith("```"):
            flush_table()
            if not in_code:
                in_code = True
                lang = stripped[3:].strip()
                header = f"[Mã nguồn: {lang}]" if lang else "[Mã nguồn]"
                processed_lines.append(
                    {"text": header, "line_styles": ["b"], "verbatim": True}
                )
            else:
                in_code = False
            continue

        if in_code:
            processed_lines.append(
                {"text": f"  {line}", "line_styles": [], "verbatim": True}
            )
            continue

        # Markdown table row
        if stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 2:
            table_buffer.append(line)
            continue
        else:
            flush_table()

        # Convert <br> tags in non-code, non-table lines into multiple lines
        sublines = (
            re.split(r"(?i)[ \t]*<br\s*/?>[ \t]*", line)
            if re.search(r"(?i)<br\s*/?>", line)
            else [line]
        )

        for subline in sublines:
            # Horizontal rule (---, ***, ___)
            if re.match(r"^\s*[-*_]{3,}\s*$", subline):
                processed_lines.append(
                    {"text": "───────────────────", "line_styles": [], "verbatim": True}
                )
                continue

            # Headings
            h1_m = re.match(r"^#\s+(.*)$", subline)
            if h1_m:
                processed_lines.append(
                    {
                        "text": f"📌 {h1_m.group(1).strip()}",
                        "line_styles": ["b", "f_18"],
                        "verbatim": False,
                    }
                )
                continue

            h2_m = re.match(r"^##\s+(.*)$", subline)
            if h2_m:
                processed_lines.append(
                    {
                        "text": f"📌 {h2_m.group(1).strip()}",
                        "line_styles": ["b"],
                        "verbatim": False,
                    }
                )
                continue

            h3_m = re.match(r"^###+\s+(.*)$", subline)
            if h3_m:
                processed_lines.append(
                    {
                        "text": f"🔹 {h3_m.group(1).strip()}",
                        "line_styles": ["b"],
                        "verbatim": False,
                    }
                )
                continue

            # Blockquote (> quote)
            bq_m = re.match(r"^>\s*(.*)$", subline)
            if bq_m:
                processed_lines.append(
                    {"text": f"▎ {bq_m.group(1)}", "line_styles": ["i"], "verbatim": False}
                )
                continue

            # Bullet lists (-, *, +)
            li_m = re.match(r"^(\s*)[*+-]\s+(.*)$", subline)
            if li_m:
                indent = li_m.group(1)
                item = li_m.group(2)
                processed_lines.append(
                    {"text": f"{indent}• {item}", "line_styles": [], "verbatim": False}
                )
                continue

            # Standard line
            processed_lines.append({"text": subline, "line_styles": [], "verbatim": False})

    flush_table()
    return processed_lines


def _split_long_lines(
    processed_lines: list[dict[str, Any]], max_len: int
) -> list[dict[str, Any]]:
    """Split any single line exceeding max_len into smaller chunks."""
    result: list[dict[str, Any]] = []
    for pline in processed_lines:
        text = pline["text"]
        if len(text) <= max_len:
            result.append(pline)
            continue

        start = 0
        while start < len(text):
            if len(text) - start <= max_len:
                sub = text[start:]
                start = len(text)
            else:
                cut = text.rfind(" ", start, start + max_len)
                if cut == -1 or cut <= start:
                    cut = start + max_len
                sub = text[start:cut]
                start = cut + 1 if cut < len(text) and text[cut] == " " else cut

            result.append(
                {
                    "text": sub,
                    "line_styles": pline.get("line_styles", []),
                    "verbatim": pline.get("verbatim", False),
                }
            )
    return result


def _render_lines_group(
    lines_group: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Render a sequence of structured lines into Zalo-compatible text and style spans."""
    out_parts: list[str] = []
    styles: list[dict[str, Any]] = []

    for i, pline in enumerate(lines_group):
        if i > 0:
            out_parts.append("\n")

        line_start = utf16_len("".join(out_parts))

        if pline["verbatim"]:
            out_parts.append(pline["text"])
        else:
            line_text = pline["text"]
            last_idx = 0
            for m in _INLINE_RE.finditer(line_text):
                m_start, m_end = m.span()
                out_parts.append(line_text[last_idx:m_start])
                curr_offset = utf16_len("".join(out_parts))

                if m.group("bold_italic"):
                    txt = m.group("bi_txt1") or m.group("bi_txt2")
                    out_parts.append(txt)
                    t_len = utf16_len(txt)
                    styles.append({"start": curr_offset, "len": t_len, "st": "b"})
                    styles.append({"start": curr_offset, "len": t_len, "st": "i"})
                elif m.group("bold"):
                    txt = m.group("b_txt1") or m.group("b_txt2")
                    out_parts.append(txt)
                    t_len = utf16_len(txt)
                    styles.append({"start": curr_offset, "len": t_len, "st": "b"})
                elif m.group("italic"):
                    txt = m.group("i_txt1") or m.group("i_txt2")
                    out_parts.append(txt)
                    t_len = utf16_len(txt)
                    styles.append({"start": curr_offset, "len": t_len, "st": "i"})
                elif m.group("strike"):
                    txt = m.group("s_txt")
                    out_parts.append(txt)
                    t_len = utf16_len(txt)
                    styles.append({"start": curr_offset, "len": t_len, "st": "s"})
                elif m.group("code"):
                    txt = m.group("c_txt")
                    out_parts.append(txt)
                last_idx = m_end

            out_parts.append(line_text[last_idx:])

        line_len = utf16_len("".join(out_parts)) - line_start
        for st in pline["line_styles"]:
            if line_len > 0:
                styles.append({"start": line_start, "len": line_len, "st": st})

    final_str = "".join(out_parts)
    return final_str, styles


def format_for_zalo(content: str) -> tuple[str, list[dict[str, Any]]]:
    """Format Markdown content for clean display on Zalo with native text styling.

    Returns:
        tuple[str, list[dict[str, Any]]]: A tuple containing:
            - The cleaned, readable text stripped of ugly raw Markdown tokens.
            - An array of Zalo style objects: `{"start": int, "len": int, "st": str}`.
    """
    if not content:
        return "", []

    lines = _parse_lines(content)
    return _render_lines_group(lines)


def format_and_split_for_zalo(
    content: str, max_len: int = 1200
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Format Markdown content and split into chunks of at most `max_len` characters.

    Each chunk contains clean text and corresponding relative style offsets,
    guaranteeing that neither text length nor style payload overflows Zalo Web limits.

    Returns:
        list[tuple[str, list[dict[str, Any]]]]: Chunks of (text, styles).
    """
    if not content:
        return [("", [])]

    raw_lines = _parse_lines(content)
    processed_lines = _split_long_lines(raw_lines, max_len=max_len)

    chunks: list[tuple[str, list[dict[str, Any]]]] = []
    curr_group: list[dict[str, Any]] = []
    curr_len = 0

    for pline in processed_lines:
        line_len = len(pline["text"]) + 1
        if curr_group and (curr_len + line_len > max_len):
            txt, st = _render_lines_group(curr_group)
            if txt.strip():
                chunks.append((txt, st))
            curr_group = [pline]
            curr_len = line_len
        else:
            curr_group.append(pline)
            curr_len += line_len

    if curr_group:
        txt, st = _render_lines_group(curr_group)
        if txt.strip() or not chunks:
            chunks.append((txt, st))

    return chunks or [("", [])]
