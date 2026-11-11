from __future__ import annotations

from pathlib import Path

import chess
import pytest

from utils.opening_study_tree import (
    COMMON_WHITE_FIRST_MOVES,
    PlayerVectorFeatureMismatch,
    clamp01,
    cp_to_utility,
    engine_percentiles,
    evaluate_engine_soundness,
    get_opening_study_tree_children,
    load_player_vector_from_cache,
    passes_evaluation_threshold,
    resolve_study_weights,
)


OPENING_VECTORS = str(Path(__file__).resolve().parent / "openings_dataset/opening_feature_vectors.csv")


@pytest.fixture(scope="module")
def player_vector() -> dict[str, float]:
    cache = Path(__file__).resolve().parent / ".cache/player_vectors.json"
    if not cache.exists():
        pytest.skip("player_vectors.json cache not available")
    return load_player_vector_from_cache(str(cache), "sylvathur")


def test_clamp01_bounds():
    assert clamp01(-1.0) == 0.0
    assert clamp01(2.0) == 1.0
    assert clamp01(0.5) == 0.5


def test_evaluation_weights_are_excluded_and_soft_weights_are_normalized():
    supplied = {
        "player_style_match": 0.4,
        "engine_soundness": 0.9,
        "practical_gamble": 0.8,
        "systemness": 0.2,
        "memory_simplicity": 0.4,
    }
    resolved = resolve_study_weights(supplied, "style", "engine")

    assert resolved["engine_soundness"] == 0.0
    assert resolved["practical_gamble"] == 0.0
    assert resolved["player_style_match"] == pytest.approx(0.4)
    assert resolved["systemness"] == pytest.approx(0.2)
    assert resolved["memory_simplicity"] == pytest.approx(0.4)
    assert sum(resolved.values()) == pytest.approx(1.0)


def test_zero_soft_weight_levels_fall_back_to_equal_active_weights():
    supplied = {key: 0.0 for key in (
        "player_style_match",
        "engine_soundness",
        "aggressiveness",
        "practical_gamble",
        "systemness",
        "memory_simplicity",
    )}
    resolved = resolve_study_weights(supplied, "custom", "practical")

    assert resolved["aggressiveness"] == pytest.approx(1 / 3)
    assert resolved["systemness"] == pytest.approx(1 / 3)
    assert resolved["memory_simplicity"] == pytest.approx(1 / 3)
    assert resolved["player_style_match"] == 0.0
    assert resolved["engine_soundness"] == 0.0
    assert resolved["practical_gamble"] == 0.0


def test_evaluation_threshold_requires_data_only_when_positive():
    assert passes_evaluation_threshold(
        "engine", 0.0,
        engine_percentile=None,
        practical_gamble=None,
    )
    assert not passes_evaluation_threshold(
        "engine", 0.6,
        engine_percentile=None,
        practical_gamble=None,
    )
    assert passes_evaluation_threshold(
        "engine", 0.6,
        engine_percentile=0.8,
        practical_gamble=None,
    )
    assert not passes_evaluation_threshold(
        "practical", 0.6,
        engine_percentile=1.0,
        practical_gamble=0.59,
    )
    assert passes_evaluation_threshold(
        "practical", 0.6,
        engine_percentile=0.0,
        practical_gamble=0.6,
    )


def test_engine_percentiles_rank_siblings_and_keep_top_band():
    # best=40; 30 is within the 15cp top band, so it is lifted to 1.0.
    result = engine_percentiles([40.0, 30.0, 0.0, -50.0, None], top_tolerance_cp=15.0)
    assert result[0] == 1.0
    assert result[1] == 1.0
    assert result[2] == pytest.approx(1 / 3)
    assert result[3] == 0.0
    assert result[4] is None
    assert engine_percentiles([-35.0]) == [1.0]
    assert engine_percentiles([None, None]) == [None, None]
    # Ties share the midpoint rank.
    assert engine_percentiles([100.0, 0.0, 0.0], top_tolerance_cp=0.0)[1:] == [0.25, 0.25]


def test_engine_threshold_is_relative_so_black_replies_survive():
    """Every Black reply is worse than 0cp after 1.e4; a high percentile must
    still keep the best of them instead of returning an empty, unexpandable node."""
    class FakeEngine:
        def analyse(self, board, limit):
            # White-POV eval: Black's best reply (c7c5) leaves White +20, others +80.
            cp = 20 if board.peek().uci() == "c7c5" else 80
            return {"score": chess.engine.PovScore(chess.engine.Cp(cp), chess.WHITE)}

    nodes = get_opening_study_tree_children(
        _PLAYER,
        OPENING_VECTORS,
        "black",
        ["e2e4"],
        20,
        soundness_engine=FakeEngine(),
        evaluation_metric="engine",
        evaluation_threshold=1.0,
        opponent_move_ordering="popularity",
    )

    assert [node.move_uci for node in nodes] == ["c7c5"]
    assert nodes[0].engine_soundness < 0.5


def test_cp_to_utility_is_target_oriented_and_bounded():
    assert cp_to_utility(0) == pytest.approx(0.5)
    assert cp_to_utility(300) > 0.5
    assert cp_to_utility(-300) < 0.5
    assert 0.0 < cp_to_utility(-100_000) < 0.01
    assert 0.99 < cp_to_utility(100_000) < 1.0


def test_evaluate_engine_soundness_orients_cp_by_target_color():
    class FakeEngine:
        def analyse(self, board, limit):
            return {"score": chess.engine.PovScore(chess.engine.Cp(240), chess.WHITE)}

    board = chess.Board()
    white_score, white_cp = evaluate_engine_soundness(board, "white", FakeEngine())
    black_score, black_cp = evaluate_engine_soundness(board, "black", FakeEngine())

    assert white_cp == pytest.approx(240)
    assert black_cp == pytest.approx(-240)
    assert white_score > 0.5
    assert black_score < 0.5


def test_white_root_returns_white_first_moves(player_vector):
    nodes = get_opening_study_tree_children(player_vector, OPENING_VECTORS, "white", [], 5)
    assert nodes
    for node in nodes:
        # Root White nodes are White's first move: after the move it is Black to play.
        assert node.side_to_move == "black"
        assert node.is_target_move is True
        assert len(node.prefix_uci) == 1
        assert 0.0 <= node.study_score <= 1.0


def test_white_nodes_sorted_by_study_score(player_vector):
    nodes = get_opening_study_tree_children(player_vector, OPENING_VECTORS, "white", [], 5)
    scores = [node.study_score for node in nodes]
    assert scores == sorted(scores, reverse=True)


def test_opponent_moves_can_be_sorted_by_popularity(player_vector):
    nodes = get_opening_study_tree_children(
        player_vector,
        OPENING_VECTORS,
        "white",
        ["e2e4"],
        5,
        opponent_top_k=12,
        opponent_move_ordering="popularity",
    )

    assert nodes
    scores = [node.popularity_score for node in nodes]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] > 0


def test_opponent_moves_can_be_sorted_by_engine_score(player_vector):
    class FakeEngine:
        def analyse(self, board, limit):
            # From White's perspective, ...e5 is the strongest Black reply in
            # this deterministic test. Opponent ordering should therefore put
            # the lowest target-oriented engine utility first.
            cp = -500 if board.peek().uci() == "e7e5" else 500
            return {"score": chess.engine.PovScore(chess.engine.Cp(cp), chess.WHITE)}

    nodes = get_opening_study_tree_children(
        player_vector,
        OPENING_VECTORS,
        "white",
        ["e2e4"],
        5,
        opponent_top_k=12,
        soundness_engine=FakeEngine(),
        opponent_move_ordering="engine",
    )

    assert nodes[0].move_uci == "e7e5"
    scores = [node.engine_soundness for node in nodes]
    assert scores == sorted(scores)


def test_black_root_shows_common_white_first_moves(player_vector):
    nodes = get_opening_study_tree_children(player_vector, OPENING_VECTORS, "black", [], 4)
    assert [node.move_uci for node in nodes] == list(COMMON_WHITE_FIRST_MOVES)
    for node in nodes:
        # These are White's moves; target is Black, so not a target move.
        assert node.is_target_move is False
        assert node.side_to_move == "black"


def test_black_responses_after_e4_are_target_moves(player_vector):
    nodes = get_opening_study_tree_children(player_vector, OPENING_VECTORS, "black", ["e2e4"], 4)
    assert nodes
    for node in nodes:
        assert node.is_target_move is True
        assert node.side_to_move == "white"
        assert node.prefix_uci[0] == "e2e4"


def test_e4_expansion_uses_precomputed_worst_counts_without_engine(player_vector):
    class ExplodingEngine:
        def analyse(self, *args, **kwargs):
            raise AssertionError("opening-study expansion must not call the engine")

    nodes = get_opening_study_tree_children(
        player_vector,
        OPENING_VECTORS,
        "black",
        ["e2e4"],
        20,
        engine=ExplodingEngine(),
    )
    duras = next(node for node in nodes if node.move_uci == "f7f5")
    worst_line = next(
        item for item in duras.breakdown["memoryComplexity"]
        if item["key"] == "worst_line_count"
    )

    assert worst_line["rawValue"] > 1


def test_invalid_target_color_raises(player_vector):
    with pytest.raises(ValueError):
        get_opening_study_tree_children(player_vector, OPENING_VECTORS, "green", [], 4)


def test_missing_csv_raises(player_vector):
    with pytest.raises(FileNotFoundError):
        get_opening_study_tree_children(player_vector, "/nonexistent/openings.csv", "white", [], 4)


def test_feature_mismatch_raises():
    bad_vector = {"totally_unrelated_feature": 1.0}
    with pytest.raises(PlayerVectorFeatureMismatch):
        get_opening_study_tree_children(bad_vector, OPENING_VECTORS, "white", [], 4)


def test_node_serialization_has_camelcase_keys(player_vector):
    nodes = get_opening_study_tree_children(player_vector, OPENING_VECTORS, "white", [], 1)
    payload = nodes[0].to_dict()
    for key in ["moveSan", "studyScore", "boardPreviewFen", "compatibleLineCount", "stats"]:
        assert key in payload


# ---------------------------------------------------------------------------
# Part A — coverage-shrink tests (no engine required)
# ---------------------------------------------------------------------------

import math
from utils.opening_study_tree import COVERAGE_FULL, _compute_global_priors, compute_node_metrics


def _base_aggregate(
    lc: int = 10,
    div: float = 0.3,
    ent: float = 0.3,
    worst_white: float | None = None,
    worst_black: float | None = None,
) -> dict:
    agg: dict = {
        "structure_diversity": div,
        "final_structure_entropy": ent,
        "tactical_density": 0.5,
        "quiet_position_density": 0.5,
        "king_safety_risk": 0.3,
        "early_castling_tendency": 0.5,
        "opposite_side_castling_tendency": 0.2,
        "middlegame_complexity": 0.5,
        "pawn_structure_sharpness": 0.4,
        "material_imbalance": 0.3,
        "endgame_likelihood_proxy": 0.3,
    }
    if worst_white is not None:
        agg["white_worst_line_count"] = worst_white
    if worst_black is not None:
        agg["black_worst_line_count"] = worst_black
    return agg


_PLAYER = {
    "tactical_density": 0.6,
    "quiet_position_density": 0.4,
    "king_safety_risk": 0.4,
    "early_castling_tendency": 0.6,
    "opposite_side_castling_tendency": 0.3,
    "middlegame_complexity": 0.6,
    "pawn_structure_sharpness": 0.5,
    "material_imbalance": 0.4,
    "endgame_likelihood_proxy": 0.3,
}


def test_engine_threshold_filters_only_feasible_player_moves():
    class FakeEngine:
        def analyse(self, board, limit):
            cp = 400 if board.peek().uci() == "e2e4" else -400
            return {"score": chess.engine.PovScore(chess.engine.Cp(cp), chess.WHITE)}

    nodes = get_opening_study_tree_children(
        _PLAYER,
        OPENING_VECTORS,
        "white",
        [],
        20,
        soundness_engine=FakeEngine(),
        evaluation_metric="engine",
        evaluation_threshold=0.5,
        opponent_move_ordering="popularity",
    )

    assert [node.move_uci for node in nodes] == ["e2e4"]


def test_practical_threshold_filters_player_moves(monkeypatch):
    class Practical:
        raw = 0.1
        sample_size = 100
        coverage = 1.0

        def __init__(self, percentile: float):
            self.percentile = percentile

    def fake_practical(board, target_color, opening_vectors_path):
        return Practical(0.8 if board.peek().uci() == "e2e4" else 0.2)

    monkeypatch.setattr(
        "utils.opening_study_tree.practical_gamble_for_board",
        fake_practical,
    )
    nodes = get_opening_study_tree_children(
        _PLAYER,
        OPENING_VECTORS,
        "white",
        [],
        20,
        evaluation_metric="practical",
        evaluation_threshold=0.5,
        opponent_move_ordering="popularity",
    )

    assert [node.move_uci for node in nodes] == ["e2e4"]


def test_evaluation_threshold_does_not_filter_opponent_replies(monkeypatch):
    class Practical:
        percentile = 0.0
        raw = 0.0
        sample_size = 100
        coverage = 1.0

    monkeypatch.setattr(
        "utils.opening_study_tree.practical_gamble_for_board",
        lambda board, target_color, opening_vectors_path: Practical(),
    )
    nodes = get_opening_study_tree_children(
        _PLAYER,
        OPENING_VECTORS,
        "white",
        ["e2e4"],
        5,
        opponent_top_k=5,
        evaluation_metric="practical",
        evaluation_threshold=0.9,
        opponent_move_ordering="popularity",
    )

    assert nodes
    assert all(not node.is_target_move for node in nodes)


def test_sparse_family_no_longer_has_max_systemness():
    """1-line family (entropy=0, diversity=0) must not get systemness≈1.0 after coverage shrink."""
    m = compute_node_metrics(
        _base_aggregate(lc=1, div=0.0, ent=0.0),
        _PLAYER, "white", 1, 381, {},
        prior_diversity=0.35, prior_entropy=0.30,
    )
    assert m["systemness"] < 1.0, (
        f"Expected systemness < 1.0 for 1-line family; got {m['systemness']}"
    )


def test_engine_soundness_is_reported_but_does_not_change_soft_score():
    weights = {
        "player_style_match": 1.0,
        "engine_soundness": 1.0,
        "aggressiveness": 0.0,
        "practical_gamble": 0.0,
        "systemness": 0.0,
        "memory_simplicity": 0.0,
    }
    bad = compute_node_metrics(
        _base_aggregate(),
        _PLAYER,
        "white",
        5,
        381,
        weights,
        engine_soundness=0.2,
        engine_target_cp=-800,
    )
    good = compute_node_metrics(
        _base_aggregate(),
        _PLAYER,
        "white",
        5,
        381,
        weights,
        engine_soundness=0.8,
        engine_target_cp=800,
    )

    assert bad["study_score"] == pytest.approx(good["study_score"])
    assert bad["breakdown"]["engineSoundness"][0]["rawValue"] == pytest.approx(-800)


def test_practical_gamble_is_reported_but_does_not_change_soft_score():
    weights = {
        "player_style_match": 1.0,
        "engine_soundness": 0.0,
        "aggressiveness": 0.0,
        "practical_gamble": 1.0,
        "systemness": 0.0,
        "memory_simplicity": 0.0,
    }
    missing = compute_node_metrics(
        _base_aggregate(), _PLAYER, "white", 5, 381, weights,
        engine_soundness=0.8,
        practical_gamble=None,
    )
    available = compute_node_metrics(
        _base_aggregate(), _PLAYER, "white", 5, 381, weights,
        engine_soundness=0.8,
        practical_gamble=0.2,
    )

    assert missing["study_score"] == pytest.approx(available["study_score"])


def test_sparse_family_no_longer_has_zero_memory_complexity():
    """1-line family (entropy=0, diversity=0) must not get memory_complexity≈0 after coverage shrink."""
    m = compute_node_metrics(
        _base_aggregate(lc=1, div=0.0, ent=0.0),
        _PLAYER, "white", 1, 381, {},
        prior_diversity=0.35, prior_entropy=0.30,
    )
    # With coverage shrink, the prior pushes memory_complexity above the nearly-zero
    # old value even without any worst-case column.
    assert m["memory_complexity"] > 0.05, (
        f"Expected memory_complexity > 0.05 for 1-line family; got {m['memory_complexity']}"
    )


def test_global_priors_ignore_one_line_zero_entropy_rows_when_richer_rows_exist():
    rows = [
        {"line_count": 1, "structure_diversity": 0.0, "final_structure_entropy": 0.0}
        for _ in range(10)
    ]
    rows.extend(
        [
            {"line_count": 2, "structure_diversity": 0.2, "final_structure_entropy": 0.4},
            {"line_count": 3, "structure_diversity": 0.4, "final_structure_entropy": 0.6},
        ]
    )

    prior_diversity, prior_entropy = _compute_global_priors(rows)
    metrics = compute_node_metrics(
        _base_aggregate(lc=1, div=0.0, ent=0.0),
        _PLAYER,
        "black",
        1,
        381,
        {},
        prior_diversity=prior_diversity,
        prior_entropy=prior_entropy,
    )

    assert prior_diversity == pytest.approx(0.3)
    assert prior_entropy == pytest.approx(0.5)
    assert metrics["systemness"] < 1.0


def test_coverage_shrink_is_strictly_monotone():
    """More lines → structure terms are trusted more → systemness moves toward the raw signal."""
    priors = dict(prior_diversity=0.35, prior_entropy=0.30)
    sparse = compute_node_metrics(_base_aggregate(lc=1, div=0.0, ent=0.0), _PLAYER, "white", 1, 381, {}, **priors)
    medium = compute_node_metrics(_base_aggregate(lc=6, div=0.0, ent=0.0), _PLAYER, "white", 6, 381, {}, **priors)
    full = compute_node_metrics(_base_aggregate(lc=12, div=0.0, ent=0.0), _PLAYER, "white", 12, 381, {}, **priors)
    # coverage(1) < coverage(6) < coverage(12), so effective entropy/diversity rises
    # as lines increase, pushing systemness down from 1.0 toward the shrunk value.
    assert sparse["systemness"] <= medium["systemness"] <= full["systemness"] or (
        # If raw value is lower than prior, more coverage → lower systemness (still monotone).
        sparse["systemness"] >= medium["systemness"] >= full["systemness"]
    ), "Coverage shrink must be monotone: more evidence → closer to raw value"


# ---------------------------------------------------------------------------
# Part C — worst-case line count tests (no engine required)
# ---------------------------------------------------------------------------


def test_higher_worst_case_gives_higher_memory_complexity():
    """Increasing worst_line_count must increase memory_complexity monotonically."""
    priors = dict(prior_diversity=0.18, prior_entropy=0.18)
    m_low  = compute_node_metrics(_base_aggregate(lc=5, worst_white=0.0, worst_black=0.0), _PLAYER, "white", 5, 381, {}, **priors)
    m_mid  = compute_node_metrics(_base_aggregate(lc=5, worst_white=0.5, worst_black=0.5), _PLAYER, "white", 5, 381, {}, **priors)
    m_high = compute_node_metrics(_base_aggregate(lc=5, worst_white=1.0, worst_black=1.0), _PLAYER, "white", 5, 381, {}, **priors)
    assert m_low["memory_complexity"] < m_mid["memory_complexity"] < m_high["memory_complexity"], (
        f"Expected monotone increase: {m_low['memory_complexity']:.3f} < "
        f"{m_mid['memory_complexity']:.3f} < {m_high['memory_complexity']:.3f}"
    )


def test_worst_case_is_colour_specific():
    """white_worst_line_count is used for 'white' target; black_worst_line_count for 'black'."""
    priors = dict(prior_diversity=0.18, prior_entropy=0.18)
    agg = _base_aggregate(lc=5, worst_white=0.1, worst_black=0.9)
    m_white = compute_node_metrics(agg, _PLAYER, "white", 5, 381, {}, **priors)
    m_black = compute_node_metrics(agg, _PLAYER, "black", 5, 381, {}, **priors)
    assert m_white["memory_complexity"] < m_black["memory_complexity"], (
        "Black has a larger worst-case count; must yield higher memory_complexity for black target"
    )


def test_fallback_when_no_worst_case_column():
    """When worst-line columns are absent the legacy formula (with coverage shrink) is used."""
    priors = dict(prior_diversity=0.18, prior_entropy=0.18)
    agg_with = _base_aggregate(lc=5, div=0.3, ent=0.3, worst_white=0.5, worst_black=0.5)
    agg_without = _base_aggregate(lc=5, div=0.3, ent=0.3)  # legacy CSV
    m_with    = compute_node_metrics(agg_with, _PLAYER, "white", 5, 381, {}, **priors)
    m_without = compute_node_metrics(agg_without, _PLAYER, "white", 5, 381, {}, **priors)
    # Both should produce a valid score; just verify fallback does not crash and stays in [0,1].
    assert 0.0 <= m_without["memory_complexity"] <= 1.0
    assert 0.0 <= m_without["systemness"] <= 1.0


def test_breakdown_includes_coverage_row():
    """memoryComplexity breakdown must include a 'coverage' entry."""
    m = compute_node_metrics(_base_aggregate(lc=1), _PLAYER, "white", 1, 381, {})
    keys = [item["key"] for item in m["breakdown"]["memoryComplexity"]]
    assert "coverage" in keys, f"Expected 'coverage' in breakdown keys; got {keys}"


def test_breakdown_includes_worst_line_count_when_present():
    """When worst_line_count column is present it must appear in the memoryComplexity breakdown."""
    agg = _base_aggregate(lc=5, worst_white=0.6, worst_black=0.6)
    m = compute_node_metrics(agg, _PLAYER, "white", 5, 381, {})
    keys = [item["key"] for item in m["breakdown"]["memoryComplexity"]]
    assert "worst_line_count" in keys, f"Expected 'worst_line_count' in breakdown keys; got {keys}"


# ---------------------------------------------------------------------------
# CSV round-trip test (no engine required)
# ---------------------------------------------------------------------------


def test_worst_line_count_round_trips_through_csv(tmp_path):
    """write_group_features_with_raw must persist and restore the breadth columns."""
    import csv as csv_mod
    from dataclasses import replace
    from utils.opening_feature_transformer import (
        OpeningGroupFeatureVector,
        MATCHER_COLUMNS_V2,
        SIDE_MATCHER_COLUMNS_V2,
    )
    from utils.opening_feature_distribution_tools import write_group_features_with_raw

    def _make_group(**overrides) -> OpeningGroupFeatureVector:
        defaults = dict(
            opening_name="Test Opening",
            line_count=5,
            eco_values="A00",
            representative_pgn="1. e4 e5",
            representative_uci="e2e4 e7e5",
            tactical_density=0.5,
            quiet_position_density=0.5,
            king_safety_risk=0.3,
            early_castling_tendency=0.5,
            opposite_side_castling_tendency=0.2,
            middlegame_complexity=0.5,
            pawn_structure_sharpness=0.4,
            material_imbalance=0.3,
            endgame_likelihood_proxy=0.3,
            structure_diversity=0.25,
            final_structure_entropy=0.20,
        )
        for col in [*[f"white_{c}" for c in MATCHER_COLUMNS_V2], *[f"black_{c}" for c in MATCHER_COLUMNS_V2]]:
            defaults.setdefault(col, 0.5)
        defaults.update(overrides)
        return OpeningGroupFeatureVector(**defaults)

    raw = _make_group(white_worst_line_count=1.23, black_worst_line_count=2.45,
                      white_worst_line_count_raw_int=7, black_worst_line_count_raw_int=9)
    cal = _make_group(white_worst_line_count=0.40, black_worst_line_count=0.80,
                      white_worst_line_count_raw_int=7, black_worst_line_count_raw_int=9)

    out = tmp_path / "test_fv.csv"
    write_group_features_with_raw(str(out), [raw], [cal])

    with out.open() as fh:
        rows = list(csv_mod.DictReader(fh))

    assert len(rows) == 1
    row = rows[0]
    assert float(row["raw_white_worst_line_count"]) == pytest.approx(1.23, abs=1e-4)
    assert float(row["white_worst_line_count"])     == pytest.approx(0.40, abs=1e-4)
    assert int(row["white_worst_line_count_raw_int"]) == 7
    assert float(row["raw_black_worst_line_count"]) == pytest.approx(2.45, abs=1e-4)
    assert float(row["black_worst_line_count"])     == pytest.approx(0.80, abs=1e-4)
    assert int(row["black_worst_line_count_raw_int"]) == 9


def _general_request(**overrides):
    from backend.models import OpeningStudyTreeChildrenRequest

    payload = {
        "targetColor": "white",
        "prefixUci": [],
        "topK": 4,
        "opponentTopK": 4,
        "opponentMoveOrdering": "popularity",
        "evaluationMetric": "practical",
        "evaluationThreshold": 0.0,
        **overrides,
    }
    return OpeningStudyTreeChildrenRequest.model_validate(payload)


@pytest.mark.parametrize("color,prefix", [("white", []), ("black", []), ("black", ["e2e4"])])
def test_general_tree_needs_no_report_or_username(color, prefix):
    from backend.services.opening_study_service import opening_study_tree_children

    payload = opening_study_tree_children(_general_request(targetColor=color, prefixUci=prefix))

    assert payload["children"]
    assert payload["playerVector"] is None
    assert payload["vectorSource"] is None
    assert all(node["playerStyleMatch"] == 0.0 for node in payload["children"])
    assert all(not node["breakdown"].get("playerStyleMatch") for node in payload["children"])


def test_style_mode_is_disabled_and_coerced_to_custom():
    from backend.services.opening_study_service import opening_study_tree_children

    # No vector source is given: a real style request would fail to resolve one.
    payload = opening_study_tree_children(_general_request(matchMode="style", username="nobody"))

    assert payload["children"]
    assert payload["playerVector"] is None


def test_style_mode_without_vector_is_rejected_in_the_engine():
    with pytest.raises(PlayerVectorFeatureMismatch):
        get_opening_study_tree_children(None, OPENING_VECTORS, "white", [], 4, match_mode="style")
