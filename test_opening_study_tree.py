from __future__ import annotations

from pathlib import Path

import pytest

from utils.opening_study_tree import (
    COMMON_WHITE_FIRST_MOVES,
    PlayerVectorFeatureMismatch,
    clamp01,
    get_opening_study_tree_children,
    load_player_vector_from_cache,
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
from utils.opening_study_tree import COVERAGE_FULL, compute_node_metrics


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
