from __future__ import annotations

import copy
import fcntl
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, TypeVar

from backend.settings import settings


SCHEMA_VERSION = 1
COLLECTIONS = (
    "users",
    "email_verifications",
    "sessions",
    "target_players",
    "reports",
    "audit_events",
)
T = TypeVar("T")
_thread_lock = threading.RLock()


class DatabaseCorruptionError(RuntimeError):
    """Raised when persistent state cannot be trusted."""


def empty_database() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        **{collection: [] for collection in COLLECTIONS},
    }


class JsonDatabase:
    """Small transactional document store with a Mongo-friendly collection shape."""

    def __init__(self, path: Path | None = None):
        self.path = path or settings.app_database_path
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return empty_database()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DatabaseCorruptionError(f"Could not read application database: {exc}") from exc
        if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
            raise DatabaseCorruptionError("Unsupported or malformed application database schema.")
        for collection in COLLECTIONS:
            if not isinstance(raw.get(collection), list):
                raise DatabaseCorruptionError(f"Malformed database collection: {collection}")
        return raw

    def _save_unlocked(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def read(self) -> dict[str, Any]:
        with _thread_lock:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            with self.lock_path.open("a+", encoding="utf-8") as lock_handle:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_SH)
                try:
                    return copy.deepcopy(self._load_unlocked())
                finally:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    def transaction(self, operation: Callable[[dict[str, Any]], T]) -> T:
        with _thread_lock:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            with self.lock_path.open("a+", encoding="utf-8") as lock_handle:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
                try:
                    data = self._load_unlocked()
                    result = operation(data)
                    self._save_unlocked(data)
                    return result
                finally:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
