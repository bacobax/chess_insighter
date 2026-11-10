from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.services.mongo_service import blob_delete, blob_get, blob_items, blob_put
from backend.settings import settings
from utils.player_vector_cache import CachedPlayerVector, PlayerVectorCache


def normalize_for_hash(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): normalize_for_hash(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple, set)):
        normalized = [normalize_for_hash(item) for item in value]
        if all(isinstance(item, (str, int, float, bool, type(None))) for item in normalized):
            return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True))
        return normalized
    return value


def stable_hash(payload: dict[str, Any]) -> str:
    normalized = normalize_for_hash(payload)
    raw = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def dataset_identity(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {"path": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def report_cache_key(
    *,
    username: str,
    hparams: dict[str, Any],
    filters: dict[str, Any],
    max_games: int,
    engine_depth: int,
    use_engine: bool,
) -> dict[str, Any]:
    return {
        "source": "chess.com",
        "username": username.strip().lower(),
        "hparams": hparams,
        "filters": filters,
        "max_games": int(max_games),
        "engine_depth": int(engine_depth),
        "use_engine": bool(use_engine),
        "feature_model_version": "player_opening_match_v3_color_aware",
        "datasets": {
            "openings": dataset_identity(settings.openings_path),
            "opening_vectors": dataset_identity(settings.opening_vectors_path),
        },
    }


REPORTS_NAMESPACE = "reports"
PLAYER_VECTORS_NAMESPACE = "player_vectors"


class ReportCache:
    """Full report payloads, keyed by the deterministic report cache hash."""

    def get(self, cache_hash: str) -> dict[str, Any] | None:
        return blob_get(REPORTS_NAMESPACE, cache_hash)

    def set(self, cache_hash: str, payload: dict[str, Any]) -> None:
        blob_put(REPORTS_NAMESPACE, cache_hash, payload)

    def delete(self, cache_hash: str) -> None:
        blob_delete(REPORTS_NAMESPACE, cache_hash)


class MongoPlayerVectorCache(PlayerVectorCache):
    """``PlayerVectorCache`` backed by MongoDB instead of ``player_vectors.json``."""

    def __init__(self) -> None:
        pass

    def get(self, key: dict[str, Any]) -> CachedPlayerVector | None:
        entry = blob_get(PLAYER_VECTORS_NAMESPACE, self.key_id(key))
        if entry is None:
            return None
        return CachedPlayerVector(
            vector=entry["vector"],
            feature_order=list(entry["feature_order"]),
            metadata=dict(entry.get("metadata", {})),
            confidence=dict(entry.get("confidence", {})),
            cache_key=dict(entry["cache_key"]),
            created_at=str(entry["created_at"]),
            cache_hit=True,
        )

    def set(self, value: CachedPlayerVector) -> None:
        blob_put(
            PLAYER_VECTORS_NAMESPACE,
            self.key_id(value.cache_key),
            {
                "vector": value.vector,
                "feature_order": value.feature_order,
                "metadata": value.metadata,
                "confidence": value.confidence,
                "cache_key": value.cache_key,
                "created_at": value.created_at,
            },
            username=str(value.cache_key.get("username") or "").strip().lower(),
        )

    def entries(self) -> dict[str, Any]:
        return dict(blob_items(PLAYER_VECTORS_NAMESPACE))


def update_player_vector_cache(
    *,
    cache_key: dict[str, Any],
    vector: dict[str, float | None],
    confidence: dict[str, float],
    metadata: dict[str, Any],
) -> None:
    value = CachedPlayerVector(
        vector=vector,
        feature_order=list(vector.keys()),
        metadata=metadata,
        confidence=confidence,
        cache_key=cache_key,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    MongoPlayerVectorCache().set(value)
