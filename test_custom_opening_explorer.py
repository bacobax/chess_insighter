from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

import chess
import numpy as np

import utils.custom_opening_explorer as explorer
from utils.custom_opening_explorer import (
    ExplorerConfig,
    cp_to_utility,
    minimax,
    open_engine,
    parse_user_move,
)
from utils.opening_repository import OpeningRepository
from utils.position_feature_extractor import FEATURES, extract_position_vector


def config(target_color=chess.WHITE, no_engine=True):
    return ExplorerConfig(
        target_color=target_color,
        max_depth=1,
        top_k=3,
        engine_path="/definitely/missing/stockfish",
        engine_depth=1,
        no_engine=no_engine,
        max_candidate_moves=None,
        opening_book=None,
        show_progress=False,
        style_weight=1.0,
        cp_weight=0.0,
    )


def test_parse_user_move_accepts_san_and_uci_and_rejects_illegal():
    board = chess.Board()

    assert parse_user_move(board, "e4") == chess.Move.from_uci("e2e4")
    assert parse_user_move(board, "g1f3") == chess.Move.from_uci("g1f3")
    assert parse_user_move(board, "e2e5") is None


def test_minimax_minimizes_on_opponent_node():
    original = explorer.extract_position_vector

    def fake_vector(board, target_color, engine, feature_names, engine_depth=1, engine_cache=None):
        black_king = board.king(chess.BLACK)
        values = {chess.H2: 0.1, chess.G2: 0.5, chess.H1: 0.9}
        value = values.get(black_king, 0.0)
        return np.array([value, 1.0 - value])

    explorer.extract_position_vector = fake_vector
    try:
        board = chess.Board("8/8/8/8/8/8/P3K3/6k1 b - - 0 1")
        score, line = minimax(
            board,
            depth=1,
            alpha=float("-inf"),
            beta=float("inf"),
            maximizing=False,
            target_color=chess.WHITE,
            player_vector=np.array([1.0, 0.0]),
            config=config(chess.WHITE),
            cache={},
        )

        assert round(score, 6) == round(0.1 / (0.1**2 + 0.9**2) ** 0.5, 6)
        assert board.san(line[0]) == "Kh2"
    finally:
        explorer.extract_position_vector = original


def test_minimax_maximizes_on_target_node():
    original = explorer.extract_position_vector

    def fake_vector(board, target_color, engine, feature_names, engine_depth=1, engine_cache=None):
        black_king = board.king(chess.BLACK)
        values = {chess.H2: 0.1, chess.G2: 0.5, chess.H1: 0.9}
        value = values.get(black_king, 0.0)
        return np.array([value, 1.0 - value])

    explorer.extract_position_vector = fake_vector
    try:
        board = chess.Board("8/8/8/8/8/8/P3K3/6k1 b - - 0 1")
        score, line = minimax(
            board,
            depth=1,
            alpha=float("-inf"),
            beta=float("inf"),
            maximizing=True,
            target_color=chess.BLACK,
            player_vector=np.array([1.0, 0.0]),
            config=config(chess.BLACK),
            cache={},
        )

        assert round(score, 6) == round(0.9 / (0.9**2 + 0.1**2) ** 0.5, 6)
        assert board.san(line[0]) == "Kh1"
    finally:
        explorer.extract_position_vector = original


def test_position_vector_has_expected_order_and_normalized_values():
    board = chess.Board()
    vector = extract_position_vector(board, chess.WHITE, None, list(FEATURES), engine_depth=1)

    assert len(vector) == len(FEATURES)
    assert all(0.0 <= value <= 1.0 for value in vector)


def test_opening_repository_detects_position_from_temp_book():
    with tempfile.TemporaryDirectory() as tmp:
        board = chess.Board()
        board.push(chess.Move.from_uci("e2e4"))
        path = Path(tmp) / "book.tsv"
        path.write_text(
            "eco\tname\tpgn\tuci\tepd\n"
            f"C20\tKing's Pawn Game\t1. e4\te2e4\t{board.epd()}\n",
            encoding="utf-8",
        )
        repo = OpeningRepository(path)

        assert repo.get_by_board(board).name == "King's Pawn Game"


def test_open_engine_falls_back_when_path_missing():
    assert open_engine(config(no_engine=False)) is None


def test_cp_to_utility_normalizes_target_eval():
    assert cp_to_utility(0, 600) == 0.5
    assert cp_to_utility(600, 600) > 0.5
    assert cp_to_utility(-600, 600) < 0.5


def test_cp_weight_can_drive_leaf_utility():
    board = chess.Board("8/8/8/8/8/8/P3K3/6k1 b - - 0 1")
    cp_config = ExplorerConfig(
        target_color=chess.WHITE,
        max_depth=1,
        top_k=3,
        engine_path=None,
        engine_depth=1,
        no_engine=True,
        max_candidate_moves=None,
        opening_book=None,
        show_progress=False,
        style_weight=0.0,
        cp_weight=1.0,
    )

    score, _line = minimax(
        board,
        depth=0,
        alpha=float("-inf"),
        beta=float("inf"),
        maximizing=True,
        target_color=chess.WHITE,
        player_vector=np.array([0.0, 0.0]),
        config=cp_config,
        cache={},
    )

    assert score > 0.5


class CustomOpeningExplorerTests(unittest.TestCase):
    def test_parse_user_move_accepts_san_and_uci_and_rejects_illegal(self):
        test_parse_user_move_accepts_san_and_uci_and_rejects_illegal()

    def test_minimax_minimizes_on_opponent_node(self):
        test_minimax_minimizes_on_opponent_node()

    def test_minimax_maximizes_on_target_node(self):
        test_minimax_maximizes_on_target_node()

    def test_position_vector_has_expected_order_and_normalized_values(self):
        test_position_vector_has_expected_order_and_normalized_values()

    def test_opening_repository_detects_position_from_temp_book(self):
        test_opening_repository_detects_position_from_temp_book()

    def test_open_engine_falls_back_when_path_missing(self):
        test_open_engine_falls_back_when_path_missing()

    def test_cp_to_utility_normalizes_target_eval(self):
        test_cp_to_utility_normalizes_target_eval()

    def test_cp_weight_can_drive_leaf_utility(self):
        test_cp_weight_can_drive_leaf_utility()
