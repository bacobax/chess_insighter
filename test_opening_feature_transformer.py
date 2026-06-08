from __future__ import annotations

import os
from pathlib import Path
import shutil
import unittest

import chess
import chess.engine

from utils.opening_feature_transformer import (
    FEATURE_START_PLY,
    MATCHER_COLUMNS_V2,
    OpeningLine,
    aggregate_by_normalized_name,
    aggregate_line_features,
    calibrate_opening_group_features,
    decode_distribution_csv,
    encode_distribution_csv,
    histogram_intersection,
    normalize_distribution,
    castling_opportunity_score,
    compute_line_features,
    compute_opening_groups,
    detect_castling_stats,
    doubled_pawns,
    endgame_likelihood_proxy,
    isolated_pawns,
    material_imbalance_score,
    match_lines_for_gt_row,
    open_files,
    opening_family_name,
    passed_pawns,
    sampled_position_pairs,
    semi_open_files,
    write_feature_distribution_diagnostics,
)


class FakeScore:
    def __init__(self, cp: int):
        self.cp = cp

    def white(self):
        return self

    def score(self, mate_score: int = 100_000):
        return self.cp


class FakeEngine:
    def analyse(self, board, limit, multipv=1, root_moves=None):
        legal = list(board.legal_moves)
        if not legal:
            return {"score": FakeScore(0), "pv": []}

        infos = []
        for index, move in enumerate(legal[:multipv]):
            cp = 30 - index * 25
            if board.turn == chess.BLACK:
                cp = -cp
            infos.append({"score": FakeScore(cp), "pv": [move]})
        return infos if multipv != 1 else infos[0]


def test_pawn_structure_helpers_detect_basic_features():
    board = chess.Board("8/8/8/2p5/2P1P3/2P5/8/4K2k w - - 0 1")

    assert isolated_pawns(board, chess.WHITE) == 3
    assert doubled_pawns(board, chess.WHITE) == 1
    assert passed_pawns(board, chess.WHITE) == 1
    assert open_files(board) == 6
    assert semi_open_files(board, chess.WHITE) == 0
    assert semi_open_files(board, chess.BLACK) == 1


def test_castling_stats_detect_early_and_opposite_side_castling():
    boards = []
    moves = []
    board = chess.Board()
    for uci in ["g1f3", "d7d5", "g2g3", "c8g4", "f1g2", "d8d7", "e1g1", "b8c6", "d2d4", "e8c8"]:
        move = chess.Move.from_uci(uci)
        boards.append(board.copy())
        moves.append(move)
        board.push(move)

    early, opposite, castled, sides = detect_castling_stats(boards, moves)

    assert early[chess.WHITE] == 1.0
    assert early[chess.BLACK] == 1.0
    assert opposite == 1.0
    assert castled[chess.WHITE] is True
    assert castled[chess.BLACK] is True
    assert sides[chess.WHITE] == "king"
    assert sides[chess.BLACK] == "queen"


def test_material_and_endgame_proxy_raise_after_queen_trade():
    board = chess.Board("8/8/8/8/8/8/4K3/4k3 w - - 0 1")

    assert material_imbalance_score(board) > 0.0
    assert endgame_likelihood_proxy(board, tactical_density=0.1, king_safety_risk=0.1, eval_volatility=10) > 0.5


def test_compute_line_features_with_fake_engine_and_aggregate():
    line = OpeningLine(
        eco="C20",
        name="King's Pawn Game",
        pgn="1. e4 e5 2. Nf3",
        uci="e2e4 e7e5 g1f3",
        epd="",
    )

    feature = compute_line_features(
        line,
        FakeEngine(),
        limit=chess.engine.Limit(depth=1),
        multipv=3,
        cache={},
    )
    group = aggregate_line_features([feature])

    assert group.opening_name == "King's Pawn Game"
    assert group.line_count == 1
    for value in group.vector():
        assert 0.0 <= value <= 1.0


def test_sampled_position_pairs_skips_common_early_plies_with_short_line_fallback():
    boards, _moves = [], []
    board = chess.Board()
    boards.append(board.copy())
    for uci in ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4"]:
        board.push(chess.Move.from_uci(uci))
        boards.append(board.copy())
    infos = [
        type("Info", (), {})()
        for _board in boards
    ]

    sampled = sampled_position_pairs(boards, infos)  # type: ignore[arg-type]
    short_sampled = sampled_position_pairs(boards[:3], infos[:3])  # type: ignore[arg-type]

    assert sampled[0][0].ply() >= FEATURE_START_PLY
    assert len(short_sampled) == 3


def test_short_line_retained_castling_rights_gets_nonzero_opportunity():
    line = OpeningLine(
        eco="C20",
        name="King's Pawn Game",
        pgn="1. e4 e5",
        uci="e2e4 e7e5",
        epd="",
    )

    feature = compute_line_features(
        line,
        FakeEngine(),
        limit=chess.engine.Limit(depth=1),
        multipv=3,
        cache={},
    )

    assert feature.early_castling_tendency > 0.0
    assert feature.king_safety_risk < 0.2


def test_explicit_castling_scores_higher_than_potential_only():
    potential_line = OpeningLine("C20", "King's Pawn Game", "1. e4 e5", "e2e4 e7e5", "")
    castled_line = OpeningLine(
        "C20",
        "King's Pawn Game",
        "1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. O-O",
        "e2e4 e7e5 g1f3 b8c6 f1c4 g8f6 e1g1",
        "",
    )

    potential_feature = compute_line_features(
        potential_line,
        FakeEngine(),
        limit=chess.engine.Limit(depth=1),
        multipv=3,
        cache={},
    )
    castled_feature = compute_line_features(
        castled_line,
        FakeEngine(),
        limit=chess.engine.Limit(depth=1),
        multipv=3,
        cache={},
    )

    assert castled_feature.early_castling_tendency > potential_feature.early_castling_tendency


def test_opposite_side_castling_potential_without_both_kings_castled():
    board = chess.Board()
    for uci in ["d2d4", "d7d5", "b1c3", "g8f6", "c1g5", "g7g6", "d1d2", "f8g7"]:
        board.push(chess.Move.from_uci(uci))
    boards = [board]

    white_side = castling_opportunity_score(board, chess.WHITE)
    black_side = castling_opportunity_score(board, chess.BLACK)
    early, opposite, _castled, _sides = detect_castling_stats(boards, [])

    assert white_side > 0.0
    assert black_side > 0.0
    assert early[chess.WHITE] > 0.0
    assert early[chess.BLACK] > 0.0
    assert opposite > 0.0


def test_material_imbalance_includes_equal_material_minor_piece_asymmetry():
    board = chess.Board("4k3/8/8/8/8/8/8/2BBK1nn w - - 0 1")

    assert material_imbalance_score(board) > 0.0


def test_family_aggregation_combines_variations_and_diversity():
    features = [
        _feature(
            "Sicilian Defense: Najdorf Variation",
            structure_signature="open-center",
        ),
        _feature(
            "Sicilian Defense: Dragon Variation",
            structure_signature="dragon-structure",
        ),
        _feature(
            "French Defense: Advance Variation",
            structure_signature="closed-center",
        ),
    ]

    groups = aggregate_by_normalized_name(features)
    by_name = {group.opening_name: group for group in groups}

    assert opening_family_name("Sicilian Defense: Najdorf Variation") == "Sicilian Defense"
    assert by_name["Sicilian Defense"].line_count == 2
    assert by_name["Sicilian Defense"].structure_diversity > 0.0
    assert by_name["Sicilian Defense"].final_structure_entropy == by_name["Sicilian Defense"].structure_diversity
    assert by_name["Sicilian Defense"].structure_distribution == {
        "open-center": 1,
        "dragon-structure": 1,
    }


def test_v2_vector_excludes_structure_diversity_and_distribution_csv_round_trips():
    group = aggregate_line_features(
        [
            _feature("A", tactical_density=1.0, structure_signature="isolani"),
            _feature("A", tactical_density=0.5, structure_signature="isolani"),
        ]
    )

    assert "structure_diversity" not in MATCHER_COLUMNS_V2
    assert len(group.vector_v2()) == len(MATCHER_COLUMNS_V2)
    assert len(group.vector()) == len(MATCHER_COLUMNS_V2) + 1
    assert decode_distribution_csv(encode_distribution_csv(group.structure_distribution)) == {"isolani": 2}
    assert histogram_intersection(
        normalize_distribution({"isolani": 2}),
        normalize_distribution({"isolani": 1, "hanging-pawns": 1}),
    ) == 0.5


def test_calibrate_opening_group_features_scales_matcher_columns_by_percentiles():
    groups = [
        aggregate_line_features([_feature("A", tactical_density=0.0, white_tactical_density=0.0)]),
        aggregate_line_features([_feature("B", tactical_density=0.5, white_tactical_density=0.5)]),
        aggregate_line_features([_feature("C", tactical_density=1.0, white_tactical_density=1.0)]),
    ]

    calibrated = calibrate_opening_group_features(groups)

    assert calibrated[0].tactical_density == 0.0
    assert calibrated[1].tactical_density == 0.5
    assert calibrated[2].tactical_density == 1.0
    assert calibrated[1].white_tactical_density == 0.5


def test_feature_distribution_diagnostics_writes_grouped_pngs(tmp_path):
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        return

    groups = [
        aggregate_line_features([_feature("A", tactical_density=0.0, white_tactical_density=0.0)]),
        aggregate_line_features([_feature("B", tactical_density=1.0, white_tactical_density=1.0)]),
    ]
    outputs = write_feature_distribution_diagnostics(groups, tmp_path)

    assert tmp_path.joinpath("generalized", "tactical_density.png").exists()
    assert tmp_path.joinpath("white", "tactical_density.png").exists()
    assert tmp_path.joinpath("black", "tactical_density.png").exists()
    assert len(outputs) == len(MATCHER_COLUMNS_V2) * 3


def test_gt_matching_uses_alias_and_eco_range():
    lines = [
        OpeningLine("C60", "Ruy Lopez", "", "e2e4 e7e5 g1f3 b8c6 f1b5", ""),
        OpeningLine("C45", "Scotch Game", "", "e2e4 e7e5 g1f3 b8c6 d2d4", ""),
        OpeningLine("B90", "Sicilian Defense: Najdorf Variation", "", "e2e4 c7c5", ""),
    ]

    matches = match_lines_for_gt_row(
        lines,
        {"opening_name": "Ruy Lopez / Spanish Opening", "eco": "C60-C99"},
    )

    assert [line.name for line in matches] == ["Ruy Lopez"]


def test_stockfish_smoke_when_available():
    stockfish = shutil.which("stockfish") or "/opt/homebrew/bin/stockfish"
    if shutil.which("stockfish") is None and not os.path.exists(stockfish):
        return

    groups, _ = compute_opening_groups(
        [
            OpeningLine(
                eco="C20",
                name="King's Pawn Game",
                pgn="1. e4 e5",
                uci="e2e4 e7e5",
                epd="",
            )
        ],
        stockfish_path=stockfish,
        engine_depth=1,
        max_lines_per_group=1,
        show_progress=False,
    )

    assert len(groups) == 1
    assert all(0.0 <= value <= 1.0 for value in groups[0].vector())


def _feature(name: str, **overrides):
    from utils.opening_feature_transformer import LineFeatureVector

    values = {
        "opening_name": name,
        "eco": "A00",
        "pgn": "",
        "uci": "",
        "tactical_density": 0.0,
        "quiet_position_density": 0.0,
        "king_safety_risk": 0.0,
        "early_castling_tendency": 0.0,
        "opposite_side_castling_tendency": 0.0,
        "middlegame_complexity": 0.0,
        "pawn_structure_sharpness": 0.0,
        "material_imbalance": 0.0,
        "endgame_likelihood_proxy": 0.0,
        "structure_signature": name,
    }
    values.update(overrides)
    return LineFeatureVector(**values)


class OpeningFeatureTransformerTests(unittest.TestCase):
    def test_pawn_structure_helpers_detect_basic_features(self):
        test_pawn_structure_helpers_detect_basic_features()

    def test_castling_stats_detect_early_and_opposite_side_castling(self):
        test_castling_stats_detect_early_and_opposite_side_castling()

    def test_material_and_endgame_proxy_raise_after_queen_trade(self):
        test_material_and_endgame_proxy_raise_after_queen_trade()

    def test_compute_line_features_with_fake_engine_and_aggregate(self):
        test_compute_line_features_with_fake_engine_and_aggregate()

    def test_sampled_position_pairs_skips_common_early_plies_with_short_line_fallback(self):
        test_sampled_position_pairs_skips_common_early_plies_with_short_line_fallback()

    def test_short_line_retained_castling_rights_gets_nonzero_opportunity(self):
        test_short_line_retained_castling_rights_gets_nonzero_opportunity()

    def test_explicit_castling_scores_higher_than_potential_only(self):
        test_explicit_castling_scores_higher_than_potential_only()

    def test_opposite_side_castling_potential_without_both_kings_castled(self):
        test_opposite_side_castling_potential_without_both_kings_castled()

    def test_material_imbalance_includes_equal_material_minor_piece_asymmetry(self):
        test_material_imbalance_includes_equal_material_minor_piece_asymmetry()

    def test_family_aggregation_combines_variations_and_diversity(self):
        test_family_aggregation_combines_variations_and_diversity()

    def test_gt_matching_uses_alias_and_eco_range(self):
        test_gt_matching_uses_alias_and_eco_range()

    def test_calibrate_opening_group_features_scales_matcher_columns_by_percentiles(self):
        test_calibrate_opening_group_features_scales_matcher_columns_by_percentiles()

    def test_feature_distribution_diagnostics_writes_grouped_pngs(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            test_feature_distribution_diagnostics_writes_grouped_pngs(Path(tmpdir))

    def test_stockfish_smoke_when_available(self):
        test_stockfish_smoke_when_available()
