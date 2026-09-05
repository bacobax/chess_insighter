from __future__ import annotations

import chess

from utils.tactic_detector import detect_tactics


def themes(fen: str, uci: str, **kwargs) -> set[str]:
    board = chess.Board(fen)
    move = chess.Move.from_uci(uci)
    return {tag.theme for tag in detect_tactics(board, move, **kwargs)}


def test_does_not_emit_plain_check():
    found = themes(
        "4k3/8/8/8/8/8/4Q3/4K3 w - - 0 1",
        "e2e7",
    )

    assert "check" not in found


def test_detects_double_check_and_discovered_check():
    found = themes(
        "4k3/8/8/8/8/8/4B3/K3R3 w - - 0 1",
        "e2b5",
        is_pv_move=True,
    )

    assert "double_check" in found
    assert "discovered_check" in found


def test_detects_knight_fork_when_engine_relevant():
    found = themes(
        "5q2/4k3/8/4N3/8/8/8/K7 w - - 0 1",
        "e5g6",
        engine_gain_cp=120,
    )

    assert "fork" in found


def test_detects_absolute_pin_created_by_slider():
    found = themes(
        "4k3/4n3/8/8/8/8/8/R6K w - - 0 1",
        "a1e1",
        is_pv_move=True,
    )

    assert "absolute_pin" in found


def test_detects_skewer_created_by_slider():
    found = themes(
        "4q3/4k3/8/8/8/8/8/R6K w - - 0 1",
        "a1e1",
        is_pv_move=True,
    )

    assert "skewer" in found


def test_detects_checkmate_in_k_from_engine_signal():
    found = themes(
        chess.STARTING_FEN,
        "e2e4",
        mate_in=3,
    )

    assert "checkmate_in_k" in found


def test_detects_king_attraction_when_engine_validated():
    found = themes(
        "6k1/8/8/8/8/8/5Q2/6K1 w - - 0 1",
        "f2f7",
        engine_gain_cp=300,
    )

    assert "king_attraction" in found


def test_non_pv_low_value_geometry_does_not_emit_fork():
    found = themes(
        "5q2/4k3/8/4N3/8/8/8/K7 w - - 0 1",
        "e5g6",
        engine_gain_cp=0,
        is_pv_move=False,
    )

    assert "check" not in found
    assert "fork" not in found


def test_skewer_on_checkmate_suppressed():
    # Qxa8# — queen captures on a8 delivering checkmate along rank 8 (king on g8
    # has no escape, all flight squares covered by queen + own pawns). Same rank-8
    # ray continues through king (g8) to the black queen on h8: a textbook skewer,
    # but the game is over so it must not fire.
    found = themes(
        "r5kq/5ppp/8/8/8/8/6Q1/7K w - - 0 1",
        "g2a8",
        is_pv_move=True,
    )

    assert "checkmate_in_k" in found
    assert "skewer" not in found


def test_fork_on_checkmate_suppressed():
    # Nf7# — smothered mate. Knight on h6 moves to f7, checkmating the king on h8
    # (all flight squares blocked by own rook/pawns). The knight simultaneously
    # attacks the black queen on d8: a fork, but meaningless since the game ends.
    found = themes(
        "3q2rk/6pp/7N/8/8/8/8/7K w - - 0 1",
        "h6f7",
        is_pv_move=True,
    )

    assert "checkmate_in_k" in found
    assert "fork" not in found


def test_material_tactics_fire_when_not_checkmate():
    skewer_found = themes(
        "4q3/4k3/8/8/8/8/8/R6K w - - 0 1",
        "a1e1",
        is_pv_move=True,
    )
    assert "skewer" in skewer_found

    fork_found = themes(
        "5q2/4k3/8/4N3/8/8/8/K7 w - - 0 1",
        "e5g6",
        engine_gain_cp=120,
    )
    assert "fork" in fork_found
