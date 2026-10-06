"""Data contracts and errors for Google Antigravity OAuth."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any


class AntigravityAuthError(Exception):
    """An actionable Antigravity OAuth failure."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class AntigravityReauthRequiredError(AntigravityAuthError):
    """Explicit sign-in is required."""

    def __init__(self, message: str = "Sign-in required for Google Antigravity.") -> None:
        super().__init__("reauth_required", message, 401)


@dataclass(frozen=True)
class AntigravityToken:
    """OAuth token payload from Google."""

    access_token: str
    token_type: str
    refresh_token: str
    expires_in: int
    expires_at: float
    scopes: tuple[str, ...]
    id_token: str = ""
    email: str = ""
    project_id: str = ""

    def is_expired(self, lead_s: float = 300.0) -> bool:
        return time.time() >= (self.expires_at - lead_s)


@dataclass(frozen=True)
class AntigravityCredentials:
    """Stored credentials for one owner."""

    token: AntigravityToken
    client_id: str
    client_secret: str
    project_id: str
    updated_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.token.access_token,
            "token_type": self.token.token_type,
            "refresh_token": self.token.refresh_token,
            "expires_in": self.token.expires_in,
            "expires_at": self.token.expires_at,
            "scopes": list(self.token.scopes),
            "id_token": self.token.id_token,
            "email": self.token.email,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "project_id": self.project_id,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AntigravityCredentials:
        token = AntigravityToken(
            access_token=str(data.get("access_token") or ""),
            token_type=str(data.get("token_type") or "Bearer"),
            refresh_token=str(data.get("refresh_token") or ""),
            expires_in=int(data.get("expires_in") or 3600),
            expires_at=float(data.get("expires_at") or 0.0),
            scopes=tuple(data.get("scopes") or ()),
            id_token=str(data.get("id_token") or ""),
            email=str(data.get("email") or ""),
            project_id=str(data.get("project_id") or ""),
        )
        return cls(
            token=token,
            client_id=str(data.get("client_id") or ""),
            client_secret=str(data.get("client_secret") or ""),
            project_id=str(data.get("project_id") or ""),
            updated_at=float(data.get("updated_at") or 0.0),
        )


@dataclass(frozen=True)
class AntigravityModel:
    id: str
    label: str
    description: str
    context_window: int = 200_000
    supports_reasoning: bool = True
