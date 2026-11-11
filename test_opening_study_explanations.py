from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from utils.opening_study_explanations import explain_opponent_moves, explain_player_moves
from utils.opening_study_tree import get_opening_study_tree_children, resolve_study_weights

OPENING_VECTORS = str(Path(__file__).resolve().parent / "openings_dataset/opening_feature_vectors.csv")
WEIGHTS = resolve_study_weights(
    {"aggressiveness": 1.0, "systemness": 0.5, "memory_simplicity": 1.0}, "custom", "engine",
)


def _node(san: str, aggro: float, system: float, memory: float, *, tactical: float = 0.5, weights=WEIGHTS):
    score = (
        weights["aggressiveness"] * aggro
        + weights["systemness"] * system
        + weights["memory_simplicity"] * (1.0 - memory)
    )
    return SimpleNamespace(
        move_uci=san,
        move_san=san,
        player_style_match=0.0,
        aggressiveness=aggro,
        systemness=system,
        memory_complexity=memory,
        study_score=score,
        popularity_score=0.0,
        breakdown={
            "aggressiveness": [
                {"key": "tactical_density", "value": tactical, "weight": 0.35},
                {"key": "material_imbalance", "value": 0.5, "weight": 0.20},
            ],
        },
    )


def _sorted(*nodes):
    return sorted(nodes, key=lambda node: node.study_score, reverse=True)


def test_shares_add_up_to_the_score_gap():
    nodes = _sorted(_node("d5", 0.71, 0.42, 0.59), _node("c6", 0.63, 0.47, 0.57), _node("e5", 0.72, 0.32, 0.60))
    for node, explanation in zip(nodes, explain_player_moves(nodes, WEIGHTS)):
        total = sum(factor["contribution"] for factor in explanation["factors"])
        assert total == pytest.approx(explanation["scoreGap"], abs=0.02)


def test_original_wording_for_the_screenshot_example():
    d5 = _node("…d5", 0.71, 0.42, 0.59, tactical=0.7)
    c6 = _node("…c6", 0.63, 0.47, 0.57, tactical=0.5)
    top, second = explain_player_moves(_sorted(d5, c6), WEIGHTS)

    assert second["comparedTo"] == "…d5"
    assert second["summary"] == (
        "Ranks about 1 point below …d5. It is clearly less aggressive (fewer tactical positions), "
        "which costs more than it gains from being clearly more systematic and slightly easier to memorise."
    )
    assert top["comparedTo"] == "…c6"
    assert top["summary"].startswith("Ranks about 1 point above …c6, mainly because it is clearly more aggressive")
    assert top["summary"].endswith("even though it is clearly less systematic and slightly harder to memorise.")


def test_top_move_is_compared_with_the_runner_up_and_others_with_the_top():
    nodes = _sorted(_node("a", 0.9, 0.5, 0.5), _node("b", 0.6, 0.5, 0.5), _node("c", 0.3, 0.5, 0.5))
    refs = [explanation["comparedTo"] for explanation in explain_player_moves(nodes, WEIGHTS)]
    assert refs == ["b", "a", "a"]


def test_near_identical_moves_read_as_practically_tied():
    nodes = _sorted(_node("a", 0.60, 0.50, 0.50), _node("b", 0.59, 0.51, 0.50))
    explanation = explain_player_moves(nodes, WEIGHTS)[1]
    assert explanation["summary"].startswith("Practically tied with a")


def test_wording_degree_follows_the_metric_gap():
    big = explain_player_moves(_sorted(_node("a", 0.9, 0.5, 0.5), _node("b", 0.6, 0.5, 0.5)), WEIGHTS)[1]
    assert "much less aggressive" in big["summary"]
    small = explain_player_moves(_sorted(_node("a", 0.53, 0.5, 0.5), _node("b", 0.5, 0.5, 0.5)), WEIGHTS)[1]
    assert "slightly less aggressive" in small["summary"]


def test_single_option_and_highlights():
    only = explain_player_moves([_node("a", 0.5, 0.5, 0.5)], WEIGHTS)[0]
    assert only["summary"] == "The only suggested move in this position."

    nodes = _sorted(_node("a", 0.9, 0.2, 0.5), _node("b", 0.6, 0.5, 0.4), _node("c", 0.3, 0.8, 0.3))
    by_move = {node.move_san: explanation for node, explanation in zip(nodes, explain_player_moves(nodes, WEIGHTS))}
    assert "The most aggressive of the 3 options" in by_move["a"]["highlights"]
    assert "The easiest to memorise of the 3 options" in by_move["c"]["highlights"]


def test_feasibility_clause_only_when_the_check_is_active():
    nodes = _sorted(_node("a", 0.9, 0.5, 0.5), _node("b", 0.6, 0.5, 0.5))
    off = explain_player_moves(nodes, WEIGHTS, threshold=0.0, percentiles={"a": 1.0, "b": 0.0})
    assert all(explanation["feasibility"] is None for explanation in off)
    on = explain_player_moves(
        nodes, WEIGHTS, evaluation_metric="engine", threshold=0.5, percentiles={"a": 1.0, "b": 0.6},
    )
    assert on[0]["feasibility"] == "Passes the engine check: among the engine's top choices here."
    assert on[1]["feasibility"] == "Passes the engine check: a better engine evaluation than 60% of the alternatives."


def test_opponent_replies_explain_their_order():
    replies = [SimpleNamespace(popularity_score=0.454), SimpleNamespace(popularity_score=0.28)]
    popular = explain_opponent_moves(replies, "popularity")
    assert popular[0]["summary"] == "Played in 45.4% of Lichess games from this position."
    engine = explain_opponent_moves(replies, "engine")
    assert engine[0]["summary"].startswith("The strongest defence by engine evaluation.")
    assert engine[1]["summary"].startswith("The second-strongest defence")


def test_tree_children_carry_explanations_for_both_sides():
    player = get_opening_study_tree_children(
        None, OPENING_VECTORS, "black", ["e2e4"], 4,
        match_mode="custom", evaluation_metric="practical", evaluation_threshold=0.0,
        opponent_move_ordering="popularity",
    )
    assert len(player) > 1
    assert all(node.explanation["summary"] for node in player)
    assert player[1].explanation["comparedTo"] == player[0].move_san
    assert player[0].to_dict()["explanation"]["summary"] == player[0].explanation["summary"]

    root = get_opening_study_tree_children(
        None, OPENING_VECTORS, "black", [], 4,
        match_mode="custom", evaluation_metric="practical", opponent_move_ordering="popularity",
    )
    assert all(node.explanation["summary"].startswith("Played in") for node in root)
