from __future__ import annotations

from typing import Any

import chess.engine

from backend.models import GamesQueryRequest, MistakesAnalysisRequest, MistakesAnalysisResponse
from backend.services.chesscom_service import fetch_latest_games_for_report, query_games
from backend.services.openings_service import serializable
from backend.settings import settings
from utils.game_enrichment_transformer import GameEnrichmentTransformer
from utils.mistakes_analyzer import MistakeAnalyzerConfig, analyze_mistakes
from utils.opening_repository import OpeningRepository


def build_mistakes_analysis(request: MistakesAnalysisRequest) -> MistakesAnalysisResponse:
    engine_path = settings.stockfish_path
    if not engine_path:
        raise ValueError("Stockfish is required for mistakes analysis.")

    raw_games = _raw_games_for_request(request)
    if not raw_games:
        raise ValueError("No games found for the requested username and filters.")

    opening_repository = OpeningRepository(settings.openings_path)
    enriched_games = []
    with chess.engine.SimpleEngine.popen_uci(engine_path) as engine:
        transformer = GameEnrichmentTransformer(
            stockfish_path=engine_path,
            opening_repository=opening_repository,
            engine_limit=chess.engine.Limit(depth=request.engine_depth),
        )
        position_analysis_cache = {}
        for game_data in raw_games:
            if "pgn" not in game_data:
                continue
            enriched_games.append(
                transformer.transform_game(
                    game_data=game_data,
                    engine=engine,
                    position_analysis_cache=position_analysis_cache,
                )
            )

        if not enriched_games:
            raise ValueError("No games could be enriched for mistakes analysis.")

        config = MistakeAnalyzerConfig(
            engine_depth=request.engine_depth,
            max_punishment_plies=request.max_punishment_plies,
        )
        analysis = analyze_mistakes(
            enriched_games,
            username=request.username,
            config=config,
            engine=engine,
        )

    metadata: dict[str, Any] = {
        "username": request.username,
        "games_selected": len(raw_games),
        "games_enriched": len(enriched_games),
        "selected_game_ids": request.selected_game_ids,
        "engine_used": True,
        "engine_depth": request.engine_depth,
        "max_punishment_plies": request.max_punishment_plies,
        "engine_path": engine_path,
        "filters": {
            "time_classes": request.time_classes,
            "rated_filter": request.rated_filter,
            "since_year": request.since_year,
            "since_month": request.since_month,
            "until_year": request.until_year,
            "until_month": request.until_month,
        },
    }
    return MistakesAnalysisResponse(
        metadata=metadata,
        summary=serializable(analysis.summary),
        mistakes=serializable(analysis.mistakes),
    )


def _raw_games_for_request(request: MistakesAnalysisRequest) -> list[dict[str, Any]]:
    if request.selected_game_ids:
        selected_ids = set(request.selected_game_ids)
        games, _has_more, _total_loaded = query_games(
            GamesQueryRequest(
                username=request.username,
                page=1,
                page_size=min(500, max(request.max_games, len(selected_ids))),
                time_classes=request.time_classes,
                rated_filter=request.rated_filter,
                since_year=request.since_year,
                since_month=request.since_month,
                until_year=request.until_year,
                until_month=request.until_month,
            )
        )
        selected = [
            game
            for game in games
            if _game_identifier(game) in selected_ids
            or (game.get("uuid") in selected_ids)
            or (game.get("url") in selected_ids)
        ]
        missing = selected_ids - {
            identifier
            for game in selected
            for identifier in [_game_identifier(game), game.get("uuid"), game.get("url")]
            if identifier
        }
        if missing:
            raise ValueError(
                "Selected games were not found in the requested game window: "
                + ", ".join(sorted(missing))
            )
        return selected

    return fetch_latest_games_for_report(
        username=request.username,
        max_games=request.max_games,
        time_classes=request.time_classes,
        rated_filter=request.rated_filter,
        since_year=request.since_year,
        since_month=request.since_month,
        until_year=request.until_year,
        until_month=request.until_month,
    )


def _game_identifier(game: dict[str, Any]) -> str | None:
    return game.get("uuid") or game.get("url")
