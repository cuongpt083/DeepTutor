"""Service coordinator for Google Antigravity OAuth."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from pathlib import Path
import secrets
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .catalog import ANTIGRAVITY_MODELS
from .client_credentials import rejects_custom_redirect_uri
from .constants import (
    ANTIGRAVITY_LOGIN_TIMEOUT_SECONDS,
    ANTIGRAVITY_REDIRECT_URI,
    is_loopback_redirect_uri,
    resolve_antigravity_redirect_uri,
)
from .contracts import (
    AntigravityAuthError,
    AntigravityCredentials,
    AntigravityModel,
    AntigravityReauthRequiredError,
    AntigravityToken,
)
from .oauth import (
    AntigravityLoopbackCallback,
    AntigravityOAuthClient,
    PkceCodes,
    build_authorize_url,
    generate_pkce,
    oauth_state_matches,
)
from .storage import AntigravityCredentialStore

logger = logging.getLogger(__name__)

# Process-wide lock: only one OAuth login in flight at a time
_LOGIN_LOCK = asyncio.Lock()


@dataclass
class _ActiveLogin:
    operation_id: str
    state_secret: str
    pkce: PkceCodes
    callback: AntigravityLoopbackCallback | None
    client_id: str
    client_secret: str
    client_secret_candidates: tuple[str, ...]
    redirect_uri: str
    deadline: float
    user_root: Path


_CURRENT_LOGIN: _ActiveLogin | None = None


class AntigravityAuthService:
    """Owner-scoped auth service."""

    def __init__(self, user_root: Path) -> None:
        self.user_root = Path(user_root)
        self.store = AntigravityCredentialStore(self.user_root)

    def get_status(self) -> dict[str, Any]:
        creds = self.store.load_credentials()
        if not creds:
            return {
                "connected": False,
                "email": "",
                "project_id": "",
                "models": [m.id for m in ANTIGRAVITY_MODELS],
            }
        return {
            "connected": True,
            "email": creds.token.email,
            "project_id": creds.project_id,
            "models": [m.id for m in ANTIGRAVITY_MODELS],
            "expires_at": creds.token.expires_at,
        }

    async def start_login(
        self,
        *,
        client_id: str,
        client_secret: str,
        client_secret_candidates: tuple[str, ...] = (),
        client_source: str = "",
    ) -> dict[str, Any]:
        global _CURRENT_LOGIN

        if not client_id or not client_secret:
            raise AntigravityAuthError(
                "missing_client_credentials",
                "Google OAuth Client ID and Client Secret are required.",
                400,
            )

        async with _LOGIN_LOCK:
            if _CURRENT_LOGIN and time.time() < _CURRENT_LOGIN.deadline:
                if _CURRENT_LOGIN.callback:
                    await _CURRENT_LOGIN.callback.close()

            pkce = generate_pkce()
            state_secret = secrets.token_urlsafe(32)
            operation_id = secrets.token_urlsafe(16)
            redirect_uri = resolve_antigravity_redirect_uri()
            loopback = is_loopback_redirect_uri(redirect_uri)
            if not loopback and rejects_custom_redirect_uri(
                client_id, source=client_source
            ):
                raise AntigravityAuthError(
                    "redirect_uri_mismatch",
                    (
                        "The borrowed agy/gemini-cli OAuth client only allows "
                        f"{ANTIGRAVITY_REDIRECT_URI}. Unset ANTIGRAVITY_REDIRECT_URI "
                        "and paste that localhost callback after Google sign-in, "
                        "or use your own Google Cloud client registered with "
                        f"{redirect_uri}."
                    ),
                    400,
                )

            callback = None
            if loopback:
                try:
                    callback = await AntigravityLoopbackCallback.start(
                        expected_state=state_secret
                    )
                except Exception as exc:
                    logger.warning(
                        "Could not bind port 51121 loopback: %s. Relying on paste-callback.",
                        exc,
                    )

            auth_url = build_authorize_url(
                client_id=client_id,
                redirect_uri=redirect_uri,
                state=state_secret,
                pkce=pkce,
            )

            deadline = time.time() + ANTIGRAVITY_LOGIN_TIMEOUT_SECONDS
            _CURRENT_LOGIN = _ActiveLogin(
                operation_id=operation_id,
                state_secret=state_secret,
                pkce=pkce,
                callback=callback,
                client_id=client_id,
                client_secret=client_secret,
                client_secret_candidates=tuple(client_secret_candidates),
                redirect_uri=redirect_uri,
                deadline=deadline,
                user_root=self.user_root,
            )

            if callback:
                asyncio.create_task(self._wait_loopback_login(operation_id, callback))

            return {
                "operation_id": operation_id,
                "authorize_url": auth_url,
                "redirect_uri": redirect_uri,
                "loopback": loopback,
            }

    async def _wait_loopback_login(
        self,
        operation_id: str,
        callback: AntigravityLoopbackCallback,
    ) -> None:
        global _CURRENT_LOGIN
        try:
            res = await callback.wait(timeout_s=ANTIGRAVITY_LOGIN_TIMEOUT_SECONDS)
            if not res.code or res.error:
                return
            async with _LOGIN_LOCK:
                if not _CURRENT_LOGIN or _CURRENT_LOGIN.operation_id != operation_id:
                    return
                op = _CURRENT_LOGIN
                _CURRENT_LOGIN = None

            token, secret = await self._exchange_code(
                op,
                code=res.code,
            )
            creds = AntigravityCredentials(
                token=token,
                client_id=op.client_id,
                client_secret=secret,
                project_id=token.project_id,
                updated_at=time.time(),
            )
            store = AntigravityCredentialStore(op.user_root)
            store.store_credentials(creds)
            logger.info("Antigravity OAuth loopback login complete for %s", token.email)
        except Exception as exc:
            logger.error("Antigravity loopback callback processing error: %s", exc)

    async def complete_login_url(self, pasted_url: str) -> dict[str, Any]:
        """Support manual paste-callback for remote/containerized environments."""
        global _CURRENT_LOGIN
        split = urlsplit(pasted_url.strip())
        params = parse_qs(split.query)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        error = params.get("error", [None])[0]

        consume = False
        failure: AntigravityAuthError | None = None
        async with _LOGIN_LOCK:
            if not _CURRENT_LOGIN:
                raise AntigravityAuthError("no_active_login", "No pending login session.", 400)
            if time.time() > _CURRENT_LOGIN.deadline:
                _CURRENT_LOGIN = None
                raise AntigravityAuthError("login_expired", "Login session expired.", 400)
            op = _CURRENT_LOGIN
            state_ok = oauth_state_matches(state, op.state_secret)
            if error:
                if state_ok:
                    _CURRENT_LOGIN = None
                    consume = True
                failure = AntigravityAuthError(
                    "oauth_error", f"Google returned error: {error}", 400
                )
            elif not code or not state:
                failure = AntigravityAuthError(
                    "invalid_callback", "Missing code or state in pasted URL.", 400
                )
            elif not state_ok:
                failure = AntigravityAuthError(
                    "state_mismatch", "OAuth state parameter mismatch.", 400
                )
            else:
                _CURRENT_LOGIN = None
                consume = True

        if consume and op.callback:
            await op.callback.close()
        if failure is not None:
            raise failure

        token, secret = await self._exchange_code(op, code=code)
        creds = AntigravityCredentials(
            token=token,
            client_id=op.client_id,
            client_secret=secret,
            project_id=token.project_id,
            updated_at=time.time(),
        )
        AntigravityCredentialStore(op.user_root).store_credentials(creds)
        return {
            "status": "success",
            "email": token.email,
            "project_id": token.project_id,
        }

    async def _exchange_code(
        self,
        op: _ActiveLogin,
        *,
        code: str,
    ) -> tuple[AntigravityToken, str]:
        secrets_to_try = (op.client_secret, *op.client_secret_candidates)
        last_error: Exception | None = None
        for secret in secrets_to_try:
            if not secret:
                continue
            client = AntigravityOAuthClient(op.client_id, secret)
            try:
                token = await client.exchange_code(
                    code=code,
                    redirect_uri=op.redirect_uri,
                    code_verifier=op.pkce.verifier,
                )
            except Exception as exc:
                last_error = exc
                continue
            return token, secret
        if last_error is not None:
            raise last_error
        raise AntigravityAuthError(
            "missing_client_credentials",
            "Google OAuth Client ID and Client Secret are required.",
            400,
        )

    async def get_valid_token(self) -> AntigravityToken:
        """Return valid token, refreshing if expired."""
        creds = self.store.load_credentials()
        if not creds:
            raise AntigravityReauthRequiredError()

        token = creds.token
        if not token.is_expired(lead_s=300.0):
            return token

        # Refresh
        client = AntigravityOAuthClient(creds.client_id, creds.client_secret)
        try:
            new_token = await client.refresh_token(token.refresh_token)
        except Exception as exc:
            logger.warning("Antigravity token refresh failed: %s", exc)
            raise AntigravityReauthRequiredError(f"Token refresh failed: {exc}") from exc

        new_creds = AntigravityCredentials(
            token=new_token,
            client_id=creds.client_id,
            client_secret=creds.client_secret,
            project_id=new_token.project_id or creds.project_id,
            updated_at=time.time(),
        )
        self.store.store_credentials(new_creds)
        return new_token

    def disconnect(self) -> None:
        self.store.clear()
