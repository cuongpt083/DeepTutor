"""Constants for Google Antigravity OAuth."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

ANTIGRAVITY_CALLBACK_PORT = 51121
ANTIGRAVITY_CALLBACK_PATH = "/oauth-callback"
ANTIGRAVITY_REDIRECT_URI = f"http://localhost:{ANTIGRAVITY_CALLBACK_PORT}{ANTIGRAVITY_CALLBACK_PATH}"
REDIRECT_URI_ENV_VAR = "ANTIGRAVITY_REDIRECT_URI"
#: Public path the HTTPS reverse proxy already forwards (via /api/*).
ANTIGRAVITY_PUBLIC_CALLBACK_PATH = "/api/settings/providers/google-antigravity/oauth/callback"

DEFAULT_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
DEFAULT_TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
DEFAULT_USERINFO_URL = "https://www.googleapis.com/oauth2/v1/userinfo?alt=json"

DEFAULT_ENDPOINT = "https://daily-cloudcode-pa.googleapis.com"
DEFAULT_PROJECT_ID = "rising-fact-p41fc"

DEFAULT_SCOPES: tuple[str, ...] = (
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/aicode",
    "https://www.googleapis.com/auth/cclog",
    "https://www.googleapis.com/auth/experimentsandconfigs",
)

ANTIGRAVITY_LOGIN_TIMEOUT_SECONDS = 300.0

DEFAULT_USER_AGENT_VERSION = "1.21.9"

MANAGED_BY = "google_antigravity_oauth"
ANTIGRAVITY_PROFILE_ID = "llm-profile-google-antigravity-managed"


def resolve_antigravity_redirect_uri() -> str:
    """Loopback by default; override for a custom Google Cloud OAuth client."""

    raw = (os.environ.get(REDIRECT_URI_ENV_VAR) or "").strip()
    return raw or ANTIGRAVITY_REDIRECT_URI


def is_loopback_redirect_uri(uri: str) -> bool:
    host = (urlsplit(uri).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}
