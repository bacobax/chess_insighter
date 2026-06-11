from __future__ import annotations

from pathlib import Path
from typing import Any

import chess.engine

from backend.models import OpeningStudyTreeChildrenRequest
from backend.services.cache_service import ReportCache
from backend.settings import settings
from utils.opening_study_tree import (
    PlayerVectorFeatureMismatch,
    get_opening_study_tree_children,
    load_player_vector_from_cache,
)

def _resolve_opening_vectors_path(request: OpeningStudyTreeChildrenRequest) -> str:
    path = Path(request.opening_vectors_path) if request.opening_vectors_path else settings.opening_vectors_path
    if not path.exists():
        raise FileNotFoundError(f"Opening feature vectors not found: {path}")
    return str(path)


def _resolve_player_vector(request: OpeningStudyTreeChildrenRequest) -> tuple[dict[str, float], str]:
    """Return (player_vector, source_description).

    Priority:
    1. cache_hash — load from the report cache produced by /api/report/build.
       This is the correct path: the vector was computed from the specific games
       and filters the user configured (time class, rated, date range, etc.).
    2. username — fall back to the flat player_vectors.json cache. Fast, but
       ignores game filters; uses whichever computation happened to be cached
       most recently for that username.
    """
    if request.cache_hash:
        cached = ReportCache().get(request.cache_hash)
        if cached is None:
            raise FileNotFoundError(
                f"Report cache entry not found: {request.cache_hash}. "
                "Build a player report first via /api/report/build."
            )
        stats = (cached.get("report") or {}).get("statistics_bundle") or {}
        # Reports currently store a single generalized vector (not color-split).
        vector = stats.get("matcher_ready_player_vector") or {}
        if not vector:
            raise ValueError(
                f"Report {request.cache_hash[:12]}… has no matcher-ready player vector. "
                "The report may be incomplete or from an older format."
            )
        return {str(k): float(v) for k, v in vector.items() if v is not None}, f"report:{request.cache_hash[:12]}"

    # Flat-cache fallback.
    cache_path = request.player_vector_cache_path or str(settings.player_vector_cache_path)
    vector = load_player_vector_from_cache(cache_path, request.username)
    return vector, f"flat-cache:username={request.username}"


def opening_study_tree_children(request: OpeningStudyTreeChildrenRequest) -> dict[str, Any]:
    opening_vectors_path = _resolve_opening_vectors_path(request)
    player_vector, vector_source = _resolve_player_vector(request)
    weights = request.weights.to_weights() if request.weights is not None else None
    engine_path = settings.stockfish_path

    def _compute(engine: chess.engine.SimpleEngine | None) -> list[Any]:
        return get_opening_study_tree_children(
            player_vector=player_vector,
            opening_vectors_path=opening_vectors_path,
            target_color=request.target_color,
            prefix_uci=list(request.prefix_uci or []),
            top_k=request.top_k,
            opponent_top_k=request.opponent_top_k,
            weights=weights,
            similarity_type=request.similarity_type,
            weighted_matching=request.weighted_matching,
            matcher_weights=request.matcher_weights,
            soundness_engine=engine,
        )

    try:
        if engine_path is None:
            nodes = _compute(None)
        else:
            try:
                with chess.engine.SimpleEngine.popen_uci(engine_path) as engine:
                    nodes = _compute(engine)
            except Exception:
                nodes = _compute(None)
    except PlayerVectorFeatureMismatch as exc:
        raise ValueError(str(exc)) from exc

    return {
        "targetColor": request.target_color,
        "prefixUci": list(request.prefix_uci or []),
        "children": [node.to_dict() for node in nodes],
        "vectorSource": vector_source,
        "playerVector": player_vector,
    }
