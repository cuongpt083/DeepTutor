"""PKCE, loopback listener, and HTTP client for Google Antigravity OAuth."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
import hashlib
import json
import logging
import secrets
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from .constants import (
    ANTIGRAVITY_CALLBACK_PATH,
    ANTIGRAVITY_CALLBACK_PORT,
    ANTIGRAVITY_REDIRECT_URI,
    DEFAULT_AUTHORIZE_URL,
    DEFAULT_ENDPOINT,
    DEFAULT_PROJECT_ID,
    DEFAULT_REVOKE_URL,
    DEFAULT_SCOPES,
    DEFAULT_TOKEN_URL,
    DEFAULT_USERINFO_URL,
)
from .contracts import AntigravityAuthError, AntigravityToken

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PkceCodes:
    verifier: str
    challenge: str


@dataclass(frozen=True)
class OAuthCallbackResult:
    code: str | None
    state: str | None
    error: str | None


_OAUTH_STATE_MAX_LENGTH = 128
_BASE64URL_STATE_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
)


def oauth_state_matches(value: str | None, expected: str) -> bool:
    if (
        not value
        or len(value) > _OAUTH_STATE_MAX_LENGTH
        or any(character not in _BASE64URL_STATE_CHARS for character in value)
    ):
        return False
    try:
        value_bytes = value.encode("ascii")
        expected_bytes = expected.encode("ascii")
    except UnicodeEncodeError:
        return False
    return secrets.compare_digest(value_bytes, expected_bytes)


def generate_pkce() -> PkceCodes:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return PkceCodes(verifier=verifier, challenge=challenge)


def build_authorize_url(
    *,
    client_id: str,
    redirect_uri: str = ANTIGRAVITY_REDIRECT_URI,
    state: str,
    pkce: PkceCodes,
    scopes: tuple[str, ...] = DEFAULT_SCOPES,
) -> str:
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "code_challenge": pkce.challenge,
            "code_challenge_method": "S256",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
    )
    return f"{DEFAULT_AUTHORIZE_URL}?{query}"


class AntigravityLoopbackCallback:
    """One-shot loopback callback on port 51121."""

    hosts = ("127.0.0.1", "::1")

    def __init__(
        self,
        server: asyncio.AbstractServer,
        result: asyncio.Future[OAuthCallbackResult],
        port: int,
    ) -> None:
        self._server = server
        self._result = result
        self.port = port
        self._accepting = True

    @classmethod
    async def start(
        cls,
        port: int = ANTIGRAVITY_CALLBACK_PORT,
        expected_state: str | None = None,
    ) -> AntigravityLoopbackCallback:
        loop = asyncio.get_running_loop()
        result: asyncio.Future[OAuthCallbackResult] = loop.create_future()

        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            status = "404 Not Found"
            body = "Not found"
            try:
                line = await asyncio.wait_for(reader.readline(), timeout=5.0)
                if not line:
                    return
                parts = line.decode("latin1", errors="replace").split()
                if len(parts) >= 2 and parts[0] == "GET":
                    target = parts[1]
                    split = urlsplit(target)
                    if split.path.rstrip("/") == ANTIGRAVITY_CALLBACK_PATH.rstrip("/"):
                        params = parse_qs(split.query)
                        code = params.get("code", [None])[0]
                        state = params.get("state", [None])[0]
                        error = params.get("error", [None])[0]

                        state_ok = (
                            expected_state is None
                            or oauth_state_matches(state, expected_state)
                        )
                        if not state_ok:
                            status = "400 Bad Request"
                            body = "State mismatch. Login failed."
                            if not result.done():
                                result.set_result(
                                    OAuthCallbackResult(code=None, state=state, error="state_mismatch")
                                )
                        elif error:
                            status = "200 OK"
                            body = f"OAuth error: {error}. You may close this tab."
                            if not result.done():
                                result.set_result(
                                    OAuthCallbackResult(code=None, state=state, error=error)
                                )
                        elif code:
                            status = "200 OK"
                            body = "Google Antigravity authentication successful! You can close this tab."
                            if not result.done():
                                result.set_result(
                                    OAuthCallbackResult(code=code, state=state, error=None)
                                )
                        else:
                            status = "400 Bad Request"
                            body = "Missing code or error parameter."
            except Exception as exc:
                logger.debug("Loopback callback exception: %s", exc)
            finally:
                html = (
                    f"<!DOCTYPE html><html><head><title>DeepTutor Antigravity</title></head>"
                    f"<body style='font-family: sans-serif; text-align: center; padding: 40px;'>"
                    f"<h2>{body}</h2><p>Return to DeepTutor.</p></body></html>"
                )
                response = (
                    f"HTTP/1.1 {status}\r\n"
                    f"Content-Type: text/html; charset=utf-8\r\n"
                    f"Content-Length: {len(html.encode('utf-8'))}\r\n"
                    f"Connection: close\r\n\r\n{html}"
                )
                with contextlib_suppress():
                    writer.write(response.encode("utf-8"))
                    await writer.drain()
                    writer.close()
                    await writer.wait_closed()

        server = None
        for host in cls.hosts:
            try:
                server = await asyncio.start_server(handle, host, port)
                break
            except OSError:
                continue

        if server is None:
            raise AntigravityAuthError(
                "port_in_use",
                f"Loopback port {port} is unavailable. Ensure port {port} is free.",
                409,
            )

        return cls(server, result, port)

    async def wait(self, timeout_s: float = 300.0) -> OAuthCallbackResult:
        try:
            return await asyncio.wait_for(self._result, timeout=timeout_s)
        except asyncio.TimeoutError:
            return OAuthCallbackResult(code=None, state=None, error="timeout")
        finally:
            await self.close()

    async def close(self) -> None:
        if self._accepting:
            self._accepting = False
            self._server.close()
            with contextlib_suppress():
                await self._server.wait_closed()


class contextlib_suppress:
    def __enter__(self) -> None:
        pass
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        return True


class AntigravityOAuthClient:
    """HTTP client for token exchange, refresh, and project discovery."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret

    async def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> AntigravityToken:
        import time

        data = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(DEFAULT_TOKEN_URL, data=data)
            if resp.status_code != 200:
                raise AntigravityAuthError(
                    "token_exchange_failed",
                    f"Token exchange failed: {resp.status_code} {resp.text}",
                    resp.status_code,
                )
            payload = resp.json()

        now = time.time()
        expires_in = int(payload.get("expires_in") or 3600)
        access_token = str(payload.get("access_token") or "")
        refresh_token = str(payload.get("refresh_token") or "")
        id_token = str(payload.get("id_token") or "")
        scopes = tuple(str(payload.get("scope") or "").split())

        email = await self._fetch_email(access_token)
        project_id = await self._discover_project_id(access_token)

        return AntigravityToken(
            access_token=access_token,
            token_type=str(payload.get("token_type") or "Bearer"),
            refresh_token=refresh_token,
            expires_in=expires_in,
            expires_at=now + expires_in,
            scopes=scopes,
            id_token=id_token,
            email=email,
            project_id=project_id,
        )

    async def refresh_token(self, refresh_token: str) -> AntigravityToken:
        import time

        data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(DEFAULT_TOKEN_URL, data=data)
            if resp.status_code != 200:
                raise AntigravityAuthError(
                    "token_refresh_failed",
                    f"Token refresh failed: {resp.status_code} {resp.text}",
                    resp.status_code,
                )
            payload = resp.json()

        now = time.time()
        expires_in = int(payload.get("expires_in") or 3600)
        access_token = str(payload.get("access_token") or "")
        new_refresh = str(payload.get("refresh_token") or refresh_token)
        id_token = str(payload.get("id_token") or "")
        scopes = tuple(str(payload.get("scope") or "").split())

        email = await self._fetch_email(access_token)
        project_id = await self._discover_project_id(access_token)

        return AntigravityToken(
            access_token=access_token,
            token_type=str(payload.get("token_type") or "Bearer"),
            refresh_token=new_refresh,
            expires_in=expires_in,
            expires_at=now + expires_in,
            scopes=scopes,
            id_token=id_token,
            email=email,
            project_id=project_id,
        )

    async def _fetch_email(self, access_token: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    DEFAULT_USERINFO_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if resp.status_code == 200:
                    return str(resp.json().get("email") or "")
        except Exception:
            pass
        return ""

    async def _discover_project_id(self, access_token: str) -> str:
        """Call loadCodeAssist / onboardUser to discover GCP project id."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": "Antigravity/1.21.9",
        }
        body = {"metadata": {"ideType": "IDE_UNSPECIFIED", "platform": "PLATFORM_UNSPECIFIED", "pluginType": "GEMINI"}}

        # 1. loadCodeAssist
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{DEFAULT_ENDPOINT}/v1internal:loadCodeAssist",
                    headers=headers,
                    json=body,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    pid = (
                        data.get("cloudaicompanionProject")
                        or data.get("currentTier", {}).get("cloudaicompanionProject")
                        or data.get("project")
                    )
                    if pid:
                        return str(pid)
        except Exception as exc:
            logger.debug("loadCodeAssist discovery failed: %s", exc)

        # 2. onboardUser
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{DEFAULT_ENDPOINT}/v1internal:onboardUser",
                    headers=headers,
                    json={"tierId": "TIER_FREE"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    pid = (
                        data.get("cloudaicompanionProject")
                        or data.get("response", {}).get("cloudaicompanionProject")
                    )
                    if pid:
                        return str(pid)
        except Exception as exc:
            logger.debug("onboardUser discovery failed: %s", exc)

        return DEFAULT_PROJECT_ID
