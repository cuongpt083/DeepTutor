"""Unit tests for antigravity_auth package."""

from __future__ import annotations

import pytest
import time
from pathlib import Path

from deeptutor.services.antigravity_auth.contracts import (
    AntigravityCredentials,
    AntigravityToken,
)
from deeptutor.services.antigravity_auth.storage import AntigravityCredentialStore
from deeptutor.services.antigravity_auth.oauth import (
    generate_pkce,
    oauth_state_matches,
    build_authorize_url,
)
from deeptutor.services.antigravity_auth import service as auth_service_module
from deeptutor.services.antigravity_auth.constants import (
    ANTIGRAVITY_REDIRECT_URI,
    is_loopback_redirect_uri,
    resolve_antigravity_redirect_uri,
)
from deeptutor.services.antigravity_auth.service import AntigravityAuthService


def test_pkce_generation() -> None:
    pkce = generate_pkce()
    assert pkce.verifier
    assert pkce.challenge
    assert len(pkce.verifier) >= 43


def test_oauth_state_matches() -> None:
    state = "secure-random-state-12345"
    assert oauth_state_matches(state, state)
    assert not oauth_state_matches("wrong-state", state)
    assert not oauth_state_matches(None, state)


def test_build_authorize_url() -> None:
    pkce = generate_pkce()
    url = build_authorize_url(
        client_id="test-client-id",
        state="test-state",
        pkce=pkce,
    )
    assert "https://accounts.google.com" in url
    assert "test-client-id" in url
    assert "code_challenge=" in url
    assert "prompt=consent" in url


def test_credential_store(tmp_path: Path) -> None:
    store = AntigravityCredentialStore(tmp_path)
    assert store.load_credentials() is None

    token = AntigravityToken(
        access_token="ya29.test",
        token_type="Bearer",
        refresh_token="1//refresh",
        expires_in=3600,
        expires_at=time.time() + 3600,
        scopes=("openid", "email"),
        email="user@example.com",
        project_id="test-proj",
    )
    creds = AntigravityCredentials(
        token=token,
        client_id="cid",
        client_secret="sec",
        project_id="test-proj",
        updated_at=time.time(),
    )
    store.store_credentials(creds)

    loaded = store.load_credentials()
    assert loaded is not None
    assert loaded.token.access_token == "ya29.test"
    assert loaded.token.email == "user@example.com"
    assert loaded.project_id == "test-proj"

    store.clear()
    assert store.load_credentials() is None


def test_resolve_redirect_uri_defaults_to_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTIGRAVITY_REDIRECT_URI", raising=False)
    assert resolve_antigravity_redirect_uri() == ANTIGRAVITY_REDIRECT_URI
    assert is_loopback_redirect_uri(ANTIGRAVITY_REDIRECT_URI)
    assert is_loopback_redirect_uri("http://127.0.0.1:51121/oauth-callback")
    assert not is_loopback_redirect_uri(
        "https://tutor.example.com/api/settings/providers/google-antigravity/oauth/callback"
    )


def test_resolve_redirect_uri_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "ANTIGRAVITY_REDIRECT_URI",
        "https://tutor.example.com/api/settings/providers/google-antigravity/oauth/callback",
    )
    assert resolve_antigravity_redirect_uri().startswith("https://tutor.example.com")


@pytest.mark.asyncio
async def test_start_login_skips_loopback_for_public_redirect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(
        "ANTIGRAVITY_REDIRECT_URI",
        "https://tutor.example.com/api/settings/providers/google-antigravity/oauth/callback",
    )

    async def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("loopback must not start for a public redirect")

    monkeypatch.setattr(
        "deeptutor.services.antigravity_auth.service.AntigravityLoopbackCallback.start",
        boom,
    )
    auth_service_module._CURRENT_LOGIN = None
    started = await AntigravityAuthService(tmp_path).start_login(
        client_id="id", client_secret="secret"
    )
    assert started["loopback"] is False
    assert "tutor.example.com" in started["redirect_uri"]
    assert "redirect_uri=" in started["authorize_url"]
    auth_service_module._CURRENT_LOGIN = None


def test_service_status(tmp_path: Path) -> None:
    service = AntigravityAuthService(tmp_path)
    status = service.get_status()
    assert not status["connected"]
    assert "models" in status
    assert len(status["models"]) > 0
