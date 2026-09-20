"""Markdown and LaTeX math formatter for Discord channel."""

from __future__ import annotations

import re

from deeptutor.partners.helpers import (
    clean_html_tags,
    clean_latex_math,
    convert_markdown_table_to_labeled_rows,
    split_message,
)

DISCORD_MAX_MESSAGE_LEN = 2000


def format_for_discord(content: str) -> str:
    """Format Markdown content for clean, readable display on Discord.

    - Protects code blocks and inline code from mutation.
    - Cleans LaTeX math blocks ($$...$$, $...$, \\[...\\], \\(...\\)) into Unicode.
    - Cleans standalone LaTeX commands and symbols.
    - Converts HTML tags to Markdown syntax or strips unsupported tags.
    - Converts Markdown pipe tables to labeled bullet rows (Discord does not render tables).
    - Preserves native Discord markdown (headers, bold, italic, strikethrough, lists, blockquotes).
    """
    if not content or not content.strip():
        return ""

    text = content.replace("\r\n", "\n").replace("\r", "\n")

    # 1. Protect code blocks (fenced ```...```)
    code_blocks: list[str] = []

    def _save_code(m: re.Match) -> str:
        code_blocks.append(m.group(0))
        return f"\x00C{len(code_blocks) - 1}C\x00"

    text = re.sub(r"```[^\n]*\n[\s\S]*?```", _save_code, text)

    # Protect inline code (`...`)
    inline_codes: list[str] = []

    def _save_inline_code(m: re.Match) -> str:
        inline_codes.append(m.group(0))
        return f"\x00I{len(inline_codes) - 1}I\x00"

    text = re.sub(r"`[^`\n]+`", _save_inline_code, text)

    # 2. Convert / clean HTML tags
    text = clean_html_tags(text)

    # 3. Clean LaTeX math blocks
    # Protect escaped dollar signs
    text = re.sub(r"\\\$", "\x00DOLLAR\x00", text)

    # Environments: \begin{equation}...\end{equation}, \begin{align}...\end{align}, etc.
    text = re.sub(
        r"\\begin\{[a-zA-Z*]+\}([\s\S]*?)\\end\{[a-zA-Z*]+\}",
        lambda m: clean_latex_math(m.group(1)),
        text,
    )

    # Display math: $$...$$ and \[...\]
    text = re.sub(r"\$\$([\s\S]+?)\$\$", lambda m: clean_latex_math(m.group(1)), text)
    text = re.sub(r"\\\[([\s\S]+?)\\\]", lambda m: clean_latex_math(m.group(1)), text)

    # Inline math: $...$ and \(...\)
    text = re.sub(r"\$([^\$\n]+)\$", lambda m: clean_latex_math(m.group(1)), text)
    text = re.sub(r"\\\(([^\n]+?)\\\)", lambda m: clean_latex_math(m.group(1)), text)

    # Restore escaped dollar signs
    text = text.replace("\x00DOLLAR\x00", "$")

    # 4. Clean standalone LaTeX math commands/symbols outside delimiters
    text = clean_latex_math(text)

    # 5. Process line by line for tables and <br> conversions
    raw_lines = text.split("\n")
    processed_lines: list[str] = []
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
                        if not subline.startswith("  ") and not subline.startswith("•") and not subline.startswith("-"):
                            processed_lines.append(f"• {subline.strip()}")
                        else:
                            processed_lines.append(subline)

    for line in raw_lines:
        stripped = line.strip()

        # Check for markdown table row
        if stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 2:
            table_buffer.append(line)
            continue
        else:
            flush_table()

        # Convert <br> in regular text lines
        sublines = (
            re.split(r"(?i)[ \t]*<br\s*/?>[ \t]*", line)
            if re.search(r"(?i)<br\s*/?>", line)
            else [line]
        )
        for subline in sublines:
            processed_lines.append(subline)

    flush_table()
    text = "\n".join(processed_lines)

    # 6. Restore protected inline code and code blocks
    for i, code in enumerate(inline_codes):
        text = text.replace(f"\x00I{i}I\x00", code)
    for i, block in enumerate(code_blocks):
        text = text.replace(f"\x00C{i}C\x00", block)

    # Normalize excessive empty lines (more than 2 consecutive -> 2)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def format_and_split_for_discord(
    content: str, max_len: int = DISCORD_MAX_MESSAGE_LEN
) -> list[str]:
    """Format Markdown content for Discord and split into chunks within length limit."""
    formatted = format_for_discord(content)
    if not formatted:
        return []
    return split_message(formatted, max_len)
