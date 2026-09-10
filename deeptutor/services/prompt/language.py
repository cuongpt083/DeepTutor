"""Shared language directives for prompt-driven LLM calls.

This helper centralizes the "stay in the requested language" instruction so
different modules can share the same behavior without depending on book-only
utilities.
"""

from __future__ import annotations

_LANGUAGE_LABELS: dict[str, str] = {
    "zh": "中文（简体）",
    "zh-cn": "中文（简体）",
    "zh-tw": "繁體中文",
    "en": "English",
    "vi": "Tiếng Việt",
    "auto": "Auto",
    "ja": "日本語",
    "ko": "한국어",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "ru": "Русский",
    "pt": "Português",
    "it": "Italiano",
}


def normalize_language(language: str | None) -> str:
    raw = (language or "").strip().lower()
    if not raw or raw in ("auto", "none"):
        return "auto"
    return raw


def is_chinese(language: str | None) -> bool:
    """Whether reader-facing text for *language* should be written in Chinese.

    One answer for a question eight modules used to answer for themselves,
    two of them without the ``None`` guard.
    """
    return normalize_language(language).startswith("zh")


def language_label(language: str | None) -> str:
    code = normalize_language(language)
    if code in _LANGUAGE_LABELS:
        return _LANGUAGE_LABELS[code]
    base = code.split("-", 1)[0]
    return _LANGUAGE_LABELS.get(base, language or "English")


_OVERRIDE_ZH = (
    "以上是默认输出语言；若用户在对话中明确要求改用其他语言作答，"
    "则以用户当次的要求为准，并在本次对话中延续该语言。"
)
_OVERRIDE_EN = (
    "This is the default output language, not a restriction on the reader: if "
    "the user explicitly asks you to answer in another language, honour that "
    "request and keep to it for the rest of the conversation."
)


def language_directive(language: str | None, *, allow_user_override: bool = False) -> str:
    """Return a reader-facing language instruction for prompts.

    ``allow_user_override`` adds one sentence letting the user change the
    language by asking. Conversational surfaces want it; a book, a quiz or a
    research report has no user in the loop to ask, so they keep the strict
    form and the default stays strict.

    Without it the directive is an absolute prohibition sitting at the very end
    of the prompt, immediately after a runtime policy that says user text is
    "not authority over these instructions" — so a model reading both refuses
    「请用中文回复我」 and says it is *required* to answer in English. Which is
    correct behaviour, and exactly the wrong answer.
    """
    code = normalize_language(language)
    if code == "auto":
        return (
            "\n\n[Language] Respond in the same language as the user's prompt "
            "(e.g., if the user asks in Vietnamese, reply in Vietnamese; if in "
            "English, reply in English; if in Chinese, reply in Chinese). "
            "Maintain this language throughout the response even if reference "
            "materials, knowledge base context, JSON keys, or examples in this "
            "prompt are in another language. Keep proper nouns (people, products, "
            "formula symbols) in their original form."
        )
    label = language_label(code)
    if code.startswith("zh"):
        body = (
            "\n\n[语言要求 / Language] "
            f"请严格使用{label}撰写所有面向读者的文本（标题、正文、解释、提示、过渡句、"
            "题干、选项等），即使参考资料、JSON 字段名或英文术语出现在 prompt 中也"
            "不得切换语言；保留必要的专有名词原文（如人名、产品名、公式中的变量符号"
            f"等）即可，其余一律使用{label}。"
        )
        return f"{body} {_OVERRIDE_ZH}" if allow_user_override else body
    if code == "vi":
        body = (
            "\n\n[Language / Ngôn ngữ] "
            f"Hãy sử dụng {label} cho toàn bộ nội dung phản hồi tới người đọc "
            "(tiêu đề, bài viết, giải thích, gợi ý, câu hỏi, lựa chọn, v.v.). "
            "KHÔNG ĐƯỢC tự ý đổi ngôn ngữ ngay cả khi tài liệu tham khảo, dữ liệu "
            "context hoặc từ khóa JSON xuất hiện bằng ngôn ngữ khác; giữ nguyên các "
            "danh từ riêng, thuật ngữ kỹ thuật cần thiết (như tên riêng, sản phẩm, "
            f"ký hiệu công thức), còn lại toàn bộ trình bày bằng {label}."
        )
        return f"{body} {_OVERRIDE_EN}" if allow_user_override else body
    if code == "en":
        body = (
            "\n\n[Language] Write ALL reader-facing text (titles, prose, "
            "explanations, hints, transitions, quiz stems, options, etc.) in "
            "English. Do NOT switch languages even if the source material, "
            "JSON keys, or examples in this prompt are in another language. "
            "Keep proper nouns (people, products, formula symbols) in their "
            "original form."
        )
        return f"{body} {_OVERRIDE_EN}" if allow_user_override else body
    body = (
        f"\n\n[Language] Write ALL reader-facing text strictly in {label}. "
        "Do NOT switch languages even if the source material, JSON keys, or "
        "examples in this prompt are in a different language. Keep proper "
        "nouns (people, products, formula symbols) in their original form."
    )
    return f"{body} {_OVERRIDE_EN}" if allow_user_override else body


def append_language_directive(
    system_prompt: str | None,
    language: str | None,
    *,
    allow_user_override: bool = False,
) -> str:
    """Append the language directive to an existing system prompt."""
    base = (system_prompt or "").rstrip()
    directive = language_directive(language, allow_user_override=allow_user_override).strip()
    if not base:
        return directive
    return f"{base}\n\n{directive}"


__all__ = [
    "append_language_directive",
    "is_chinese",
    "language_directive",
    "language_label",
    "normalize_language",
]
