from __future__ import annotations

from dataclasses import replace
from typing import Any

import chess

from utils.game_enrichment_transformer import EnrichedGame, EnrichedMove
from utils.mistakes_analyzer import (
    MistakeAnalyzerConfig,
    PunishmentLineMove,
    _annotate_line_tactics,
    analyze_mistakes,
    classify_mistake_severity,
)
from utils.tactic_detector import detect_tactics


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


def test_line_tactics_suppress_plain_check_when_richer_check_theme_exists():
    line = tactic_line(
        "4k3/8/8/8/8/8/4B3/K3R3 w - - 0 1",
        ["e2b5"],
    )

    annotated = _annotate_line_tactics(line, "white")
    found = {tag.theme for tag in annotated[0].tactics}

    assert "double_check" in found
    assert "discovered_check" in found
    assert "check" not in found


def test_line_tactics_drop_plain_check_and_strip_user_tactics():
    opponent_check = _annotate_line_tactics(
        tactic_line("4k3/8/8/8/8/8/4Q3/4K3 w - - 0 1", ["e2e7"]),
        "white",
    )
    user_check = _annotate_line_tactics(
        tactic_line(
            "7k/8/8/8/8/8/4q3/K7 w - - 0 1",
            ["a1b1", "e2e1", "b1a2"],
        ),
        "white",
    )
    legacy_king_attraction = _annotate_line_tactics(
        tactic_line("6k1/8/8/8/8/8/5Q2/6K1 w - - 0 1", ["f2f7"]),
        "white",
    )

    assert opponent_check[0].tactics == []
    assert user_check[1].tactics == []
    assert "king_attraction" not in {
        tag.theme for tag in legacy_king_attraction[0].tactics
    }


def test_profitable_material_tactics_stay_on_validated_setup_move():
    cases = [
        (
            "fork",
            "5q2/4k3/8/4N3/8/8/8/K7 w - - 0 1",
            ["e5g6", "e7d6", "g6f8", "d6e5"],
        ),
        (
            "absolute_pin",
            "4k3/p3n3/8/8/8/8/8/R6K w - - 0 1",
            ["a1e1", "a7a6", "e1e7", "e8f8"],
        ),
        (
            "skewer",
            "4q3/4k3/8/8/8/8/8/R6K w - - 0 1",
            ["a1e1", "e7f6", "e1e8", "f6f7"],
        ),
    ]

    for theme, fen, moves in cases:
        annotated = _annotate_line_tactics(tactic_line(fen, moves), "white")
        assert theme in {tag.theme for tag in annotated[0].tactics}
        assert theme not in {tag.theme for tag in annotated[2].tactics}
        tag = next(tag for tag in annotated[0].tactics if tag.theme == theme)
        assert tag.move_uci == moves[0]
        assert tag.evidence["setup_move_uci"] == moves[0]
        assert tag.evidence["payoff_move_uci"] == moves[2]

    checking_fork_setup = _annotate_line_tactics(
        tactic_line(cases[0][1], cases[0][2]),
        "white",
    )[0]
    assert "check" not in {tag.theme for tag in checking_fork_setup.tactics}


def test_checking_fork_does_not_require_visible_payoff():
    annotated = _annotate_line_tactics(
        tactic_line(
            "r6r/pp1k2B1/8/3b1R1p/4B3/8/P2q2PP/R5K1 b - - 0 1",
            ["d2e3"],
        ),
        "black",
    )

    assert {tag.theme for tag in annotated[0].tactics} == {"fork"}
    fork = annotated[0].tactics[0]
    assert {target["square"] for target in fork.evidence["targets"]} == {
        "e4",
        "g1",
    }


def test_unprofitable_or_unanswered_skewer_is_not_emitted():
    losing_queen = _annotate_line_tactics(
        tactic_line(
            "4r3/4k3/8/8/8/8/8/Q6K w - - 0 1",
            ["a1e1", "e7f7", "e1e8", "f7e8"],
        ),
        "white",
    )
    truncated = _annotate_line_tactics(
        tactic_line(
            "4q3/4k3/8/8/8/8/8/R6K w - - 0 1",
            ["a1e1", "e7f6", "e1e8"],
        ),
        "white",
    )

    assert all(tag.theme != "skewer" for step in losing_queen for tag in step.tactics)
    assert all(tag.theme != "skewer" for step in truncated for tag in step.tactics)


def test_skewer_and_deflection_stay_on_ranking_setup_not_later_check():
    annotated = _annotate_line_tactics(
        tactic_line(
            "Q7/p1pk4/7p/6p1/8/6P1/1r1q2PP/5R1K w - - 1 42",
            [
                "f1f7",
                "d7e6",
                "a8e8",
                "e6d5",
                "e8d8",
                "d5c4",
                "f7c7",
                "c4b3",
            ],
        ),
        "white",
    )

    assert {tag.theme for tag in annotated[0].tactics} == {
        "skewer",
        "defender_deflection",
    }
    assert annotated[6].tactics == []
    assert all(tag.move_uci == "f1f7" for tag in annotated[0].tactics)
    assert all(tag.evidence["payoff_move_uci"] == "f7c7" for tag in annotated[0].tactics)


def test_defender_deflection_requires_profitable_future_capture():
    cases = [
        (
            "captured",
            "7k/8/4q3/2Nr4/8/8/8/3R3K w - - 0 1",
            ["c5e6", "h8h7", "d1d5", "h7h6"],
        ),
        (
            "attacked_away",
            "7k/8/4q3/3r4/8/7N/8/3R3K w - - 0 1",
            ["h3f4", "e6e7", "d1d5", "h8h7"],
        ),
        (
            "checked_away",
            "2N3k1/p4r2/8/8/8/8/8/5R1K w - - 0 1",
            ["c8e7", "g8h8", "f1f7", "a7a6"],
        ),
        (
            "lured",
            "7k/8/4q3/3r3N/8/8/8/3R3K w - - 0 1",
            ["h5f6", "e6f6", "d1d5", "h8g7"],
        ),
    ]

    for removal, fen, moves in cases:
        annotated = _annotate_line_tactics(tactic_line(fen, moves), "white")
        tag = next(
            tag for tag in annotated[0].tactics if tag.theme == "defender_deflection"
        )
        assert all(tag.theme != "defender_deflection" for tag in annotated[2].tactics)
        assert tag.evidence["removal"] == removal
        assert tag.evidence["setup_move_uci"] == moves[0]
        assert tag.evidence["payoff_move_uci"] == moves[2]


def test_defender_deflection_is_not_emitted_without_payoff():
    annotated = _annotate_line_tactics(
        tactic_line(
            "7k/8/4q3/3r4/8/7N/8/3R3K w - - 0 1",
            ["h3f4", "e6e7", "h1g1", "h8h7"],
        ),
        "white",
    )

    assert all(tag.theme != "defender_deflection" for step in annotated for tag in step.tactics)


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


def tactic_line(fen: str, moves: list[str]) -> list[PunishmentLineMove]:
    board = chess.Board(fen)
    result: list[PunishmentLineMove] = []
    for ply_offset, uci in enumerate(moves, start=1):
        move = chess.Move.from_uci(uci)
        assert move in board.legal_moves, f"illegal fixture move {uci} in {board.fen()}"
        fen_before = board.fen()
        side_to_move = "white" if board.turn == chess.WHITE else "black"
        san = board.san(move)
        raw_tactics = detect_tactics(
            board,
            move,
            ply_offset=ply_offset,
            engine_gain_cp=500,
            is_pv_move=True,
        )
        board.push(move)
        result.append(
            PunishmentLineMove(
                ply_offset=ply_offset,
                side_to_move=side_to_move,
                move_uci=uci,
                san=san,
                fen_before=fen_before,
                fen_after=board.fen(),
                eval_cp=None,
                user_eval_cp=None,
                user_win_prob=None,
                top_move_gap_cp=None,
                eval_volatility_cp=None,
                retained_wp_loss=None,
                stable_after_move=False,
                tactics=raw_tactics,
            )
        )
    return result


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
