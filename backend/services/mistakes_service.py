from __future__ import annotations

import chess.engine

from backend.models import MistakePositionRequest, MistakePositionResponse
from backend.services.openings_service import serializable
from backend.settings import settings
from utils.mistakes_analyzer import MistakeAnalyzerConfig, analyse_position_lines


def analyse_position(request: MistakePositionRequest) -> MistakePositionResponse:
    engine_path = settings.stockfish_path
    if not engine_path:
        raise ValueError("Stockfish is required for position analysis.")

    config = MistakeAnalyzerConfig(
        engine_depth=request.engine_depth,
        max_punishment_plies=request.max_plies,
    )
    with chess.engine.SimpleEngine.popen_uci(engine_path) as engine:
        result = analyse_position_lines(
            engine=engine,
            fen=request.fen,
            player_color=request.player_color,
            rating=request.rating,
            config=config,
            max_line_plies=6,
        )

    return MistakePositionResponse(
        top_lines=result["top_lines"],
        optimal_line=[serializable(m) for m in result["optimal_line"]],
    )
