from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


class ReportCache:
    def __init__(self, cache_dir: Path = settings.report_cache_dir):
        self.cache_dir = cache_dir

    def get(self, cache_hash: str) -> dict[str, Any] | None:
        path = self.cache_dir / f"{cache_hash}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def set(self, cache_hash: str, payload: dict[str, Any]) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / f"{cache_hash}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def update_player_vector_cache(
    *,
    cache_key: dict[str, Any],
    vector: dict[str, float | None],
    confidence: dict[str, float],
    metadata: dict[str, Any],
) -> None:
    cache = PlayerVectorCache(settings.player_vector_cache_path)
    value = CachedPlayerVector(
        vector=vector,
        feature_order=list(vector.keys()),
        metadata=metadata,
        confidence=confidence,
        cache_key=cache_key,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    cache.set(value)
