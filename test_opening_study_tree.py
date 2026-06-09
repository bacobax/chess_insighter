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
