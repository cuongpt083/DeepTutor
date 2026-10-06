"""Resolve Google Antigravity OAuth client credentials without shipping secrets.

Google OAuth client credentials are deliberately not committed: a bundled
client secret trips secret scanners and cannot be rotated without a release.
Resolution order matches nanobot:

1. ``ANTIGRAVITY_CLIENT_ID`` / ``ANTIGRAVITY_CLIENT_SECRET`` environment
2. Borrow the client embedded in a local ``gemini-cli`` / ``agy`` install
3. Admin-supplied payload (settings UI), never ordinary-user payload
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
import re
import shutil


CLIENT_ID_ENV_VAR = "ANTIGRAVITY_CLIENT_ID"
CLIENT_SECRET_ENV_VAR = "ANTIGRAVITY_CLIENT_SECRET"

#: Public Gemini CLI shared client id. A local ``agy`` install bundles both this
#: client and Antigravity's own dedicated one, so prefer the shared client (the
#: one ``agy`` actually authenticates with) when several are found.
SHARED_CLIENT_ID_PREFIX = "1071006060591-"

_CLIENT_ID_PATTERN = re.compile(rb"(\d{10,}-[a-z0-9]+\.apps\.googleusercontent\.com)")
#: Google issues ``GOCSPX-`` secrets with a fixed 28-character body; matching the
#: exact length keeps two adjacent secrets from being captured as one run.
_CLIENT_SECRET_PATTERN = re.compile(rb"(GOCSPX-[A-Za-z0-9_-]{28})")
_SCAN_CHUNK_BYTES = 1024 * 1024
_SCAN_OVERLAP_BYTES = 256


@dataclass(frozen=True)
class ResolvedAntigravityClient:
    client_id: str
    client_secret: str
    client_secret_candidates: tuple[str, ...] = ()
    source: str = "env"


def _env(name: str) -> str:
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else ""


def _is_dir(path: Path) -> bool:
    """``Path.is_dir()`` but EACCES/other OS errors are "not a directory".

    pathlib only swallows ENOENT-class errors. In Docker the backend runs as
    UID 1000 while inheriting ``HOME=/root`` from supervisord, so probing
    ``~/.bun/install/global/node_modules`` raises ``PermissionError`` instead
    of returning False — and Sign in with Google 500s.
    """

    try:
        return path.is_dir()
    except OSError:
        return False


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _glob_dirs(root: Path, pattern: str) -> list[Path]:
    try:
        return sorted(root.glob(pattern))
    except OSError:
        return []


def _rglob_files(root: Path, pattern: str) -> list[Path]:
    try:
        return sorted(root.rglob(pattern))
    except OSError:
        return []


def _node_global_module_roots() -> list[Path]:
    """Best-effort global ``node_modules`` roots without shelling out to npm."""

    home = Path.home()
    candidates: list[Path] = [
        home / ".bun" / "install" / "global" / "node_modules",
        home / ".npm-global" / "lib" / "node_modules",
        Path("/usr/local/lib/node_modules"),
        Path("/usr/lib/node_modules"),
    ]
    candidates.extend(_glob_dirs(home, ".nvm/versions/node/*/lib/node_modules"))
    appdata = os.environ.get("APPDATA")
    if appdata:
        npm = Path(appdata) / "npm" / "node_modules"
        candidates.append(npm)
        candidates.extend(_glob_dirs(Path(appdata) / "nvm", "v*/node_modules"))
        candidates.extend(_glob_dirs(Path(appdata) / "nvm", "installs/v*/node_modules"))
    return [path for path in candidates if _is_dir(path)]


def _candidate_client_files() -> list[Path]:
    """Files that may embed the shared Gemini CLI OAuth client, cheapest first."""

    files: list[Path] = []
    for root in _node_global_module_roots():
        package = root / "@google" / "gemini-cli"
        if _is_dir(package):
            files.extend(_rglob_files(package, "*.js"))
    on_path = shutil.which("agy")
    if on_path:
        files.append(Path(on_path))
    for raw in (
        "~/.local/bin/agy",
        "~/.antigravity/bin/agy",
        "~/.antigravity-cli/bin/agy",
        "/usr/local/bin/agy",
    ):
        path = Path(raw).expanduser()
        if _is_file(path):
            files.append(path)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        windows_binary = Path(local_app_data) / "agy" / "bin" / "agy.exe"
        if _is_file(windows_binary):
            files.append(windows_binary)
    seen: list[Path] = []
    for path in files:
        if path not in seen:
            seen.append(path)
    return seen


def _dedupe(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def _scan_file_for_client(path: Path) -> tuple[list[str], list[str]]:
    ids: list[str] = []
    secrets: list[str] = []
    try:
        with path.open("rb") as handle:
            carry = b""
            while chunk := handle.read(_SCAN_CHUNK_BYTES):
                window = carry + chunk
                ids.extend(m.group(1).decode() for m in _CLIENT_ID_PATTERN.finditer(window))
                secrets.extend(
                    m.group(1).decode() for m in _CLIENT_SECRET_PATTERN.finditer(window)
                )
                carry = window[-_SCAN_OVERLAP_BYTES:]
    except OSError:
        return [], []
    return _dedupe(ids), _dedupe(secrets)


@lru_cache(maxsize=1)
def discover_local_client_credentials() -> tuple[str, tuple[str, ...]] | None:
    """Borrow the OAuth client embedded in a local ``gemini-cli`` or ``agy``.

    Returns ``(client_id, candidate_secrets)`` for the first local install that
    exposes a client, preferring the Gemini CLI shared client. A file can contain
    several clients (Antigravity bundles a dedicated one too) but the binary does
    not encode which secret pairs with which id, so every secret found is
    returned in order and the caller retries until Google accepts one. Cached per
    process because scanning a large ``agy`` binary is not free.
    """

    fallback: tuple[str, tuple[str, ...]] | None = None
    for path in _candidate_client_files():
        ids, secrets = _scan_file_for_client(path)
        if not ids or not secrets:
            continue
        client_id = next(
            (value for value in ids if value.startswith(SHARED_CLIENT_ID_PREFIX)), ids[0]
        )
        found = (client_id, tuple(secrets))
        if client_id.startswith(SHARED_CLIENT_ID_PREFIX):
            return found
        if fallback is None:
            fallback = found
    return fallback


def resolve_antigravity_oauth_client(
    *,
    env_client_id: str = "",
    env_client_secret: str = "",
    payload_client_id: str = "",
    payload_client_secret: str = "",
    allow_payload: bool = False,
) -> ResolvedAntigravityClient | None:
    """Pick client credentials: env, then local install, then admin payload."""

    client_id = (env_client_id or "").strip()
    client_secret = (env_client_secret or "").strip()
    candidates: tuple[str, ...] = ()
    source = "env"
    if not (client_id and client_secret):
        discovered = discover_local_client_credentials()
        if discovered is not None:
            discovered_id, discovered_secrets = discovered
            client_id = client_id or discovered_id
            if not client_secret and discovered_secrets:
                client_secret = discovered_secrets[0]
                candidates = discovered_secrets[1:]
                source = "local_install"
    if not (client_id and client_secret) and allow_payload:
        client_id = client_id or (payload_client_id or "").strip()
        client_secret = client_secret or (payload_client_secret or "").strip()
        if client_id and client_secret:
            source = "admin_payload"
    if not client_id or not client_secret:
        return None
    return ResolvedAntigravityClient(
        client_id=client_id,
        client_secret=client_secret,
        client_secret_candidates=candidates,
        source=source,
    )
