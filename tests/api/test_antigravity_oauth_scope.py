"""Who may drive the Google Antigravity OAuth lifecycle.

Ordinary users act on their own owner-scoped credentials. Partners are refused.
Payload client secrets are an admin fallback, not a user-supplied override.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from deeptutor.api.routers import settings as settings_router
from deeptutor.multi_user.models import CurrentUser, UserScope
from deeptutor.services.partners.scope import PARTNER_USER_PREFIX

ROUTES = [
    ("post", "/api/settings/providers/google-antigravity/oauth/start"),
    ("get", "/api/settings/providers/google-antigravity/oauth/status"),
    ("post", "/api/settings/providers/google-antigravity/oauth/complete"),
    ("post", "/api/settings/providers/google-antigravity/oauth/disconnect"),
]


@pytest.fixture(autouse=True)
def _enable_antigravity_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTIGRAVITY_ENABLED", "1")


class _Service:
    instances: list["_Service"] = []

    def __init__(self, _root: Any) -> None:
        self.calls: list[Any] = []
        _Service.instances.append(self)

    async def start_login(
        self,
        *,
        client_id: str,
        client_secret: str,
        client_secret_candidates: tuple[str, ...] = (),
        client_source: str = "",
    ) -> dict[str, Any]:
        self.calls.append(
            ("start", client_id, client_secret, client_secret_candidates, client_source)
        )
        return {"status": "started"}

    def get_status(self) -> dict[str, Any]:
        self.calls.append("status")
        return {"connection": "disconnected"}

    async def complete_login_url(self, pasted_url: str) -> dict[str, Any]:
        self.calls.append(("complete", pasted_url))
        return {"status": "connected"}

    def disconnect(self) -> None:
        self.calls.append("disconnect")


def _user(uid: str, *, role: str, root) -> CurrentUser:
    return CurrentUser(
        id=uid,
        username=uid,
        role=role,
        scope=UserScope(kind="user", user_id=uid, root=root),
    )


def _body(path: str) -> dict[str, str] | None:
    if path.endswith("/complete"):
        return {"callback_url": "http://127.0.0.1/callback?code=1&state=s"}
    return None


@pytest.fixture
def client(tmp_path, monkeypatch) -> tuple[TestClient, dict[str, CurrentUser]]:
    _Service.instances.clear()
    monkeypatch.setattr(
        "deeptutor.services.antigravity_auth.service.AntigravityAuthService",
        _Service,
    )
    monkeypatch.setenv("ANTIGRAVITY_CLIENT_ID", "env-id")
    monkeypatch.setenv("ANTIGRAVITY_CLIENT_SECRET", "env-secret")
    current: dict[str, CurrentUser] = {
        "user": _user("u_alice", role="user", root=tmp_path / "alice")
    }
    monkeypatch.setattr(settings_router, "get_current_user", lambda: current["user"])
    app = FastAPI()
    app.include_router(settings_router.router, prefix="/api/settings")
    return TestClient(app), current


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_ordinary_user_reaches_owner_scoped_service(client, method, path) -> None:
    test_client, _current = client
    kwargs = {}
    body = _body(path)
    if body is not None:
        kwargs["json"] = body

    response = getattr(test_client, method)(path, **kwargs)

    assert response.status_code == 200
    assert _Service.instances, "the request must reach the owner-scoped service"
    assert _Service.instances[-1].calls


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_partner_is_refused(client, tmp_path, method, path) -> None:
    test_client, current = client
    current["user"] = _user(f"{PARTNER_USER_PREFIX}ada", role="user", root=tmp_path / "partner")
    kwargs = {}
    body = _body(path)
    if body is not None:
        kwargs["json"] = body

    response = getattr(test_client, method)(path, **kwargs)

    assert response.status_code == 403
    assert "Antigravity" in response.json()["detail"]
    assert "Codex" not in response.json()["detail"]
    assert _Service.instances == []


def test_non_admin_payload_credentials_are_rejected(client, monkeypatch) -> None:
    test_client, _current = client
    monkeypatch.delenv("ANTIGRAVITY_CLIENT_ID", raising=False)
    monkeypatch.delenv("ANTIGRAVITY_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(
        "deeptutor.services.antigravity_auth.client_credentials.discover_local_client_credentials",
        lambda: None,
    )
    _Service.instances.clear()

    response = test_client.post(
        "/api/settings/providers/google-antigravity/oauth/start",
        json={"client_id": "user-id", "client_secret": "user-secret"},
    )

    assert response.status_code == 400
    assert _Service.instances == []


def test_admin_payload_credentials_are_accepted(client, tmp_path, monkeypatch) -> None:
    test_client, current = client
    current["user"] = _user("admin", role="admin", root=tmp_path / "admin")
    monkeypatch.delenv("ANTIGRAVITY_CLIENT_ID", raising=False)
    monkeypatch.delenv("ANTIGRAVITY_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(
        "deeptutor.services.antigravity_auth.client_credentials.discover_local_client_credentials",
        lambda: None,
    )
    _Service.instances.clear()

    response = test_client.post(
        "/api/settings/providers/google-antigravity/oauth/start",
        json={"client_id": "admin-id", "client_secret": "admin-secret"},
    )

    assert response.status_code == 200
    assert _Service.instances[-1].calls == [
        ("start", "admin-id", "admin-secret", (), "admin_payload")
    ]


def test_start_uses_local_install_when_env_missing(client, monkeypatch) -> None:
    test_client, _current = client
    monkeypatch.delenv("ANTIGRAVITY_CLIENT_ID", raising=False)
    monkeypatch.delenv("ANTIGRAVITY_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(
        "deeptutor.services.antigravity_auth.client_credentials.discover_local_client_credentials",
        lambda: ("local-id", ("local-secret", "alt-secret")),
    )
    _Service.instances.clear()

    response = test_client.post("/api/settings/providers/google-antigravity/oauth/start")

    assert response.status_code == 200
    assert _Service.instances[-1].calls == [
        ("start", "local-id", "local-secret", ("alt-secret",), "local_install")
    ]


def test_antigravity_disabled_by_default_returns_403(client, monkeypatch) -> None:
    test_client, _ = client
    monkeypatch.delenv("ANTIGRAVITY_ENABLED", raising=False)
    for method, path in ROUTES:
        fn = getattr(test_client, method)
        body = _body(path)
        response = fn(path) if method == "get" or body is None else fn(path, json=body)
        assert response.status_code == 403, (path, response.status_code)
        assert "disabled" in response.text


PUBLIC_CALLBACK = "/api/settings/providers/google-antigravity/oauth/callback"


@pytest.fixture
def public_client(tmp_path, monkeypatch) -> TestClient:
    _Service.instances.clear()
    monkeypatch.setattr(
        "deeptutor.services.antigravity_auth.service.AntigravityAuthService",
        _Service,
    )
    app = FastAPI()
    app.include_router(settings_router.public_router, prefix="/api/settings")
    return TestClient(app)


def test_public_callback_completes_without_auth(public_client) -> None:
    response = public_client.get(
        PUBLIC_CALLBACK,
        params={"code": "abc", "state": "s"},
    )
    assert response.status_code == 200
    assert "successful" in response.text
    assert "<script" not in response.text.lower()
    assert _Service.instances[-1].calls
    kind, pasted = _Service.instances[-1].calls[-1]
    assert kind == "complete"
    assert "code=abc" in pasted


def test_public_callback_disabled_returns_403(public_client, monkeypatch) -> None:
    monkeypatch.delenv("ANTIGRAVITY_ENABLED", raising=False)
    response = public_client.get(PUBLIC_CALLBACK, params={"code": "abc"})
    assert response.status_code == 403
    assert "disabled" in response.text
    assert _Service.instances == []


def test_public_callback_escapes_error_html(public_client, monkeypatch) -> None:
    from deeptutor.services.antigravity_auth.contracts import AntigravityAuthError

    async def boom(self, pasted_url: str) -> dict[str, Any]:
        raise AntigravityAuthError(
            "oauth_error",
            'Google returned error: <script>alert(1)</script>',
            400,
        )

    monkeypatch.setattr(_Service, "complete_login_url", boom)
    response = public_client.get(PUBLIC_CALLBACK, params={"error": "<script>"})
    assert response.status_code == 400
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
