from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


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

    # Open a Stockfish engine for beyond-book worst-case extension when available.
    # The engine is opened per-request (not shared across requests) so each
    # threadpool task owns its engine lifecycle and avoids concurrency issues.
    engine = None
    stockfish_path = settings.stockfish_path
    if stockfish_path:
        try:
            engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not open Stockfish at %s: %s", stockfish_path, exc)
            engine = None

    try:
        nodes = get_opening_study_tree_children(
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
            engine=engine,
        )
    except PlayerVectorFeatureMismatch as exc:
        raise ValueError(str(exc)) from exc
    finally:
        if engine is not None:
            try:
                engine.quit()
            except Exception:  # noqa: BLE001
                pass

    return {
        "targetColor": request.target_color,
        "prefixUci": list(request.prefix_uci or []),
        "children": [node.to_dict() for node in nodes],
        "vectorSource": vector_source,
        "playerVector": player_vector,
    }
