from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend import main as api_main
from backend.models import ReportBuildRequest, SaveReportRequest
from backend.services import openings_service, statistics_service
from backend.services.cache_service import stable_hash
from backend.services.cache_service import report_cache_key
from backend.services.chesscom_service import summarize_game
from backend.services.openings_service import (
    opening_feature_rows,
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
    # With the variation-level CSV (~3709 rows) the exact variation name has its
    # own row, so the lookup returns that variation directly rather than falling
    # back to the family.  Both outcomes are acceptable depending on CSV version;
    # the important guarantee is that a result is returned and its name starts
    # with the family prefix.
    row = find_opening_family_row("Amar Opening: Paris Gambit")
    assert row is not None
    assert str(row["opening_name"]).startswith("Amar Opening")
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


def test_opening_feature_rows_falls_back_to_global_side_fields(tmp_path):
    path = tmp_path / "opening_vectors.csv"
    path.write_text(
        ",".join(
            [
                "opening_name",
                "line_count",
                "eco_values",
                "representative_pgn",
                "representative_uci",
                "tactical_density",
                "quiet_position_density",
                "king_safety_risk",
                "early_castling_tendency",
                "opposite_side_castling_tendency",
                "middlegame_complexity",
                "pawn_structure_sharpness",
                "material_imbalance",
                "endgame_likelihood_proxy",
                "final_structure_entropy",
                "structure_diversity",
                "structure_distribution",
            ]
        )
        + "\n"
        + "Fallback,1,A00,,,0.7,0.2,0.1,0.3,0.4,0.5,0.6,0.8,0.9,0.0,0.0,{}\n",
        encoding="utf-8",
    )
    previous = settings.opening_vectors_path
    object.__setattr__(settings, "opening_vectors_path", path)
    opening_feature_rows.cache_clear()
    try:
        row = opening_feature_rows()[0]
        assert row["white_tactical_density"] == row["tactical_density"]
        assert row["black_material_imbalance"] == row["material_imbalance"]
    finally:
        object.__setattr__(settings, "opening_vectors_path", previous)
        opening_feature_rows.cache_clear()


def test_top_opening_matches_uses_side_specific_opening_vectors(monkeypatch):
    rows = [
        _opening_row(
            "White Fit",
            tactical_density=0.0,
            quiet_position_density=1.0,
            white_tactical_density=1.0,
            white_quiet_position_density=0.0,
            black_tactical_density=0.0,
            black_quiet_position_density=1.0,
        ),
        _opening_row(
            "Black Fit",
            tactical_density=1.0,
            quiet_position_density=0.0,
            white_tactical_density=0.0,
            white_quiet_position_density=1.0,
            black_tactical_density=1.0,
            black_quiet_position_density=0.0,
        ),
    ]
    monkeypatch.setattr(openings_service, "opening_feature_rows", lambda: rows)
    vector = {"tactical_density": 1.0, "quiet_position_density": 0.0}

    white = top_opening_matches(vector, target_color="white", match_mode="dot_product", limit=1)[0]
    black = top_opening_matches(vector, target_color="black", match_mode="dot_product", limit=1)[0]
    both = top_opening_matches(vector, target_color="both", match_mode="dot_product", limit=1)[0]

    assert white.opening_name == "White Fit"
    assert white.used_vector_color == "white"
    assert black.opening_name == "Black Fit"
    assert black.used_vector_color == "black"
    assert both.opening_name == "Black Fit"
    assert both.used_vector_color == "global"


def test_report_cache_key_does_not_include_target_color():
    key = report_cache_key(
        username="Alice",
        hparams={"sampling": {"min_samples": 3}},
        filters={},
        max_games=20,
        engine_depth=10,
        use_engine=True,
    )

    assert "target_color" not in key


def test_save_report_rejects_missing_cache_hash(monkeypatch):
    calls = []

    class FakeCache:
        def get(self, _cache_hash):
            return None

    monkeypatch.setattr(api_main, "ReportCache", lambda: FakeCache())
    monkeypatch.setattr(api_main, "save_report_entry", lambda **kwargs: calls.append(kwargs))

    with pytest.raises(HTTPException) as exc_info:
        api_main.save_report(
            SaveReportRequest(
                cache_hash="missing",
                username="Alice",
                games_analyzed=3,
                request_params={"username": "Alice"},
            )
        )

    assert exc_info.value.status_code == 404
    assert calls == []


def test_build_report_computes_once_and_returns_opening_groups(monkeypatch, tmp_path):
    calls = {"fetch": 0, "enrich": 0, "build": 0}

    class FakeCache:
        def get(self, _cache_hash):
            return None

        def set(self, _cache_hash, _payload):
            return None

    class FakeBuilder:
        def __init__(self, _hparams_path):
            pass

        def build(self, _games, player_name):
            calls["build"] += 1
            profile = SimpleNamespace(
                player_name=player_name,
                games_analyzed=1,
                moves_analyzed=1,
                style_vector={},
                skill_vector={},
                subfeatures={},
                confidence={},
            )
            return SimpleNamespace(
                global_statistics=_fake_stats(),
                player_profile=profile,
                matcher_ready_player_vector={"tactical_density": 0.5},
                player_profiles_by_color={"white": profile, "black": profile, "both": profile},
                matcher_ready_player_vectors={
                    "white": {"tactical_density": 1.0},
                    "black": {"tactical_density": 0.0},
                    "both": {"tactical_density": 0.5},
                },
            )

    def fake_fetch_latest_games_for_report(**_kwargs):
        calls["fetch"] += 1
        return [{"uuid": "game"}]

    def fake_enrich_games(_games, **_kwargs):
        calls["enrich"] += 1
        return ([{"id": "enriched"}], {})

    def fake_opening_charts(_bundle):
        group = {
            "opening_characteristics": [],
            "top_opening_features": [],
            "top_opening_matches": [],
        }
        return {
            "favourite_openings": [],
            "top_opening_features": [],
            "opening_characteristics": [],
            "top_opening_matches": [],
            "opening_report_groups": {"white": group, "black": group, "both": group},
        }

    monkeypatch.setattr(statistics_service, "ReportCache", lambda: FakeCache())
    monkeypatch.setattr(statistics_service, "PlayerStatisticsBuilder", FakeBuilder)
    monkeypatch.setattr(statistics_service, "fetch_latest_games_for_report", fake_fetch_latest_games_for_report)
    monkeypatch.setattr(statistics_service, "enrich_games", fake_enrich_games)
    monkeypatch.setattr(statistics_service, "build_opening_charts", fake_opening_charts)
    monkeypatch.setattr(
        statistics_service,
        "serializable",
        lambda bundle: {
            "player_profile": {},
            "matcher_ready_player_vector": bundle.matcher_ready_player_vector,
            "player_profiles_by_color": {},
            "matcher_ready_player_vectors": bundle.matcher_ready_player_vectors,
        },
    )
    monkeypatch.setattr(statistics_service, "update_player_vector_cache", lambda **_kwargs: None)
    previous_report_config_dir = settings.report_config_dir
    object.__setattr__(settings, "report_config_dir", tmp_path)
    try:
        response = statistics_service.build_report(
            ReportBuildRequest(username="Alice", hparams={}, max_games=1, use_engine=False)
        )
    finally:
        object.__setattr__(settings, "report_config_dir", previous_report_config_dir)

    assert calls == {"fetch": 1, "enrich": 1, "build": 1}
    assert set(response.report.charts.opening_report_groups) == {"white", "black", "both"}


def _opening_row(name: str, **values):
    row = {
        "opening_name": name,
        "line_count": 1,
        "eco_values": "A00",
        "representative_pgn": "",
        "representative_uci": "",
        "structure_distribution": {},
    }
    for feature in openings_service.MATCHER_COLUMNS_V2:
        row[feature] = values.get(feature, 0.0)
        row[f"white_{feature}"] = values.get(f"white_{feature}", row[feature])
        row[f"black_{feature}"] = values.get(f"black_{feature}", row[feature])
    return row


def _fake_stats():
    class Section:
        score = 0.5
        average_time_spent_by_complexity = {
            "simple": 1.0,
            "normal": 1.0,
            "complex": 1.0,
            "high_complexity": 1.0,
        }

        def __getattr__(self, _name):
            return 0.5

    section = Section()
    return SimpleNamespace(
        middlegame_strategy_score=section,
        openings_score=section,
        calculation_score=section,
        tactics_score=section,
        resourcefulness_score=section,
        advantage_capitalization_score=section,
        game_analysis_score=section,
        time_management_score=section,
        endgame_score=section,
    )
