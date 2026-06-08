from __future__ import annotations

from backend.services.cache_service import stable_hash
from backend.services.chesscom_service import summarize_game
from backend.services.openings_service import (
    structure_distribution_similarity,
    top_opening_matches,
    top_opening_matches_from_cached_report,
    uci_to_fen,
    weighted_dot_product_similarity,
    weighted_cosine_similarity,
    find_opening_family_row,
)
from backend.settings import settings
from utils.statistics_shared import StatisticsHparams


def test_default_hparams_loader_matches_config():
    assert StatisticsHparams(settings.hparams_path).values["sampling"]["min_samples"] == 3


def test_stable_hash_normalizes_dict_order_and_simple_lists():
    left = stable_hash({"b": 2, "a": {"time_classes": ["rapid", "blitz"]}})
    right = stable_hash({"a": {"time_classes": ["blitz", "rapid"]}, "b": 2})
    assert left == right


def test_stable_hash_changes_for_hparam_value():
    left = stable_hash({"username": "alice", "hparams": {"sampling": {"min_samples": 3}}})
    right = stable_hash({"username": "alice", "hparams": {"sampling": {"min_samples": 4}}})
    assert left != right


def test_game_summary_maps_player_and_opponent_fields():
    game = {
        "uuid": "id",
        "url": "https://example.test/game",
        "white": {"username": "Alice", "rating": 1510, "result": "win"},
        "black": {"username": "Bob", "rating": 1490, "result": "resigned"},
        "end_time": 1700000000,
        "time_class": "rapid",
        "time_control": "600",
        "rated": True,
        "pgn": '[White "Alice"]\n[Black "Bob"]\n[Result "1-0"]\n[ECO "C20"]\n[Opening "King\'s Pawn Game"]\n\n1. e4 e5 1-0\n',
    }
    summary = summarize_game("alice", game)
    assert summary.result == "win"
    assert summary.player_color == "white"
    assert summary.opponent_username == "Bob"
    assert summary.opening_name == "King's Pawn Game"


def test_opening_family_lookup_and_uci_to_fen():
    assert find_opening_family_row("Amar Opening: Paris Gambit")["opening_name"] == "Amar Opening"
    fen = uci_to_fen("g1h3")
    assert fen is not None
    assert " b " in fen


def test_weighted_cosine_and_structure_similarity_helpers():
    score, used = weighted_cosine_similarity(
        {"tactical_density": 1.0, "quiet_position_density": 0.0},
        {"tactical_density": 1.0, "quiet_position_density": 1.0},
        {"tactical_density": 1.0, "quiet_position_density": 0.5},
    )

    assert used == ["tactical_density", "quiet_position_density"]
    assert score is not None and 0.0 < score < 1.0

    profile = type("Profile", (), {"subfeatures": {"structure_distribution": {"isolani": 2}}})()
    assert structure_distribution_similarity(
        profile,
        {"structure_distribution": {"isolani": 1, "hanging-pawns": 1}},
    ) == 0.5

    dot, dot_used = weighted_dot_product_similarity(
        {"tactical_density": 1.0, "quiet_position_density": 0.5},
        {"tactical_density": 0.25, "quiet_position_density": 1.0},
        {"tactical_density": 2.0, "quiet_position_density": 0.5},
    )
    assert dot_used == ["tactical_density", "quiet_position_density"]
    assert dot == 0.75


def test_top_opening_matches_accepts_target_color_both_without_distribution():
    matches = top_opening_matches(
        {"tactical_density": 1.0},
        limit=1,
        target_color="both",
    )

    assert len(matches) == 1
    assert matches[0].target_color == "both"
    assert matches[0].weighted_cosine_score == matches[0].similarity_score

    dot_matches = top_opening_matches(
        {"tactical_density": 1.0},
        limit=1,
        target_color="both",
        match_mode="dot_product",
    )
    assert dot_matches[0].match_mode == "dot_product"
    assert dot_matches[0].dot_product_score == dot_matches[0].similarity_score
