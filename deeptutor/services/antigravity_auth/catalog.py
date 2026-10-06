"""Model catalog for Google Antigravity."""

from __future__ import annotations

from .contracts import AntigravityModel

ANTIGRAVITY_MODELS: tuple[AntigravityModel, ...] = (
    AntigravityModel(
        id="google-antigravity/gemini-3-pro-low",
        label="Gemini 3 Pro (Low Reasoning)",
        description="Google frontier coding model with fast reasoning effort.",
        context_window=200_000,
    ),
    AntigravityModel(
        id="google-antigravity/gemini-3-pro-high",
        label="Gemini 3 Pro (High Reasoning)",
        description="Google frontier coding model with deep reasoning effort.",
        context_window=200_000,
    ),
    AntigravityModel(
        id="google-antigravity/gemini-3-1-pro-low",
        label="Gemini 3.1 Pro (Low Reasoning)",
        description="Next-gen Gemini 3.1 Pro with fast reasoning effort.",
        context_window=200_000,
    ),
    AntigravityModel(
        id="google-antigravity/gemini-3-1-pro-high",
        label="Gemini 3.1 Pro (High Reasoning)",
        description="Next-gen Gemini 3.1 Pro with deep reasoning effort.",
        context_window=200_000,
    ),
    AntigravityModel(
        id="google-antigravity/gemini-3.7-flash-tiered",
        label="Gemini 3.7 Flash",
        description="Fast multimodal coding model with tiered thinking.",
        context_window=200_000,
    ),
    AntigravityModel(
        id="google-antigravity/gemini-3.8-flash-tiered",
        label="Gemini 3.8 Flash",
        description="Latest fast flash model with thinking capabilities.",
        context_window=200_000,
    ),
)
