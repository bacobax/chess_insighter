from __future__ import annotations

from typing import Any, Optional

import chess
import chess.engine
import numpy as np

from utils.opening_feature_transformer import (
    EnginePositionInfo,
    analyse_position,
    castling_opportunity_score,
    castling_side,
    clamp01,
    endgame_likelihood_proxy,
    king_safety_risk_for_color,
    material_imbalance_score,
    pawn_structure_sharpness,
    pawn_structure_signature,
    position_complexity,
    preferred_castling_side,
    quiet_position_score,
    signature_entropy,
    tactical_position_score,
)


FEATURES = [
    "structure_diversity",
    "material_imbalance",
    "quiet_position_density",
    "tactical_density",
    "middlegame_complexity",
    "endgame_likelihood_proxy",
    "opposite_castle_tendency",
    "early_castle_tendency",
    "pawn_structure_sharpness",
    "king_safety_risk",
]

FEATURE_ALIASES = {
    "early_castle_tendency": "early_castling_tendency",
    "opposite_castle_tendency": "opposite_side_castling_tendency",
}


def canonical_feature_name(name: str) -> str:
    return FEATURE_ALIASES.get(name, name)


def heuristic_engine_info(board: chess.Board) -> EnginePositionInfo:
    forcing_moves = [
        move
        for move in board.legal_moves
        if board.is_capture(move) or board.gives_check(move) or move.promotion is not None
    ]
    return EnginePositionInfo(
        eval_cp=None,
        top_moves=[],
        best_move_cp_gain=0.0,
        eval_volatility=0.0,
        low_gap_between_top_moves=0.0,
        best_move_is_forcing=bool(forcing_moves),
        forcing_line_depth=1 if forcing_moves else 0,
    )


def analyse_position_safe(
    board: chess.Board,
    engine: Optional[chess.engine.SimpleEngine],
    *,
    engine_depth: int = 10,
    multipv: int = 3,
    cache: Optional[dict[str, EnginePositionInfo]] = None,
) -> EnginePositionInfo:
    if engine is None:
        return heuristic_engine_info(board)

    try:
        return analyse_position(
            engine,
            board,
            limit=chess.engine.Limit(depth=engine_depth),
            multipv=multipv,
            cache=cache if cache is not None else {},
        )
    except Exception:
        return heuristic_engine_info(board)


def extract_position_features(
    board: chess.Board,
    target_color: chess.Color,
    engine: Optional[chess.engine.SimpleEngine] = None,
    *,
    engine_depth: int = 10,
    engine_cache: Optional[dict[str, EnginePositionInfo]] = None,
) -> dict[str, float]:
    engine_info = analyse_position_safe(
        board,
        engine,
        engine_depth=engine_depth,
        cache=engine_cache,
    )

    tactical = tactical_position_score(board, engine_info)
    quiet = quiet_position_score(board, engine_info)
    king_risk = king_safety_risk_for_color(
        board,
        target_color,
        board.fullmove_number,
        castling_side(board.king(target_color)) is not None,
    )

    # A single board cannot know historical structure entropy. Use the current
    # pawn signature's non-starting sharpness as a robust one-position proxy.
    structure_diversity = signature_entropy([pawn_structure_signature(chess.Board()), pawn_structure_signature(board)])

    features = {
        "structure_diversity": structure_diversity,
        "material_imbalance": material_imbalance_score(board, engine_info),
        "quiet_position_density": quiet,
        "tactical_density": tactical,
        "middlegame_complexity": position_complexity(board, engine_info),
        "endgame_likelihood_proxy": endgame_likelihood_proxy(
            board,
            tactical_density=tactical,
            king_safety_risk=king_risk,
            eval_volatility=engine_info.eval_volatility,
        ),
        "opposite_side_castling_tendency": opposite_castling_tendency(board),
        "early_castling_tendency": early_castling_tendency(board, target_color),
        "pawn_structure_sharpness": pawn_structure_sharpness(board),
        "king_safety_risk": king_risk,
    }
    return {key: clamp01(value) for key, value in features.items()}


def extract_position_vector(
    board: chess.Board,
    target_color: chess.Color,
    engine: Optional[chess.engine.SimpleEngine],
    feature_names: list[str],
    *,
    engine_depth: int = 10,
    engine_cache: Optional[dict[str, EnginePositionInfo]] = None,
) -> np.ndarray:
    features = extract_position_features(
        board,
        target_color,
        engine,
        engine_depth=engine_depth,
        engine_cache=engine_cache,
    )
    return np.array(
        [float(features.get(canonical_feature_name(name), 0.0)) for name in feature_names],
        dtype=float,
    )


def player_vector_to_array(vector: dict[str, Optional[float]], feature_names: list[str]) -> np.ndarray:
    return np.array(
        [
            0.0 if vector.get(canonical_feature_name(name)) is None else float(vector[canonical_feature_name(name)])
            for name in feature_names
        ],
        dtype=float,
    )


def cosine_similarity_safe(a: np.ndarray, b: np.ndarray) -> float:
    left_norm = float(np.linalg.norm(a))
    right_norm = float(np.linalg.norm(b))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return float(np.dot(a, b) / (left_norm * right_norm))


def early_castling_tendency(board: chess.Board, target_color: chess.Color) -> float:
    side = castling_side(board.king(target_color))
    if side is not None:
        if board.fullmove_number <= 8:
            return 1.0
        if board.fullmove_number <= 10:
            return 0.8
        if board.fullmove_number <= 12:
            return 0.6
        return 0.3

    opportunity = castling_opportunity_score(board, target_color)
    if board.fullmove_number < 8:
        return 0.65 * opportunity
    return 0.35 * opportunity


def opposite_castling_tendency(board: chess.Board) -> float:
    white_side = castling_side(board.king(chess.WHITE))
    black_side = castling_side(board.king(chess.BLACK))
    if white_side is not None and black_side is not None:
        return 1.0 if white_side != black_side else 0.0

    white_preferred = white_side or preferred_castling_side(board, chess.WHITE)
    black_preferred = black_side or preferred_castling_side(board, chess.BLACK)
    if white_preferred is None or black_preferred is None or white_preferred == black_preferred:
        return 0.0
    return 0.55 * min(
        castling_opportunity_score(board, chess.WHITE),
        castling_opportunity_score(board, chess.BLACK),
    )


def clamp_feature_dict(values: dict[str, Any]) -> dict[str, float]:
    return {key: clamp01(float(value or 0.0)) for key, value in values.items()}
