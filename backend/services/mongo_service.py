"""MongoDB Atlas access: one lazily created client, collection indexes and a compressed blob store.

Structured application state (users, sessions, reports, ...) lives in regular collections.
Large opaque payloads (report artifacts, per-game analysis, training plans, player vectors)
go through the blob helpers below, which store zlib-compressed JSON so they keep their
exact JSON round-trip and stay well below MongoDB's 16 MB document limit.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import threading
from typing import Any
import zlib

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database

from backend.settings import settings


BLOBS = "artifacts"
_lock = threading.Lock()
_client: MongoClient | None = None
_database: Database | None = None
_indexed = False


class DatabaseUnavailable(RuntimeError):
    """Raised when the MongoDB connection is not configured."""


def _ensure_indexes(db: Database) -> None:
    db.users.create_index([("email", ASCENDING)], unique=True)
    db.email_verifications.create_index([("token_digest", ASCENDING)])
    db.email_verifications.create_index([("user_id", ASCENDING)])
    db.sessions.create_index([("user_id", ASCENDING)])
    db.reports.create_index([("owner_id", ASCENDING), ("cache_hash", ASCENDING)], unique=True)
    db.reports.create_index([("owner_id", ASCENDING), ("username_key", ASCENDING), ("status", ASCENDING)])
    db.reports.create_index([("cache_hash", ASCENDING)])
    db.target_players.create_index([("owner_id", ASCENDING), ("username_key", ASCENDING)], unique=True)
    db.audit_events.create_index([("user_id", ASCENDING)])
    db[BLOBS].create_index([("namespace", ASCENDING), ("key", ASCENDING)])
    db.repertoires.create_index([("owner_id", ASCENDING)])


def get_database() -> Database:
    global _client, _database, _indexed
    with _lock:
        if _database is None:
            if not settings.mongodb_uri:
                raise DatabaseUnavailable("MONGODB_URI is not set; add it to .env.")
            _client = MongoClient(settings.mongodb_uri, tz_aware=True)
            _database = _client[settings.mongodb_db]
        if not _indexed:
            _ensure_indexes(_database)
            _indexed = True
        return _database


def use_database(db: Database | None) -> None:
    """Swap the active database (tests inject a mongomock database here)."""
    global _database, _indexed
    with _lock:
        _database = db
        _indexed = False


def collection(name: str):
    return get_database()[name]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _blob_id(namespace: str, key: str) -> str:
    return f"{namespace}:{key}"


def encode_payload(payload: Any) -> bytes:
    return zlib.compress(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"), 6)


def decode_payload(data: bytes) -> Any:
    return json.loads(zlib.decompress(data).decode("utf-8"))


def blob_put(namespace: str, key: str, payload: Any, **metadata: Any) -> None:
    collection(BLOBS).replace_one(
        {"_id": _blob_id(namespace, key)},
        {
            "_id": _blob_id(namespace, key),
            "namespace": namespace,
            "key": key,
            "data": encode_payload(payload),
            "updated_at": _now(),
            **metadata,
        },
        upsert=True,
    )


def blob_get(namespace: str, key: str) -> Any | None:
    document = collection(BLOBS).find_one({"_id": _blob_id(namespace, key)}, {"data": 1})
    if document is None:
        return None
    return decode_payload(bytes(document["data"]))


def blob_exists(namespace: str, key: str) -> bool:
    return collection(BLOBS).count_documents({"_id": _blob_id(namespace, key)}, limit=1) > 0


def blob_delete(namespace: str, key: str) -> None:
    collection(BLOBS).delete_one({"_id": _blob_id(namespace, key)})


def blob_delete_prefix(namespace: str, prefix: str) -> int:
    result = collection(BLOBS).delete_many(
        {"namespace": namespace, "key": {"$regex": f"^{re.escape(prefix)}"}}
    )
    return result.deleted_count


def blob_items(namespace: str) -> list[tuple[str, Any]]:
    return [
        (document["key"], decode_payload(bytes(document["data"])))
        for document in collection(BLOBS).find({"namespace": namespace}, {"key": 1, "data": 1})
    ]
