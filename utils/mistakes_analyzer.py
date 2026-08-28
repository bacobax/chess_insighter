from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

import chess
import chess.engine

from utils.game_enrichment_transformer import (
    EnrichedGame,
    EnrichedMove,
    default_cp_to_expected_points,
)
from utils.tactic_detector import TacticDetectorConfig, TacticTag, detect_tactics


@dataclass(frozen=True)
class MistakeAnalyzerConfig:
    candidate_cp_loss: int = 120
    candidate_wp_loss: float = 0.07
    inaccuracy_cp_loss: int = 50
    inaccuracy_wp_loss: float = 0.03
    mistake_cp_loss: int = 120
    mistake_wp_loss: float = 0.07
    blunder_cp_loss: int = 250
    blunder_wp_loss: float = 0.15
    retention_ratio: float = 0.70
    stable_volatility_cp: int = 60
    stable_top_gap_cp: int = 40
    stable_consecutive_plies: int = 2
    actual_eval_tolerance_cp: int = 80
    max_punishment_plies: int = 8
    multipv: int = 3
    engine_depth: int = 10
    mate_score: int = 100_000
    default_rating: int = 1500
    tactic_min_engine_gain_cp: int = 80


@dataclass(frozen=True)
class EngineMoveLine:
    rank: int
    move_uci: str
    eval_cp: int | None
    line_uci: list[str]
    mate_in: int | None = None


@dataclass(frozen=True)
class EngineRootAnalysis:
    eval_cp: int | None
    best_move_uci: str | None
    top_moves: list[EngineMoveLine]
    top_move_gap_cp: int | None
    eval_volatility_cp: float | None
    legal_move_count: int
    mate_in: int | None = None


@dataclass(frozen=True)
class PunishmentLineMove:
    ply_offset: int
    side_to_move: str
    move_uci: str
    san: str
    fen_before: str
    fen_after: str
    eval_cp: int | None
    user_eval_cp: int | None
    user_win_prob: float | None
    top_move_gap_cp: int | None
    eval_volatility_cp: float | None
    retained_wp_loss: float | None
    stable_after_move: bool
    tactics: list[TacticTag] = field(default_factory=list)


@dataclass(frozen=True)
class ActualPunishment:
    actual_punished: bool
    actual_punishing_moves_played: int
    missed_at_ply: int | None
    best_move_uci: str | None
    actual_move_uci: str | None
    actual_line_moves: list[PunishmentLineMove] = field(default_factory=list)
    tactics: list[TacticTag] = field(default_factory=list)


@dataclass(frozen=True)
class MistakeAnalysisItem:
    game_uuid: str | None
    game_url: str | None
    ply: int
    move_number: int
    player_color: str
    san: str
    uci: str
    fen_before: str
    fen_after: str
    severity: str
    cp_loss: int | None
    wp_loss: float | None
    user_eval_before_cp: int | None
    user_eval_after_cp: int | None
    win_prob_before: float | None
    win_prob_after: float | None
    best_line: list[str]
    best_line_moves: list[PunishmentLineMove]
    theoretical_punishment_depth: int
    theoretical_punishment_plies: int
    punishment_difficulty: float
    stability_reached: bool
    actual_punished: bool
    actual_punishing_moves_played: int
    missed_at_ply: int | None
    missed_best_move_uci: str | None
    missed_actual_move_uci: str | None
    actual_line_moves: list[PunishmentLineMove]
    tactics: list[TacticTag] = field(default_factory=list)
    actual_tactics: list[TacticTag] = field(default_factory=list)
    user_rating: int = 1500


@dataclass(frozen=True)
class MistakesAnalysisSummary:
    games_analyzed: int
    target_moves_analyzed: int
    mistake_count: int
    severity_counts: dict[str, int]
    theme_counts: dict[str, int]
    average_theoretical_punishment_depth: float | None
    actual_punished_count: int


@dataclass(frozen=True)
class MistakesAnalysis:
    username: str
    config: MistakeAnalyzerConfig
    summary: MistakesAnalysisSummary
    mistakes: list[MistakeAnalysisItem]


def analyze_mistakes(
    enriched_games: list[EnrichedGame],
    username: str,
    config: MistakeAnalyzerConfig | None,
    engine: Any,
) -> MistakesAnalysis:
    config = config or MistakeAnalyzerConfig()
    username_key = _username_key(username)
    analysis_cache: dict[str, EngineRootAnalysis] = {}
    mistakes: list[MistakeAnalysisItem] = []
    target_moves_analyzed = 0

    for game in enriched_games:
        target_color = _target_color(game, username_key)
        if target_color is None:
            continue
        rating = _target_rating(game, target_color, config)
        opponent_color = "black" if target_color == "white" else "white"

        for move_index, move in enumerate(game.moves):
            if move.player_color != target_color:
                continue
            target_moves_analyzed += 1

            cp_loss = _move_cp_loss_for_user(move, target_color)
            wp_loss = _move_wp_loss_for_user(move, target_color, rating)
            if not _is_candidate_mistake(cp_loss, wp_loss, config):
                continue

            severity = classify_mistake_severity(cp_loss, wp_loss, config)
            user_eval_before = _orient_cp(move.eval_before_cp, target_color)
            user_eval_after = _orient_cp(move.eval_after_cp, target_color)
            wp_before = move.win_prob_before
            if wp_before is None and user_eval_before is not None:
                wp_before = default_cp_to_expected_points(user_eval_before, rating)
            wp_after = move.win_prob_after
            if wp_after is None and user_eval_after is not None:
                wp_after = default_cp_to_expected_points(user_eval_after, rating)
            original_wp_loss = wp_loss or 0.0

            best_line_moves, stability_reached, punishment_difficulty = _build_best_line(
                engine=engine,
                board=chess.Board(move.fen_after),
                target_color=target_color,
                opponent_color=opponent_color,
                wp_before=wp_before,
                original_wp_loss=original_wp_loss,
                rating=rating,
                config=config,
                analysis_cache=analysis_cache,
            )
            theoretical_plies = len(best_line_moves)
            theoretical_depth = sum(
                1 for line_move in best_line_moves if line_move.side_to_move == opponent_color
            )
            actual = _evaluate_actual_punishment(
                engine=engine,
                game=game,
                mistake_index=move_index,
                target_color=target_color,
                opponent_color=opponent_color,
                wp_before=wp_before,
                original_wp_loss=original_wp_loss,
                required_opponent_moves=theoretical_depth,
                rating=rating,
                config=config,
                analysis_cache=analysis_cache,
            )
            theoretical_tactics = [
                tag
                for line_move in best_line_moves
                if line_move.side_to_move == opponent_color
                for tag in line_move.tactics
            ]

            mistakes.append(
                MistakeAnalysisItem(
                    game_uuid=game.uuid,
                    game_url=game.url,
                    ply=move.ply,
                    move_number=move.move_number,
                    player_color=target_color,
                    san=move.san,
                    uci=move.uci,
                    fen_before=move.fen_before,
                    fen_after=move.fen_after,
                    severity=severity,
                    cp_loss=cp_loss,
                    wp_loss=wp_loss,
                    user_eval_before_cp=user_eval_before,
                    user_eval_after_cp=user_eval_after,
                    win_prob_before=wp_before,
                    win_prob_after=wp_after,
                    best_line=[line_move.move_uci for line_move in best_line_moves],
                    best_line_moves=best_line_moves,
                    theoretical_punishment_depth=theoretical_depth,
                    theoretical_punishment_plies=theoretical_plies,
                    punishment_difficulty=punishment_difficulty,
                    stability_reached=stability_reached,
                    actual_punished=actual.actual_punished,
                    actual_punishing_moves_played=actual.actual_punishing_moves_played,
                    missed_at_ply=actual.missed_at_ply,
                    missed_best_move_uci=actual.best_move_uci,
                    missed_actual_move_uci=actual.actual_move_uci,
                    actual_line_moves=actual.actual_line_moves,
                    tactics=theoretical_tactics,
                    actual_tactics=actual.tactics,
                    user_rating=rating,
                )
            )

    mistakes.sort(key=lambda item: ((item.wp_loss or 0.0), (item.cp_loss or 0)), reverse=True)
    return MistakesAnalysis(
        username=username,
        config=config,
        summary=_summary(
            games=enriched_games,
            target_moves_analyzed=target_moves_analyzed,
            mistakes=mistakes,
        ),
        mistakes=mistakes,
    )


def classify_mistake_severity(
    cp_loss: int | None,
    wp_loss: float | None,
    config: MistakeAnalyzerConfig | None = None,
) -> str:
    config = config or MistakeAnalyzerConfig()
    cp = cp_loss or 0
    wp = wp_loss or 0.0
    if cp >= config.blunder_cp_loss or wp >= config.blunder_wp_loss:
        return "blunder"
    if cp >= config.mistake_cp_loss or wp >= config.mistake_wp_loss:
        return "mistake"
    if cp >= config.inaccuracy_cp_loss or wp >= config.inaccuracy_wp_loss:
        return "inaccuracy"
    return "none"


def _build_best_line(
    *,
    engine: Any,
    board: chess.Board,
    target_color: str,
    opponent_color: str,
    wp_before: float | None,
    original_wp_loss: float,
    rating: int,
    config: MistakeAnalyzerConfig,
    analysis_cache: dict[str, EngineRootAnalysis],
) -> tuple[list[PunishmentLineMove], bool, float]:
    line: list[PunishmentLineMove] = []
    temp_board = board.copy(stack=False)
    stable_streak = 0
    stability_reached = False
    punishment_difficulty = 0.0
    tactic_config = TacticDetectorConfig(min_engine_gain_cp=config.tactic_min_engine_gain_cp)

    for ply_offset in range(1, config.max_punishment_plies + 1):
        if temp_board.is_game_over():
            break

        info = _analyse_position_cached(engine, temp_board, config, analysis_cache)
        if info.best_move_uci is None:
            break

        side_to_move = _color_name(temp_board.turn)
        move = chess.Move.from_uci(info.best_move_uci)
        if move not in temp_board.legal_moves:
            break

        if side_to_move == opponent_color:
            punishment_difficulty += _decision_difficulty(info)

        fen_before = temp_board.fen()
        san = temp_board.san(move)
        user_eval_before = _orient_cp(info.eval_cp, target_color)

        temp_board.push(move)
        post_info = _analyse_position_cached(engine, temp_board, config, analysis_cache)
        user_eval_after = _orient_cp(post_info.eval_cp, target_color)
        engine_gain_cp = _engine_gain_against_user(
            before_user_eval=user_eval_before,
            after_user_eval=user_eval_after,
        )
        tactics = detect_tactics(
            chess.Board(fen_before),
            move,
            ply_offset=ply_offset,
            engine_gain_cp=engine_gain_cp,
            mate_in=info.mate_in,
            is_pv_move=True,
            config=tactic_config,
        )
        user_wp_after = (
            default_cp_to_expected_points(user_eval_after, rating)
            if user_eval_after is not None
            else None
        )
        retained_loss = _retained_wp_loss(wp_before, user_wp_after)
        stable_after_move = _is_stable_position(
            info=post_info,
            retained_wp_loss=retained_loss,
            original_wp_loss=original_wp_loss,
            config=config,
        )
        stable_streak = stable_streak + 1 if stable_after_move else 0
        fen_after = temp_board.fen()

        line.append(
            PunishmentLineMove(
                ply_offset=ply_offset,
                side_to_move=side_to_move,
                move_uci=move.uci(),
                san=san,
                fen_before=fen_before,
                fen_after=fen_after,
                eval_cp=post_info.eval_cp,
                user_eval_cp=user_eval_after,
                user_win_prob=user_wp_after,
                top_move_gap_cp=post_info.top_move_gap_cp,
                eval_volatility_cp=post_info.eval_volatility_cp,
                retained_wp_loss=retained_loss,
                stable_after_move=stable_after_move,
                tactics=tactics,
            )
        )

        if stable_streak >= config.stable_consecutive_plies:
            stability_reached = True
            break

    return line, stability_reached, min(1.0, punishment_difficulty)


def _evaluate_actual_punishment(
    *,
    engine: Any,
    game: EnrichedGame,
    mistake_index: int,
    target_color: str,
    opponent_color: str,
    wp_before: float | None,
    original_wp_loss: float,
    required_opponent_moves: int,
    rating: int,
    config: MistakeAnalyzerConfig,
    analysis_cache: dict[str, EngineRootAnalysis],
) -> ActualPunishment:
    if required_opponent_moves <= 0:
        return ActualPunishment(
            actual_punished=True,
            actual_punishing_moves_played=0,
            missed_at_ply=None,
            best_move_uci=None,
            actual_move_uci=None,
        )

    tactics: list[TacticTag] = []
    actual_line_moves: list[PunishmentLineMove] = []
    preserved_opponent_moves = 0
    punishment_requirement_satisfied = False
    tactic_config = TacticDetectorConfig(min_engine_gain_cp=config.tactic_min_engine_gain_cp)

    for ply_offset, actual_move in enumerate(
        game.moves[mistake_index + 1:mistake_index + 1 + config.max_punishment_plies],
        start=1,
    ):
        board = chess.Board(actual_move.fen_before)
        move = chess.Move.from_uci(actual_move.uci)
        if move not in board.legal_moves:
            return ActualPunishment(
                actual_punished=False,
                actual_punishing_moves_played=preserved_opponent_moves,
                missed_at_ply=ply_offset,
                best_move_uci=None,
                actual_move_uci=actual_move.uci,
                actual_line_moves=actual_line_moves,
                tactics=tactics,
            )

        info = _analyse_position_cached(engine, board, config, analysis_cache)
        actual_eval_cp = _analyse_forced_move(engine, board, move, config)
        best_user_eval = _orient_cp(info.eval_cp, target_color)
        actual_user_eval = _orient_cp(actual_eval_cp, target_color)
        actual_user_wp = (
            default_cp_to_expected_points(actual_user_eval, rating)
            if actual_user_eval is not None
            else None
        )
        retained_loss = _retained_wp_loss(wp_before, actual_user_wp)
        post_board = chess.Board(actual_move.fen_after)
        post_info = _analyse_position_cached(engine, post_board, config, analysis_cache)

        exact_top = actual_move.uci == info.best_move_uci
        within_eval_tolerance = (
            best_user_eval is not None
            and actual_user_eval is not None
            and actual_user_eval <= best_user_eval + config.actual_eval_tolerance_cp
        )
        is_pv_for_tactics = exact_top or within_eval_tolerance
        engine_gain_cp = _engine_gain_against_user(
            before_user_eval=_orient_cp(info.eval_cp, target_color),
            after_user_eval=actual_user_eval,
        )
        move_tactics = detect_tactics(
            board,
            move,
            ply_offset=ply_offset,
            engine_gain_cp=engine_gain_cp,
            mate_in=info.mate_in if exact_top else None,
            is_pv_move=is_pv_for_tactics,
            config=tactic_config,
        )
        actual_line_moves.append(
            PunishmentLineMove(
                ply_offset=ply_offset,
                side_to_move=actual_move.player_color,
                move_uci=actual_move.uci,
                san=actual_move.san,
                fen_before=actual_move.fen_before,
                fen_after=actual_move.fen_after,
                eval_cp=actual_eval_cp,
                user_eval_cp=actual_user_eval,
                user_win_prob=actual_user_wp,
                top_move_gap_cp=post_info.top_move_gap_cp,
                eval_volatility_cp=post_info.eval_volatility_cp,
                retained_wp_loss=retained_loss,
                stable_after_move=_is_stable_position(
                    info=post_info,
                    retained_wp_loss=retained_loss,
                    original_wp_loss=original_wp_loss,
                    config=config,
                ),
                tactics=move_tactics,
            )
        )

        if actual_move.player_color != opponent_color:
            continue

        retains_loss = (
            retained_loss is not None
            and retained_loss >= config.retention_ratio * original_wp_loss
        )
        if not (exact_top or within_eval_tolerance or retains_loss):
            if punishment_requirement_satisfied:
                break
            return ActualPunishment(
                actual_punished=False,
                actual_punishing_moves_played=preserved_opponent_moves,
                missed_at_ply=ply_offset,
                best_move_uci=info.best_move_uci,
                actual_move_uci=actual_move.uci,
                actual_line_moves=actual_line_moves,
                tactics=tactics,
            )

        preserved_opponent_moves += 1
        tactics.extend(move_tactics)
        if preserved_opponent_moves >= required_opponent_moves:
            punishment_requirement_satisfied = True

    return ActualPunishment(
        actual_punished=punishment_requirement_satisfied,
        actual_punishing_moves_played=preserved_opponent_moves,
        missed_at_ply=None,
        best_move_uci=None,
        actual_move_uci=None,
        actual_line_moves=actual_line_moves,
        tactics=tactics,
    )


def _analyse_position_cached(
    engine: Any,
    board: chess.Board,
    config: MistakeAnalyzerConfig,
    cache: dict[str, EngineRootAnalysis],
) -> EngineRootAnalysis:
    fen = board.fen()
    cached = cache.get(fen)
    if cached is not None:
        return cached
    info = _analyse_position(engine, board, config)
    cache[fen] = info
    return info


def _analyse_position(
    engine: Any,
    board: chess.Board,
    config: MistakeAnalyzerConfig,
) -> EngineRootAnalysis:
    legal_count = board.legal_moves.count()
    if board.is_game_over() or legal_count == 0:
        eval_cp = _terminal_eval_cp(board, config)
        return EngineRootAnalysis(
            eval_cp=eval_cp,
            best_move_uci=None,
            top_moves=[],
            top_move_gap_cp=0,
            eval_volatility_cp=0.0,
            legal_move_count=legal_count,
        )

    raw = engine.analyse(
        board,
        chess.engine.Limit(depth=config.engine_depth),
        multipv=min(config.multipv, max(1, legal_count)),
    )
    raw_infos = [raw] if isinstance(raw, dict) else list(raw)
    top_moves: list[EngineMoveLine] = []
    for rank, info in enumerate(raw_infos, start=1):
        pv = [_coerce_move(move) for move in (info.get("pv") or [])]
        pv = [move for move in pv if move is not None]
        if not pv:
            continue
        score = info.get("score")
        top_moves.append(
            EngineMoveLine(
                rank=rank,
                move_uci=pv[0].uci(),
                eval_cp=_score_to_white_cp(score, config),
                line_uci=[move.uci() for move in pv],
                mate_in=_score_to_white_mate(score),
            )
        )

    eval_cp = top_moves[0].eval_cp if top_moves else None
    return EngineRootAnalysis(
        eval_cp=eval_cp,
        best_move_uci=top_moves[0].move_uci if top_moves else None,
        top_moves=top_moves,
        top_move_gap_cp=_top_move_gap(top_moves, board.turn),
        eval_volatility_cp=_eval_volatility(top_moves),
        legal_move_count=legal_count,
        mate_in=top_moves[0].mate_in if top_moves else None,
    )


def _analyse_forced_move(
    engine: Any,
    board: chess.Board,
    move: chess.Move,
    config: MistakeAnalyzerConfig,
) -> int | None:
    if board.is_game_over():
        return _terminal_eval_cp(board, config)
    info = engine.analyse(
        board,
        chess.engine.Limit(depth=config.engine_depth),
        root_moves=[move],
    )
    return _score_to_white_cp(info.get("score"), config)


def _score_to_white_cp(score: Any, config: MistakeAnalyzerConfig) -> int | None:
    if score is None:
        return None
    if isinstance(score, (int, float)):
        return int(score)
    if hasattr(score, "white"):
        return score.white().score(mate_score=config.mate_score)
    return None


def _score_to_white_mate(score: Any) -> int | None:
    if score is None or not hasattr(score, "white"):
        return None
    white_score = score.white()
    if not hasattr(white_score, "mate"):
        return None
    mate = white_score.mate()
    return None if mate is None else int(mate)


def _coerce_move(value: Any) -> chess.Move | None:
    if isinstance(value, chess.Move):
        return value
    if isinstance(value, str):
        try:
            return chess.Move.from_uci(value)
        except ValueError:
            return None
    return None


def _terminal_eval_cp(board: chess.Board, config: MistakeAnalyzerConfig) -> int:
    outcome = board.outcome()
    if outcome is None or outcome.winner is None:
        return 0
    return config.mate_score if outcome.winner == chess.WHITE else -config.mate_score


def _top_move_gap(
    top_moves: list[EngineMoveLine],
    side_to_move: chess.Color,
) -> int | None:
    if len(top_moves) < 2:
        return 0
    best = top_moves[0].eval_cp
    second = top_moves[1].eval_cp
    if best is None or second is None:
        return None
    if side_to_move == chess.WHITE:
        return max(0, best - second)
    return max(0, second - best)


def _eval_volatility(top_moves: list[EngineMoveLine]) -> float | None:
    evals = [move.eval_cp for move in top_moves if move.eval_cp is not None]
    if len(evals) < 2:
        return 0.0
    mean = sum(evals) / len(evals)
    variance = sum((value - mean) ** 2 for value in evals) / len(evals)
    return math.sqrt(variance)


def _is_stable_position(
    *,
    info: EngineRootAnalysis,
    retained_wp_loss: float | None,
    original_wp_loss: float,
    config: MistakeAnalyzerConfig,
) -> bool:
    if retained_wp_loss is None:
        return False
    retains_enough = retained_wp_loss >= config.retention_ratio * original_wp_loss
    volatility_stable = (
        info.eval_volatility_cp is not None
        and info.eval_volatility_cp <= config.stable_volatility_cp
    )
    top_gap_stable = (
        info.legal_move_count <= 1
        or (
            info.top_move_gap_cp is not None
            and info.top_move_gap_cp <= config.stable_top_gap_cp
        )
    )
    return retains_enough and volatility_stable and top_gap_stable


def _decision_difficulty(info: EngineRootAnalysis) -> float:
    if info.legal_move_count <= 1:
        return 0.0
    gap = min(1.0, max(0.0, float(info.top_move_gap_cp or 0)) / 300.0)
    volatility = min(1.0, max(0.0, float(info.eval_volatility_cp or 0.0)) / 300.0)
    return 0.6 * gap + 0.4 * volatility


def _engine_gain_against_user(
    *,
    before_user_eval: int | None,
    after_user_eval: int | None,
) -> int | None:
    if before_user_eval is None or after_user_eval is None:
        return None
    return before_user_eval - after_user_eval


def _retained_wp_loss(
    wp_before: float | None,
    current_wp: float | None,
) -> float | None:
    if wp_before is None or current_wp is None:
        return None
    return max(0.0, wp_before - current_wp)


def _move_cp_loss_for_user(move: EnrichedMove, target_color: str) -> int | None:
    if move.move_cp_loss is not None:
        return int(max(0, move.move_cp_loss))
    before = _orient_cp(move.eval_before_cp, target_color)
    after = _orient_cp(move.eval_after_cp, target_color)
    if before is None or after is None:
        return None
    return max(0, before - after)


def _move_wp_loss_for_user(
    move: EnrichedMove,
    target_color: str,
    rating: int,
) -> float | None:
    if move.win_prob_loss is not None:
        return max(0.0, move.win_prob_loss)
    before = _orient_cp(move.eval_before_cp, target_color)
    after = _orient_cp(move.eval_after_cp, target_color)
    if before is None or after is None:
        return None
    return max(
        0.0,
        default_cp_to_expected_points(before, rating)
        - default_cp_to_expected_points(after, rating),
    )


def _is_candidate_mistake(
    cp_loss: int | None,
    wp_loss: float | None,
    config: MistakeAnalyzerConfig,
) -> bool:
    return (
        (cp_loss is not None and cp_loss >= config.candidate_cp_loss)
        or (wp_loss is not None and wp_loss >= config.candidate_wp_loss)
    )


def _summary(
    *,
    games: list[EnrichedGame],
    target_moves_analyzed: int,
    mistakes: list[MistakeAnalysisItem],
) -> MistakesAnalysisSummary:
    severity_counts: dict[str, int] = {}
    theme_counts: dict[str, int] = {}
    for mistake in mistakes:
        severity_counts[mistake.severity] = severity_counts.get(mistake.severity, 0) + 1
        for tag in mistake.tactics:
            theme_counts[tag.theme] = theme_counts.get(tag.theme, 0) + 1
    depths = [mistake.theoretical_punishment_depth for mistake in mistakes]
    return MistakesAnalysisSummary(
        games_analyzed=len(games),
        target_moves_analyzed=target_moves_analyzed,
        mistake_count=len(mistakes),
        severity_counts=severity_counts,
        theme_counts=theme_counts,
        average_theoretical_punishment_depth=(
            sum(depths) / len(depths) if depths else None
        ),
        actual_punished_count=sum(1 for mistake in mistakes if mistake.actual_punished),
    )


def _target_color(game: EnrichedGame, username_key: str) -> str | None:
    if _username_key(game.white_username) == username_key:
        return "white"
    if _username_key(game.black_username) == username_key:
        return "black"
    return None


def _target_rating(
    game: EnrichedGame,
    target_color: str,
    config: MistakeAnalyzerConfig,
) -> int:
    rating = game.white_rating if target_color == "white" else game.black_rating
    return int(rating) if rating is not None else config.default_rating


def _orient_cp(cp: int | None, color_name: str) -> int | None:
    if cp is None:
        return None
    return cp if color_name == "white" else -cp


def _color_name(color: chess.Color) -> str:
    return "white" if color == chess.WHITE else "black"


def _username_key(username: str | None) -> str:
    return (username or "").strip().lower()


# ─── Public helper: on-demand position analysis ──────────────────────────────

def _build_line_from_pv(
    engine: Any,
    board: chess.Board,
    pv_uci: list[str],
    player_color: str,
    rating: int,
    config: MistakeAnalyzerConfig,
    analysis_cache: dict[str, EngineRootAnalysis],
    max_plies: int = 8,
) -> list[PunishmentLineMove]:
    """Replay a PV and build per-move PunishmentLineMove objects."""
    line: list[PunishmentLineMove] = []
    temp = board.copy(stack=False)
    tactic_config = TacticDetectorConfig(min_engine_gain_cp=config.tactic_min_engine_gain_cp)

    for ply_offset, uci in enumerate(pv_uci[:max_plies], start=1):
        if temp.is_game_over():
            break
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            break
        if move not in temp.legal_moves:
            break

        side_to_move = _color_name(temp.turn)
        fen_before = temp.fen()
        san = temp.san(move)

        pre_info = _analyse_position_cached(engine, temp, config, analysis_cache)
        user_eval_before = _orient_cp(pre_info.eval_cp, player_color)

        temp.push(move)
        fen_after = temp.fen()
        post_info = _analyse_position_cached(engine, temp, config, analysis_cache)
        user_eval_after = _orient_cp(post_info.eval_cp, player_color)
        user_wp = (
            default_cp_to_expected_points(user_eval_after, rating)
            if user_eval_after is not None
            else None
        )
        engine_gain_cp = _engine_gain_against_user(
            before_user_eval=user_eval_before,
            after_user_eval=user_eval_after,
        )
        tactics = detect_tactics(
            chess.Board(fen_before),
            move,
            ply_offset=ply_offset,
            engine_gain_cp=engine_gain_cp,
            mate_in=pre_info.mate_in,
            is_pv_move=True,
            config=tactic_config,
        )
        volatility_stable = (
            post_info.eval_volatility_cp is not None
            and post_info.eval_volatility_cp <= config.stable_volatility_cp
        )
        top_gap_stable = (
            post_info.legal_move_count <= 1
            or (
                post_info.top_move_gap_cp is not None
                and post_info.top_move_gap_cp <= config.stable_top_gap_cp
            )
        )
        line.append(
            PunishmentLineMove(
                ply_offset=ply_offset,
                side_to_move=side_to_move,
                move_uci=uci,
                san=san,
                fen_before=fen_before,
                fen_after=fen_after,
                eval_cp=post_info.eval_cp,
                user_eval_cp=user_eval_after,
                user_win_prob=user_wp,
                top_move_gap_cp=post_info.top_move_gap_cp,
                eval_volatility_cp=post_info.eval_volatility_cp,
                retained_wp_loss=None,
                stable_after_move=volatility_stable and top_gap_stable,
                tactics=tactics,
            )
        )

    return line


def analyse_position_lines(
    engine: Any,
    fen: str,
    player_color: str,
    rating: int,
    config: MistakeAnalyzerConfig | None = None,
    max_line_plies: int = 6,
) -> dict[str, Any]:
    """Compute top-3 engine lines + optimal continuation from a FEN.

    Returns:
        top_lines: list of dicts with rank, first_san, line_san, user_win_prob, etc.
        optimal_line: list of PunishmentLineMove (rank-1 PV, per-move analysis).
    """
    config = config or MistakeAnalyzerConfig()
    board = chess.Board(fen)
    analysis_cache: dict[str, EngineRootAnalysis] = {}

    root = _analyse_position_cached(engine, board, config, analysis_cache)

    top_lines: list[dict[str, Any]] = []
    for ml in root.top_moves:
        user_eval_cp = _orient_cp(ml.eval_cp, player_color)
        user_win_prob = (
            default_cp_to_expected_points(user_eval_cp, rating)
            if user_eval_cp is not None
            else None
        )
        line_san: list[str] = []
        temp = board.copy(stack=False)
        for uci in ml.line_uci[:max_line_plies]:
            try:
                m = chess.Move.from_uci(uci)
                if m not in temp.legal_moves:
                    break
                line_san.append(temp.san(m))
                temp.push(m)
            except (ValueError, AssertionError):
                break
        top_lines.append(
            {
                "rank": ml.rank,
                "first_uci": ml.move_uci,
                "first_san": line_san[0] if line_san else ml.move_uci,
                "line_san": line_san,
                "line_uci": ml.line_uci[:max_line_plies],
                "eval_cp": ml.eval_cp,
                "mate_in": ml.mate_in,
                "user_win_prob": user_win_prob,
                "user_eval_cp": user_eval_cp,
            }
        )

    rank1_pv = root.top_moves[0].line_uci if root.top_moves else []
    optimal_line = _build_line_from_pv(
        engine=engine,
        board=board,
        pv_uci=rank1_pv,
        player_color=player_color,
        rating=rating,
        config=config,
        analysis_cache=analysis_cache,
        max_plies=config.max_punishment_plies,
    )

    return {"top_lines": top_lines, "optimal_line": optimal_line}
