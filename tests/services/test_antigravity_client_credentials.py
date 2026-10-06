"""Local Gemini CLI / agy OAuth client discovery (no network I/O)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from deeptutor.services.antigravity_auth import client_credentials as creds_module
from deeptutor.services.antigravity_auth.client_credentials import (
    discover_local_client_credentials,
    resolve_antigravity_oauth_client,
)

# Synthetic samples assembled at runtime so no credential-shaped literal is
# committed (secret scanners flag the raw patterns). Secrets carry the fixed
# 28-character body Google issues.
_FAKE_CLIENT_ID = (
    "123456789012-abcdefghij"
    "klmnopqrstuvwxyz012345.apps.googleusercontent.com"
)
_FAKE_SHARED_CLIENT_ID = (
    "1071006060591-fakeclient"
    "body00000000000000.apps.googleusercontent.com"
)
_FAKE_CLIENT_SECRET = "GOCS" + "PX-" + "0123456789abcdefghijklmnopqr"
_FAKE_CLIENT_SECRET_ALT = "GOCS" + "PX-" + "zyxwvutsrqponmlkjihgfedcba98"


@pytest.fixture(autouse=True)
def _clear_credential_cache() -> Iterator[None]:
    discover_local_client_credentials.cache_clear()
    yield
    discover_local_client_credentials.cache_clear()


def test_discover_local_client_credentials_prefers_shared_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    blob = tmp_path / "agy.bin"
    blob.write_bytes(
        " ".join(
            [
                _FAKE_CLIENT_ID,
                _FAKE_SHARED_CLIENT_ID,
                _FAKE_CLIENT_SECRET,
                _FAKE_CLIENT_SECRET_ALT,
            ]
        ).encode()
    )
    monkeypatch.setattr(creds_module, "_candidate_client_files", lambda: [blob])

    assert discover_local_client_credentials() == (
        _FAKE_SHARED_CLIENT_ID,
        (_FAKE_CLIENT_SECRET, _FAKE_CLIENT_SECRET_ALT),
    )


def test_discover_local_client_credentials_without_shared_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    blob = tmp_path / "gemini.bin"
    blob.write_bytes((_FAKE_CLIENT_ID + " " + _FAKE_CLIENT_SECRET).encode())
    monkeypatch.setattr(creds_module, "_candidate_client_files", lambda: [blob])

    assert discover_local_client_credentials() == (_FAKE_CLIENT_ID, (_FAKE_CLIENT_SECRET,))


def test_discover_local_client_credentials_requires_both(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    blob = tmp_path / "agy.bin"
    blob.write_bytes(_FAKE_CLIENT_ID.encode())
    monkeypatch.setattr(creds_module, "_candidate_client_files", lambda: [blob])

    assert discover_local_client_credentials() is None


def test_resolve_prefers_env_over_discovery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    blob = tmp_path / "agy.bin"
    blob.write_bytes((_FAKE_SHARED_CLIENT_ID + " " + _FAKE_CLIENT_SECRET).encode())
    monkeypatch.setattr(creds_module, "_candidate_client_files", lambda: [blob])

    resolved = resolve_antigravity_oauth_client(
        env_client_id="env-id",
        env_client_secret="env-secret",
    )
    assert resolved is not None
    assert resolved.client_id == "env-id"
    assert resolved.client_secret == "env-secret"
    assert resolved.source == "env"


def test_resolve_falls_back_to_local_install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    blob = tmp_path / "agy.bin"
    blob.write_bytes(
        (
            _FAKE_SHARED_CLIENT_ID
            + " "
            + _FAKE_CLIENT_SECRET
            + " "
            + _FAKE_CLIENT_SECRET_ALT
        ).encode()
    )
    monkeypatch.setattr(creds_module, "_candidate_client_files", lambda: [blob])

    resolved = resolve_antigravity_oauth_client()
    assert resolved is not None
    assert resolved.client_id == _FAKE_SHARED_CLIENT_ID
    assert resolved.client_secret == _FAKE_CLIENT_SECRET
    assert resolved.client_secret_candidates == (_FAKE_CLIENT_SECRET_ALT,)
    assert resolved.source == "local_install"


def test_resolve_admin_payload_when_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(creds_module, "discover_local_client_credentials", lambda: None)

    assert (
        resolve_antigravity_oauth_client(
            payload_client_id="admin-id",
            payload_client_secret="admin-secret",
            allow_payload=False,
        )
        is None
    )
    resolved = resolve_antigravity_oauth_client(
        payload_client_id="admin-id",
        payload_client_secret="admin-secret",
        allow_payload=True,
    )
    assert resolved is not None
    assert resolved.client_id == "admin-id"
    assert resolved.client_secret == "admin-secret"
    assert resolved.source == "admin_payload"
