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


def format_for_zalo(content: str) -> tuple[str, list[dict[str, Any]]]:
    """Format Markdown content for clean display on Zalo with native text styling.

    Returns:
        tuple[str, list[dict[str, Any]]]: A tuple containing:
            - The cleaned, readable text stripped of ugly raw Markdown tokens.
            - An array of Zalo style objects: `{"start": int, "len": int, "st": str}`.
    """
    if not content:
        return "", []

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
                processed_lines.append(
                    {"text": f"• {row.strip()}", "line_styles": [], "verbatim": False}
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

        # Horizontal rule (---, ***, ___)
        if re.match(r"^\s*[-*_]{3,}\s*$", line):
            processed_lines.append(
                {"text": "───────────────────", "line_styles": [], "verbatim": True}
            )
            continue

        # Headings
        h1_m = re.match(r"^#\s+(.*)$", line)
        if h1_m:
            processed_lines.append(
                {
                    "text": f"📌 {h1_m.group(1).strip()}",
                    "line_styles": ["b", "f_18"],
                    "verbatim": False,
                }
            )
            continue

        h2_m = re.match(r"^##\s+(.*)$", line)
        if h2_m:
            processed_lines.append(
                {
                    "text": f"📌 {h2_m.group(1).strip()}",
                    "line_styles": ["b"],
                    "verbatim": False,
                }
            )
            continue

        h3_m = re.match(r"^###+\s+(.*)$", line)
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
        bq_m = re.match(r"^>\s*(.*)$", line)
        if bq_m:
            processed_lines.append(
                {"text": f"▎ {bq_m.group(1)}", "line_styles": ["i"], "verbatim": False}
            )
            continue

        # Bullet lists (-, *, +)
        li_m = re.match(r"^(\s*)[*+-]\s+(.*)$", line)
        if li_m:
            indent = li_m.group(1)
            item = li_m.group(2)
            processed_lines.append(
                {"text": f"{indent}• {item}", "line_styles": [], "verbatim": False}
            )
            continue

        # Standard line
        processed_lines.append({"text": line, "line_styles": [], "verbatim": False})

    flush_table()

    # Construct final text and calculate style offsets
    out_parts: list[str] = []
    styles: list[dict[str, Any]] = []

    for i, pline in enumerate(processed_lines):
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
