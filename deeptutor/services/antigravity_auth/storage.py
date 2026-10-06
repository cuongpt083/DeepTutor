"""Secure credential storage for Google Antigravity OAuth."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
from typing import Any

from .contracts import AntigravityAuthError, AntigravityCredentials

_SCHEMA_VERSION = 1


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except FileNotFoundError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _assert_safe_regular_path(path: Path) -> None:
    parent = path.parent
    if parent.is_symlink() or _is_reparse_point(parent):
        raise AntigravityAuthError("unsafe_storage_path", "Unsafe storage path.", 500)
    if path.is_symlink() or _is_reparse_point(path):
        raise AntigravityAuthError("unsafe_storage_path", "Unsafe storage path.", 500)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    _assert_safe_regular_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


class AntigravityCredentialStore:
    """Store credentials scoped per user root."""

    def __init__(self, user_root: Path) -> None:
        self.root = Path(user_root) / "private" / "google-antigravity"
        self.credentials_path = self.root / "credentials.v1.json"
        self._thread_lock = threading.Lock()

    def load_credentials(self) -> AntigravityCredentials | None:
        with self._thread_lock:
            if not self.credentials_path.is_file():
                return None
            try:
                content = self.credentials_path.read_text(encoding="utf-8")
                payload = json.loads(content)
                if not isinstance(payload, dict):
                    return None
                return AntigravityCredentials.from_dict(payload)
            except Exception:
                return None

    def store_credentials(self, credentials: AntigravityCredentials) -> None:
        with self._thread_lock:
            self.root.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(self.credentials_path, credentials.to_dict())

    def clear(self) -> None:
        with self._thread_lock:
            if self.credentials_path.exists():
                self.credentials_path.unlink(missing_ok=True)
