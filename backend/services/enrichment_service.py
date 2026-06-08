from __future__ import annotations

from typing import Any

import chess.engine

from backend.settings import settings
from utils.game_enrichment_transformer import EnrichedGame, GameEnrichmentTransformer
from utils.opening_repository import OpeningRepository
from utils.player_vector_cache import heuristic_enrich_game_data


def enrich_games(
    raw_games: list[dict[str, Any]],
    *,
    engine_depth: int,
    use_engine: bool,
) -> tuple[list[EnrichedGame], dict[str, Any]]:
    opening_repository = OpeningRepository(settings.openings_path)
    engine_path = settings.stockfish_path
    metadata = {
        "engine_used": False,
        "engine_depth": engine_depth,
        "engine_path": engine_path,
        "fallback_reason": None,
    }

    if use_engine and engine_path:
        try:
            transformer = GameEnrichmentTransformer(
                stockfish_path=engine_path,
                opening_repository=opening_repository,
                engine_limit=chess.engine.Limit(depth=engine_depth),
            )
            enriched = transformer.transform_games(raw_games)
            metadata["engine_used"] = True
            return enriched, metadata
        except Exception as exc:
            metadata["fallback_reason"] = str(exc)
    else:
        metadata["fallback_reason"] = "engine disabled" if not use_engine else "stockfish unavailable"

    enriched = heuristic_enrich_game_data(
        raw_games,
        opening_repository=opening_repository,
        engine_depth=engine_depth,
    )
    return enriched, metadata
