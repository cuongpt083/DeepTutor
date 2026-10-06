"""Unit tests for antigravity_auth package."""

from __future__ import annotations

import pytest
import time
from pathlib import Path

from deeptutor.services.antigravity_auth.contracts import (
    AntigravityAuthError,
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


def _fake_token() -> AntigravityToken:
    return AntigravityToken(
        access_token="ya29.test",
        token_type="Bearer",
        refresh_token="1//refresh",
        expires_in=3600,
        expires_at=time.time() + 3600,
        scopes=("openid", "email"),
        email="user@example.com",
        project_id="test-proj",
    )


@pytest.mark.asyncio
async def test_complete_login_stores_on_start_login_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner = tmp_path / "owner"
    other = tmp_path / "other"
    monkeypatch.setenv(
        "ANTIGRAVITY_REDIRECT_URI",
        "https://tutor.example.com/api/settings/providers/google-antigravity/oauth/callback",
    )
    exchanged: list[str] = []

    async def fake_exchange(self: AntigravityAuthService, op: object, *, code: str):
        exchanged.append(code)
        return _fake_token(), "secret"

    monkeypatch.setattr(AntigravityAuthService, "_exchange_code", fake_exchange)
    auth_service_module._CURRENT_LOGIN = None
    started = await AntigravityAuthService(owner).start_login(
        client_id="id", client_secret="secret"
    )
    login = auth_service_module._CURRENT_LOGIN
    assert login is not None
    url = f"{started['redirect_uri']}?code=the-code&state={login.state_secret}"
    result = await AntigravityAuthService(other).complete_login_url(url)
    assert result["email"] == "user@example.com"
    assert exchanged == ["the-code"]
    assert AntigravityCredentialStore(owner).load_credentials() is not None
    assert AntigravityCredentialStore(other).load_credentials() is None
    assert not (other / "private").exists()
    auth_service_module._CURRENT_LOGIN = None


@pytest.mark.asyncio
async def test_complete_login_rejects_state_mismatch_without_consuming(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(
        "ANTIGRAVITY_REDIRECT_URI",
        "https://tutor.example.com/api/settings/providers/google-antigravity/oauth/callback",
    )

    exchanged: list[str] = []

    async def fake_exchange(self: AntigravityAuthService, op: object, *, code: str):
        exchanged.append(code)
        return _fake_token(), "secret"

    monkeypatch.setattr(AntigravityAuthService, "_exchange_code", fake_exchange)
    auth_service_module._CURRENT_LOGIN = None
    owner = tmp_path / "owner"
    started = await AntigravityAuthService(owner).start_login(
        client_id="id", client_secret="secret"
    )
    login = auth_service_module._CURRENT_LOGIN
    assert login is not None
    with pytest.raises(AntigravityAuthError) as exc:
        await AntigravityAuthService(tmp_path / "other").complete_login_url(
            f"{started['redirect_uri']}?code=the-code&state=wrong-state-value"
        )
    assert exc.value.code == "state_mismatch"
    assert auth_service_module._CURRENT_LOGIN is not None
    assert exchanged == []
    result = await AntigravityAuthService(tmp_path / "other").complete_login_url(
        f"{started['redirect_uri']}?code=the-code&state={login.state_secret}"
    )
    assert result["email"] == "user@example.com"
    assert exchanged == ["the-code"]
    assert AntigravityCredentialStore(owner).load_credentials() is not None
    auth_service_module._CURRENT_LOGIN = None


@pytest.mark.asyncio
async def test_complete_login_consumes_google_error_with_matching_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(
        "ANTIGRAVITY_REDIRECT_URI",
        "https://tutor.example.com/api/settings/providers/google-antigravity/oauth/callback",
    )

    async def boom(self: AntigravityAuthService, op: object, *, code: str):
        raise AssertionError("token exchange must not run on Google error")

    monkeypatch.setattr(AntigravityAuthService, "_exchange_code", boom)
    auth_service_module._CURRENT_LOGIN = None
    started = await AntigravityAuthService(tmp_path / "owner").start_login(
        client_id="id", client_secret="secret"
    )
    login = auth_service_module._CURRENT_LOGIN
    assert login is not None
    with pytest.raises(AntigravityAuthError) as exc:
        await AntigravityAuthService(tmp_path).complete_login_url(
            f"{started['redirect_uri']}?error=access_denied&state={login.state_secret}"
        )
    assert exc.value.code == "oauth_error"
    assert auth_service_module._CURRENT_LOGIN is None


def test_service_status(tmp_path: Path) -> None:
    service = AntigravityAuthService(tmp_path)
    status = service.get_status()
    assert not status["connected"]
    assert "models" in status
    assert len(status["models"]) > 0
