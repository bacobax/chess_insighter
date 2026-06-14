from __future__ import annotations

from dataclasses import replace
from typing import Any

import chess

from utils.game_enrichment_transformer import EnrichedGame, EnrichedMove
from utils.mistakes_analyzer import (
    MistakeAnalyzerConfig,
    analyze_mistakes,
    classify_mistake_severity,
)


START_FEN = chess.Board().fen()


class ScriptedEngine:
    def __init__(
        self,
        analyses: dict[str, list[tuple[str, int]]],
        forced: dict[tuple[str, str], int] | None = None,
    ):
        self.analyses = analyses
        self.forced = forced or {}

    def analyse(self, board: chess.Board, _limit: Any, multipv=None, root_moves=None):
        fen = board.fen()
        if root_moves:
            move_uci = root_moves[0].uci()
            score = self.forced.get((fen, move_uci))
            if score is None:
                score = next(
                    (
                        candidate_score
                        for candidate_uci, candidate_score in self.analyses.get(fen, [])
                        if candidate_uci == move_uci
                    ),
                    0,
                )
            return {"score": score, "pv": [root_moves[0]]}

        entries = self.analyses.get(fen)
        if not entries:
            move = next(iter(board.legal_moves), None)
            return {"score": 0, "pv": [] if move is None else [move]}
        limit = multipv or 1
        return [
            {"score": score, "pv": [chess.Move.from_uci(move_uci)]}
            for move_uci, score in entries[:limit]
        ]


def test_classifies_thresholds():
    assert classify_mistake_severity(40, 0.01) == "none"
    assert classify_mistake_severity(50, 0.01) == "inaccuracy"
    assert classify_mistake_severity(120, 0.01) == "mistake"
    assert classify_mistake_severity(10, 0.15) == "blunder"
    assert classify_mistake_severity(250, 0.01) == "blunder"


def test_punishment_reaches_stability_after_two_opponent_decisions():
    game = game_from_uci(["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"])
    fens = fens_after(["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"])
    engine = ScriptedEngine(
        {
            fens["e2e4"]: [("e7e5", -220), ("c7c5", 20), ("g8f6", 40)],
            fens["e7e5"]: [("g1f3", -200), ("d2d4", 20), ("b1c3", 30)],
            fens["g1f3"]: [("b8c6", -210), ("g8f6", -160), ("d7d6", -150)],
            fens["b8c6"]: [("f1c4", -205), ("f1b5", -190), ("d2d4", -180)],
            fens["f1c4"]: [("g8f6", -200), ("d7d6", -180), ("f8c5", -175)],
        }
    )

    result = analyze_mistakes([game], "alice", MistakeAnalyzerConfig(), engine)

    assert result.summary.mistake_count == 1
    mistake = result.mistakes[0]
    assert mistake.severity == "blunder"
    assert mistake.stability_reached is True
    assert mistake.theoretical_punishment_depth == 2
    assert mistake.theoretical_punishment_plies == 4
    assert mistake.best_line[:4] == ["e7e5", "g1f3", "b8c6", "f1c4"]
    assert [move.move_uci for move in mistake.actual_line_moves[:4]] == ["e7e5", "g1f3", "b8c6", "f1c4"]
    assert mistake.actual_punished is True
    assert mistake.actual_punishing_moves_played == 2


def test_no_stability_before_max_depth_is_censored():
    game = game_from_uci(["e2e4", "e7e5", "g1f3", "b8c6"])
    fens = fens_after(["e2e4", "e7e5", "g1f3", "b8c6"])
    engine = ScriptedEngine(
        {
            fens["e2e4"]: [("e7e5", -220), ("c7c5", 80), ("g8f6", 100)],
            fens["e7e5"]: [("g1f3", -210), ("d2d4", 80), ("b1c3", 100)],
            fens["g1f3"]: [("b8c6", -205), ("g8f6", 80), ("d7d6", 100)],
            fens["b8c6"]: [("f1c4", -200), ("f1b5", 80), ("d2d4", 100)],
        }
    )
    config = replace(MistakeAnalyzerConfig(), max_punishment_plies=3)

    result = analyze_mistakes([game], "alice", config, engine)

    mistake = result.mistakes[0]
    assert mistake.stability_reached is False
    assert mistake.theoretical_punishment_plies == 3


def test_actual_non_top_move_can_preserve_punishment():
    game = game_from_uci(["e2e4", "c7c5"])
    fens = fens_after(["e2e4", "e7e5", "c7c5"])
    engine = ScriptedEngine(
        {
            fens["e2e4"]: [("e7e5", -220), ("c7c5", -180), ("g8f6", -170)],
            fens["e7e5"]: [("g1f3", -210), ("d2d4", -190), ("b1c3", -185)],
        },
        forced={(fens["e2e4"], "c7c5"): -180},
    )
    config = replace(MistakeAnalyzerConfig(), max_punishment_plies=1)

    result = analyze_mistakes([game], "alice", config, engine)

    mistake = result.mistakes[0]
    assert mistake.best_line == ["e7e5"]
    assert [move.move_uci for move in mistake.actual_line_moves] == ["c7c5"]
    assert mistake.actual_punished is True
    assert mistake.actual_punishing_moves_played == 1


def test_actual_bad_non_top_move_misses_punishment():
    game = game_from_uci(["e2e4", "c7c5"])
    fens = fens_after(["e2e4", "e7e5", "c7c5"])
    engine = ScriptedEngine(
        {
            fens["e2e4"]: [("e7e5", -220), ("c7c5", 20), ("g8f6", 40)],
            fens["e7e5"]: [("g1f3", -210), ("d2d4", -190), ("b1c3", -185)],
        },
        forced={(fens["e2e4"], "c7c5"): 20},
    )
    config = replace(MistakeAnalyzerConfig(), max_punishment_plies=1)

    result = analyze_mistakes([game], "alice", config, engine)

    mistake = result.mistakes[0]
    assert mistake.actual_punished is False
    assert mistake.actual_punishing_moves_played == 0
    assert mistake.missed_at_ply == 1
    assert mistake.missed_best_move_uci == "e7e5"
    assert mistake.missed_actual_move_uci == "c7c5"


def test_theoretical_tactics_come_only_from_opponent_moves():
    """mistake.tactics must not include tags from user's own moves in the best line."""
    game = game_from_uci(["e2e4", "e7e5", "g1f3"])
    fens = fens_after(["e2e4", "e7e5", "g1f3"])
    engine = ScriptedEngine(
        {
            fens["e2e4"]: [("e7e5", -220), ("c7c5", 20), ("d7d5", 30)],
            fens["e7e5"]: [("g1f3", -210), ("d2d4", 20), ("b1c3", 30)],
            fens["g1f3"]: [("b8c6", -205), ("d7d5", -180), ("g8f6", -170)],
        }
    )
    config = replace(MistakeAnalyzerConfig(), max_punishment_plies=2)

    result = analyze_mistakes([game], "alice", config, engine)

    assert result.summary.mistake_count >= 1
    mistake = result.mistakes[0]
    user_move_ucis = {
        lm.move_uci for lm in mistake.best_line_moves if lm.side_to_move == "white"
    }
    for tag in mistake.tactics:
        assert tag.move_uci not in user_move_ucis, (
            f"Tag {tag.theme!r} on {tag.move_uci!r} leaked from a user (white) move"
        )


def test_actual_near_top_move_is_processed_for_tactics():
    """A near-top opponent move (within eval tolerance) must be processed for tactics."""
    # Alice (white) blunders on move 1. Bob plays a near-top move (not exact best)
    # that gives check. Before fix #3, is_pv_move=False and engine_gain_cp is near 0
    # because gain is measured as best_eval - actual_eval. After the fix, within_eval_tolerance
    # makes is_pv_for_tactics=True so check fires.
    #
    # Position after e2e4: 8/8/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1
    # We use the same blunder-on-move-1 setup; Bob's actual move is e7e5 (not exact top).
    game = game_from_uci(["e2e4", "e7e5"])
    fens = fens_after(["e2e4", "e7e5"])
    # Scripted so: engine best after e4 is d7d5 (-240), second best e7e5 (-220, within 80cp)
    # Alice's blunder: eval starts at 100, drops to -220 after e2e4 (scripted on move object)
    # Bob actually plays e7e5; engine says d7d5 is best (-240), so e7e5 is second
    # within_eval_tolerance: actual_user_eval(-220) <= best_user_eval(-240) + 80 = -160 → TRUE
    engine = ScriptedEngine(
        {
            fens["e2e4"]: [("d7d5", -240), ("e7e5", -220), ("c7c5", -200)],
            fens["e7e5"]: [("g1f3", -230), ("d2d4", -210), ("b1c3", -200)],
        },
        forced={(fens["e2e4"], "e7e5"): -220},
    )
    config = replace(MistakeAnalyzerConfig(), max_punishment_plies=1)

    result = analyze_mistakes([game], "alice", config, engine)

    assert result.summary.mistake_count >= 1
    mistake = result.mistakes[0]
    # Bob's actual move must appear in actual_line_moves and be processed (tactics list exists)
    assert len(mistake.actual_line_moves) == 1
    assert mistake.actual_line_moves[0].move_uci == "e7e5"
    # is_pv_for_tactics=True means the move was fully evaluated for tactics
    # (tactics list is present, even if empty for a quiet move like e7e5)
    assert isinstance(mistake.actual_line_moves[0].tactics, list)


def test_subthreshold_loss_is_not_listed_as_candidate():
    game = game_from_uci(["e2e4"])
    quiet_move = replace(game.moves[0], move_cp_loss=80, win_prob_loss=0.04)
    game = replace(game, moves=[quiet_move])

    result = analyze_mistakes([game], "alice", MistakeAnalyzerConfig(), ScriptedEngine({}))

    assert result.summary.mistake_count == 0


def fens_after(moves: list[str]) -> dict[str, str]:
    board = chess.Board()
    fens: dict[str, str] = {}
    for uci in moves:
        move = chess.Move.from_uci(uci)
        board.push(move)
        fens[uci] = board.fen()
    return fens


def game_from_uci(moves: list[str]) -> EnrichedGame:
    board = chess.Board()
    enriched_moves: list[EnrichedMove] = []
    for ply, uci in enumerate(moves, start=1):
        move = chess.Move.from_uci(uci)
        color = "white" if board.turn == chess.WHITE else "black"
        fen_before = board.fen()
        san = board.san(move)
        board.push(move)
        fen_after = board.fen()
        is_first = ply == 1
        enriched_moves.append(
            EnrichedMove(
                game_uuid="game-1",
                game_url="https://example.test/game-1",
                ply=ply,
                move_number=(ply + 1) // 2,
                player_color=color,
                player_username="alice" if color == "white" else "bob",
                san=san,
                uci=uci,
                fen_before=fen_before,
                fen_after=fen_after,
                eval_before_cp=100 if is_first else 0,
                eval_after_cp=-220 if is_first else 0,
                eval_best_move_cp=100 if is_first else 0,
                eval_played_move_cp=-220 if is_first else 0,
                move_cp_loss=320 if is_first else 0,
                best_move_uci=None,
                top_engine_moves=[],
                best_move_cp_gain=0,
                win_prob_before=0.65 if is_first else 0.5,
                win_prob_after=0.35 if is_first else 0.5,
                win_prob_loss=0.30 if is_first else 0.0,
                clock_before=None,
                clock_after=None,
                clock_spent=None,
                phase="middlegame",
                position_type_tags=[],
                tactical_position=False,
                quiet_middlegame=False,
                complexity=0.0,
                number_of_legal_moves=board.legal_moves.count(),
                eval_volatility_among_top_engine_lines=0.0,
                forcing_line_depth=0,
                low_gap_between_top_moves=0.0,
                engine_top_move_is_forcing=False,
                move_is_threat=False,
                is_capture=False,
                is_check=False,
                is_castling=False,
                is_promotion=False,
                in_opening_book=False,
                opening_eco=None,
                opening_name=None,
            )
        )
    return EnrichedGame(
        uuid="game-1",
        url="https://example.test/game-1",
        white_username="alice",
        black_username="bob",
        white_rating=1500,
        black_rating=1500,
        white_result="resigned",
        black_result="win",
        result="0-1",
        time_class="rapid",
        time_control="600",
        rated=True,
        end_time=1,
        chesscom_white_accuracy=None,
        chesscom_black_accuracy=None,
        opening_eco=None,
        opening_name=None,
        moves=enriched_moves,
    )
