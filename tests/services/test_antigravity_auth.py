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


def test_service_status(tmp_path: Path) -> None:
    service = AntigravityAuthService(tmp_path)
    status = service.get_status()
    assert not status["connected"]
    assert "models" in status
    assert len(status["models"]) > 0
