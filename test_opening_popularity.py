from __future__ import annotations

from datetime import datetime, timezone

import chess
import pytest
import requests

from build_opening_popularity import (
    DirectMetric,
    EnginePositionAnalysis,
    compute_direct_metric,
    default_window,
    enrich_opening_vectors,
    fetch_explorer_position,
    write_snapshot,
)
from utils.opening_popularity import (
    empirical_midrank_percentiles,
    load_popularity_snapshot,
    position_key,
    weighted_practical_gamble,
)


def test_default_window_uses_last_24_complete_months():
    assert default_window(datetime(2026, 9, 1, tzinfo=timezone.utc)) == ("2024-09", "2026-08")


def test_weighted_practical_gamble_has_no_sigma_term():
    raw, sample = weighted_practical_gamble(
        {"a": 75, "b": 25},
        {"a": 0.40, "b": 0.80},
        0.30,
    )
    assert sample == 100
    assert raw == pytest.approx((0.75 * 0.40 + 0.25 * 0.80) - 0.30)


def test_weighted_practical_gamble_requires_30_covered_games():
    raw, sample = weighted_practical_gamble({"a": 29}, {"a": 0.8}, 0.2)
    assert raw is None
    assert sample == 29


def test_best_defense_can_be_absent_from_popular_moves():
    raw, sample = weighted_practical_gamble(
        {"popular": 100},
        {"popular": 0.75, "engine": 0.25},
        0.25,
    )
    assert sample == 100
    assert raw == pytest.approx(0.5)


def test_midrank_percentiles_ties_missing_and_constants():
    assert empirical_midrank_percentiles([0.0, 0.5, 0.5, 1.0, None]) == [0.0, 0.5, 0.5, 1.0, None]
    assert empirical_midrank_percentiles([0.2, 0.2, None]) == [0.5, 0.5, None]


def test_direct_metric_is_oriented_for_side_not_to_move():
    board = chess.Board()  # White moves, so the studied/defending side is Black.
    payload = {
        "white": 75,
        "draws": 0,
        "black": 25,
        "moves": [
            {"uci": "e2e4", "white": 75, "draws": 0, "black": 0},
            {"uci": "d2d4", "white": 0, "draws": 0, "black": 25},
        ],
    }
    analysis = EnginePositionAnalysis(
        best_move="e2e4",
        white_cp_by_move={"e2e4": 0.0, "d2d4": -600.0},
    )
    metric = compute_direct_metric(board, payload, analysis, min_games=30)

    assert metric.target_color == "black"
    assert metric.sample_size == 100
    assert metric.raw is not None and metric.raw > 0


def test_target_to_move_uses_best_move_child_metric(tmp_path):
    root = chess.Board()
    child = root.copy()
    child.push_uci("e2e4")
    root_epd = position_key(root)
    child_epd = position_key(child)
    base = {root_epd: root}
    payload = {"white": 50, "draws": 0, "black": 50, "moves": []}
    direct = {
        root_epd: DirectMetric("black", 0.10, 100, 1.0),
        child_epd: DirectMetric("white", 0.30, 100, 1.0),
    }

    rows = write_snapshot(
        tmp_path / "snapshot.csv",
        base,
        {root_epd: payload},
        {root_epd: child_epd},
        direct,
    )

    assert rows[root_epd]["black_practical_gamble_raw"] == pytest.approx(0.10)
    assert rows[root_epd]["white_practical_gamble_raw"] == pytest.approx(0.30)


def test_snapshot_loader_notices_file_created_after_initial_miss(tmp_path):
    snapshot = tmp_path / "snapshot.csv"
    assert load_popularity_snapshot(str(snapshot)) == {}
    root = chess.Board()
    epd = position_key(root)
    write_snapshot(
        snapshot,
        {epd: root},
        {epd: {"white": 50, "draws": 0, "black": 50, "moves": []}},
        {},
        {epd: DirectMetric("black", 0.1, 100, 1.0)},
    )
    assert epd in load_popularity_snapshot(str(snapshot))


def test_explorer_fetch_retries_and_then_resumes_from_cache(tmp_path, monkeypatch):
    payload = {"white": 1, "draws": 2, "black": 3, "moves": []}

    class Response:
        def __init__(self, status_code, body=None, headers=None):
            self.status_code = status_code
            self._body = body
            self.headers = headers or {}

        def json(self):
            return self._body

    class Session:
        def __init__(self):
            self.calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise requests.ConnectionError("remote disconnected")
            if self.calls == 2:
                return Response(429, headers={"Retry-After": "1"})
            return Response(200, payload)

    session = Session()
    monkeypatch.setattr("build_opening_popularity.time.sleep", lambda _: None)
    first = fetch_explorer_position(
        chess.Board(), cache_dir=tmp_path, session=session, token="secret",
        since="2024-09", until="2026-08", request_delay=0,
    )
    assert first == payload
    assert session.calls == 3

    class ExplodingSession:
        def get(self, *args, **kwargs):
            raise AssertionError("cached fetch must not hit the network")

    cached = fetch_explorer_position(
        chess.Board(), cache_dir=tmp_path, session=ExplodingSession(), token=None,
        since="2024-09", until="2026-08", request_delay=0,
    )
    assert cached == payload


def test_enrich_opening_vectors_adds_popularity_columns(tmp_path):
    vectors = tmp_path / "opening_feature_vectors.csv"
    vectors.write_text(
        "opening_name,representative_uci,existing_feature\nKing Pawn,e2e4,0.75\n",
        encoding="utf-8",
    )
    root = chess.Board()
    child = root.copy()
    child.push_uci("e2e4")
    root_epd = position_key(root)
    child_epd = position_key(child)
    rows = {
        root_epd: {
            "total_games": 1000,
            "moves_json": '[{"uci":"e2e4","games":600,"share":0.6}]',
        },
        child_epd: {
            "total_games": 600,
            "moves_json": "[]",
            "white_practical_gamble_raw": 0.2,
            "white_practical_gamble": 0.8,
            "white_practical_gamble_games": 600,
            "black_practical_gamble_raw": 0.1,
            "black_practical_gamble": 0.4,
            "black_practical_gamble_games": 600,
        },
    }

    assert enrich_opening_vectors(vectors, vectors, rows) == 1
    content = vectors.read_text(encoding="utf-8")
    assert "lichess_position_games" in content
    assert "white_practical_gamble" in content
    assert ",600,0.6,0.6,0.2,0.8,600,0.1,0.4,600" in content
