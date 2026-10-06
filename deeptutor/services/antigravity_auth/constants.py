"""Constants for Google Antigravity OAuth."""

from __future__ import annotations

ANTIGRAVITY_CALLBACK_PORT = 51121
ANTIGRAVITY_CALLBACK_PATH = "/oauth-callback"
ANTIGRAVITY_REDIRECT_URI = f"http://localhost:{ANTIGRAVITY_CALLBACK_PORT}{ANTIGRAVITY_CALLBACK_PATH}"

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
