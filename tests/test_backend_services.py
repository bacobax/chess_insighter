from __future__ import annotations

from backend.services.cache_service import stable_hash
from backend.services.chesscom_service import summarize_game
from backend.services.openings_service import find_opening_family_row, uci_to_fen
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
