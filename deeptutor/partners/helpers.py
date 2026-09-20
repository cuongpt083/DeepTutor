"""Utility functions shared by the partner channel layer."""

from datetime import datetime
from pathlib import Path
import re


def detect_image_mime(data: bytes) -> str | None:
    """Detect image MIME type from magic bytes, ignoring file extension."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def ensure_dir(path: Path) -> Path:
    """Ensure directory exists, return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def timestamp() -> str:
    """Current ISO timestamp."""
    return datetime.now().isoformat()


_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*]')
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def safe_filename(name: str) -> str:
    """Replace unsafe path / control characters; ``.`` / ``..`` become empty."""
    cleaned = _CONTROL_CHARS.sub("", _UNSAFE_CHARS.sub("_", name or "")).strip().strip(".")
    return cleaned


def split_message(content: str, max_len: int = 2000) -> list[str]:
    """
    Split content into chunks within max_len, preferring line breaks.

    Args:
        content: The text content to split.
        max_len: Maximum length per chunk (default 2000 for Discord compatibility).

    Returns:
        List of message chunks, each within max_len.
    """
    if not content:
        return []
    # Non-positive max_len cannot advance the cut pointer; return unsplit.
    if max_len <= 0:
        return [content]
    if len(content) <= max_len:
        return [content]
    chunks: list[str] = []
    while content:
        if len(content) <= max_len:
            chunks.append(content)
            break
        cut = content[:max_len]
        # Try to break at newline first, then space, then hard break
        pos = cut.rfind("\n")
        if pos <= 0:
            pos = cut.rfind(" ")
        if pos <= 0:
            pos = max_len
        chunks.append(content[:pos])
        content = content[pos:].lstrip()
    return chunks


def split_markdown_table_row(line: str) -> list[str]:
    """Split one Markdown pipe-table row into stripped cells.

    Strips exactly one leading and one trailing pipe so leading/trailing empty
    cells (``|| a |`` / ``| a ||``) survive — ``str.strip("|")`` would collapse
    them and shift every column.
    """
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip() for cell in line.split("|")]


def is_markdown_table_separator_row(cells: list[str]) -> bool:
    """True if *cells* look like a markdown table separator row.

    An all-empty row is not a separator (`all([])` would otherwise be True).
    """
    return bool(any(c for c in cells)) and all(re.match(r"^:?-+:?$", c) for c in cells if c)


def convert_markdown_table_to_labeled_rows(table_text: str) -> str:
    """Convert a Markdown pipe table to labeled rows (for Slack-style text).

    Empty cells are kept so blank columns are not dropped.
    """
    lines = [ln.strip() for ln in table_text.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return table_text
    headers = split_markdown_table_row(lines[0])
    start = 2 if is_markdown_table_separator_row(split_markdown_table_row(lines[1])) else 1
    rows: list[str] = []
    for line in lines[start:]:
        cells = split_markdown_table_row(line)
        cells = (cells + [""] * len(headers))[: len(headers)]
        parts = [f"**{headers[i]}**: {cells[i]}" for i in range(len(headers))]
        if parts:
            rows.append(" · ".join(parts))
    return "\n".join(rows)


_SUP_MAP = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
    "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    "+": "⁺", "-": "⁻", "=": "⁼", "(": "⁽", ")": "⁾",
    "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ",
    "f": "ᶠ", "g": "ᵍ", "h": "ʰ", "i": "ⁱ", "j": "ʲ",
    "k": "ᵏ", "l": "ˡ", "m": "ᵐ", "n": "ⁿ", "o": "ᵒ",
    "p": "ᵖ", "r": "ʳ", "s": "ˢ", "t": "ᵗ", "u": "ᵘ",
    "v": "ᵛ", "w": "ʷ", "x": "ˣ", "y": "ʸ", "z": "ᶻ",
}

_SUB_MAP = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄",
    "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
    "+": "₊", "-": "₋", "=": "₌", "(": "₍", ")": "₎",
    "a": "ₐ", "e": "ₑ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ",
    "k": "ₖ", "l": "ₗ", "m": "ₘ", "n": "ₙ", "o": "ₒ",
    "p": "ₚ", "r": "ᵣ", "s": "ₛ", "t": "ₜ", "u": "ᵤ",
    "v": "ᵥ", "x": "ₓ",
}

_LATEX_SYMBOLS: list[tuple[str, str]] = [
    # Degree & temperature
    (r"\\degree([CF])\b", r"°\1"),
    (r"\^\{?\\circ\}?|\\degree(?![a-zA-Z])", "°"),
    # Relations & Operators
    (r"\\ge(?:q)?(?![a-zA-Z])", "≥"),
    (r"\\le(?:q)?(?![a-zA-Z])", "≤"),
    (r"\\sim(?![a-zA-Z])", "~"),
    (r"\\approx(?![a-zA-Z])", "≈"),
    (r"\\pm(?![a-zA-Z])", "±"),
    (r"\\mp(?![a-zA-Z])", "∓"),
    (r"\\times(?![a-zA-Z])", "×"),
    (r"\\div(?![a-zA-Z])", "÷"),
    (r"\\ne(?:q)?(?![a-zA-Z])", "≠"),
    (r"\\equiv(?![a-zA-Z])", "≡"),
    (r"\\cdot(?![a-zA-Z])", "·"),
    (r"\\bullet(?![a-zA-Z])", "•"),
    (r"\\(?:dots|ldots|cdots|vdots|ddots)(?![a-zA-Z])", "..."),
    # Arrows
    (r"\\(?:to|rightarrow)(?![a-zA-Z])", "→"),
    (r"\\leftarrow(?![a-zA-Z])", "←"),
    (r"\\Rightarrow(?![a-zA-Z])", "⇒"),
    (r"\\Leftarrow(?![a-zA-Z])", "⇐"),
    (r"\\leftrightarrow(?![a-zA-Z])", "↔"),
    (r"\\iff(?![a-zA-Z])", "⇔"),
    (r"\\implies(?![a-zA-Z])", "⇒"),
    # Math sets & logic
    (r"\\infty(?![a-zA-Z])", "∞"),
    (r"\\sum(?![a-zA-Z])", "∑"),
    (r"\\prod(?![a-zA-Z])", "∏"),
    (r"\\int(?![a-zA-Z])", "∫"),
    (r"\\iint(?![a-zA-Z])", "∬"),
    (r"\\partial(?![a-zA-Z])", "∂"),
    (r"\\nabla(?![a-zA-Z])", "∇"),
    (r"\\in(?![a-zA-Z])", "∈"),
    (r"\\notin(?![a-zA-Z])", "∉"),
    (r"\\subset(?![a-zA-Z])", "⊂"),
    (r"\\subseteq(?![a-zA-Z])", "⊆"),
    (r"\\cup(?![a-zA-Z])", "∪"),
    (r"\\cap(?![a-zA-Z])", "∩"),
    (r"\\emptyset(?![a-zA-Z])", "∅"),
    (r"\\forall(?![a-zA-Z])", "∀"),
    (r"\\exists(?![a-zA-Z])", "∃"),
    # Greek letters (lowercase)
    (r"\\alpha(?![a-zA-Z])", "α"),
    (r"\\beta(?![a-zA-Z])", "β"),
    (r"\\gamma(?![a-zA-Z])", "γ"),
    (r"\\delta(?![a-zA-Z])", "δ"),
    (r"\\(?:epsilon|varepsilon)(?![a-zA-Z])", "ε"),
    (r"\\zeta(?![a-zA-Z])", "ζ"),
    (r"\\eta(?![a-zA-Z])", "η"),
    (r"\\(?:theta|vartheta)(?![a-zA-Z])", "θ"),
    (r"\\iota(?![a-zA-Z])", "ι"),
    (r"\\kappa(?![a-zA-Z])", "κ"),
    (r"\\lambda(?![a-zA-Z])", "λ"),
    (r"\\mu(?![a-zA-Z])", "μ"),
    (r"\\nu(?![a-zA-Z])", "ν"),
    (r"\\xi(?![a-zA-Z])", "ξ"),
    (r"\\pi(?![a-zA-Z])", "π"),
    (r"\\rho(?![a-zA-Z])", "ρ"),
    (r"\\sigma(?![a-zA-Z])", "σ"),
    (r"\\tau(?![a-zA-Z])", "τ"),
    (r"\\upsilon(?![a-zA-Z])", "υ"),
    (r"\\(?:phi|varphi)(?![a-zA-Z])", "φ"),
    (r"\\chi(?![a-zA-Z])", "χ"),
    (r"\\psi(?![a-zA-Z])", "ψ"),
    (r"\\omega(?![a-zA-Z])", "ω"),
    # Greek letters (uppercase)
    (r"\\Gamma(?![a-zA-Z])", "Γ"),
    (r"\\Delta(?![a-zA-Z])", "Δ"),
    (r"\\Theta(?![a-zA-Z])", "Θ"),
    (r"\\Lambda(?![a-zA-Z])", "Λ"),
    (r"\\Xi(?![a-zA-Z])", "Ξ"),
    (r"\\Pi(?![a-zA-Z])", "Π"),
    (r"\\Sigma(?![a-zA-Z])", "Σ"),
    (r"\\Phi(?![a-zA-Z])", "Φ"),
    (r"\\Psi(?![a-zA-Z])", "Ψ"),
    (r"\\Omega(?![a-zA-Z])", "Ω"),
]

def _extract_braced_group(text: str, start_idx: int) -> tuple[str, int] | None:
    """Extract content inside balanced { ... } starting at start_idx (which must be '{').

    Returns (content, end_idx) where end_idx is the index right after closing '}'.
    """
    if start_idx >= len(text) or text[start_idx] != "{":
        return None
    depth = 0
    content = []
    for i in range(start_idx, len(text)):
        char = text[i]
        if char == "{":
            depth += 1
            if depth > 1:
                content.append(char)
        elif char == "}":
            depth -= 1
            if depth == 0:
                return "".join(content), i + 1
            content.append(char)
        else:
            content.append(char)
    return None


def clean_latex_math(text: str) -> str:
    """Convert LaTeX math constructs and symbols to clean, readable Unicode text."""
    if not text:
        return ""

    # 0. Environments & linebreaks inside math
    text = re.sub(r"\\(?:begin|end)\{[a-zA-Z*]+\}", "", text)
    text = re.sub(r"\\\\", "\n", text)

    # Ensure space between number and unit wrapper: e.g. 100\text{kg} -> 100 kg
    text = re.sub(
        r"(\d)\s*\\(?:text|mathrm|mathbf|mathit|operatorname|textbf|textit|bm|boldsymbol)\{([a-zA-Z])",
        r"\1 \2",
        text,
    )

    # 1. Strip wrappers: \text{...}, \mathrm{...}, etc. with balanced braces
    wrapper_re = re.compile(
        r"\\(?:text|mathrm|mathbf|mathit|operatorname|textbf|textit|bm|boldsymbol|underline)\b"
    )
    while True:
        m = wrapper_re.search(text)
        if not m:
            break
        idx = m.start()
        after = m.end()
        while after < len(text) and text[after] in " \t":
            after += 1
        arg_res = _extract_braced_group(text, after)
        if not arg_res:
            break
        arg, end_idx = arg_res
        text = text[:idx] + arg + text[end_idx:]

    # 2. Fractions: \frac{a}{b} -> (a)/(b) with balanced braces
    while True:
        idx = text.find(r"\frac")
        if idx == -1:
            break
        after_frac = idx + len(r"\frac")
        while after_frac < len(text) and text[after_frac] in " \t":
            after_frac += 1
        num_res = _extract_braced_group(text, after_frac)
        if not num_res:
            break
        num, den_start = num_res
        while den_start < len(text) and text[den_start] in " \t":
            den_start += 1
        den_res = _extract_braced_group(text, den_start)
        if not den_res:
            break
        den, end_idx = den_res
        num_clean = clean_latex_math(num)
        den_clean = clean_latex_math(den)
        text = text[:idx] + f"({num_clean})/({den_clean})" + text[end_idx:]

    # 3. Square roots: \sqrt[n]{x} -> (n)√(x), \sqrt{x} -> √(x) with balanced braces
    while True:
        m = re.search(r"\\sqrt\[([^\]]+)\]", text)
        if not m:
            break
        deg = m.group(1)
        idx = m.start()
        after = m.end()
        while after < len(text) and text[after] in " \t":
            after += 1
        arg_res = _extract_braced_group(text, after)
        if not arg_res:
            break
        arg, end_idx = arg_res
        arg_clean = clean_latex_math(arg)
        text = text[:idx] + f"({deg})√({arg_clean})" + text[end_idx:]

    while True:
        idx = text.find(r"\sqrt")
        if idx == -1:
            break
        after = idx + len(r"\sqrt")
        while after < len(text) and text[after] in " \t":
            after += 1
        arg_res = _extract_braced_group(text, after)
        if not arg_res:
            break
        arg, end_idx = arg_res
        arg_clean = clean_latex_math(arg)
        text = text[:idx] + f"√({arg_clean})" + text[end_idx:]
    # 4. Symbol replacements
    for pattern, repl in _LATEX_SYMBOLS:
        text = re.sub(pattern, repl, text)

    # 5. Sizing & delimiters: \left, \right, \big, etc.
    text = re.sub(r"\\(?:left|right|big|Big|bigg|Bigg)\b", "", text)

    # 6. Spacing: \, \: \; \! \quad \qquad \enspace
    text = re.sub(r"\\[,;:!]", " ", text)
    text = re.sub(r"\\(?:quad|qquad|enspace)\b", " ", text)

    # 7. Superscripts and subscripts
    def _replace_sup(m: re.Match) -> str:
        chars = m.group(1)
        if all(c in _SUP_MAP for c in chars):
            return "".join(_SUP_MAP[c] for c in chars)
        return f"^({chars})"

    def _replace_sub(m: re.Match) -> str:
        chars = m.group(1)
        if all(c in _SUB_MAP for c in chars):
            return "".join(_SUB_MAP[c] for c in chars)
        return f"_({chars})"

    text = re.sub(r"\^\{([^{}]+)\}", _replace_sup, text)
    text = re.sub(
        r"\^([0-9a-zA-Z+-=()])",
        lambda m: _SUP_MAP.get(m.group(1), f"^{m.group(1)}"),
        text,
    )
    text = re.sub(r"_\{([^{}]+)\}", _replace_sub, text)
    text = re.sub(
        r"_([0-9a-zA-Z+-=()])",
        lambda m: _SUB_MAP.get(m.group(1), f"_{m.group(1)}"),
        text,
    )

    # 8. Escaped characters: \%, \$, \&, \#, \_, \{, \}
    text = re.sub(r"\\([%&#${}_])", r"\1", text)

    # 9. Clean any remaining lone curly braces
    while re.search(r"\{([^{}]*)\}", text):
        text = re.sub(r"\{([^{}]*)\}", r"\1", text)

    # 10. Clean lone backslashes before words
    text = re.sub(r"\\([a-zA-Z]+)", r"\1", text)

    # 11. Normalize horizontal spaces
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def clean_html_tags(text: str) -> str:
    """Convert inline HTML formatting tags to Markdown syntax or strip unneeded tags."""
    # Convert formatting tags to Markdown
    text = re.sub(r"(?i)<(?:b|strong)>(.*?)</(?:b|strong)>", r"**\1**", text)
    text = re.sub(r"(?i)<(?:i|em)>(.*?)</(?:i|em)>", r"*\1*", text)
    text = re.sub(r"(?i)<(?:del|s|strike)>(.*?)</(?:del|s|strike)>", r"~~\1~~", text)
    text = re.sub(r"(?i)<code>(.*?)</code>", r"`\1`", text)
    text = re.sub(r"(?i)<(?:u|ins)>(.*?)</(?:u|ins)>", r"\1", text)

    # Strip span, div, p, center, font, etc.
    text = re.sub(
        r"(?i)</?(?:span|div|p|center|font|small|big|header|footer|section|article)[^>]*>",
        "",
        text,
    )

    # Strip any remaining stray tags except <br>
    text = re.sub(r"(?i)<(?!/?br\s*/?>)[^>]+>", "", text)
    return text
