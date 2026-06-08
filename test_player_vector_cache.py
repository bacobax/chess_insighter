from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from utils.player_vector_cache import (
    CachedPlayerVector,
    PlayerVectorCache,
    chesscom_cache_key,
    pgn_cache_key,
)


def cached_value(key, marker="first"):
    return CachedPlayerVector(
        vector={"tactical_density": 0.5},
        feature_order=["tactical_density"],
        metadata={"marker": marker},
        confidence={"tactical_density": 1.0},
        cache_key=key,
        created_at="2026-01-01T00:00:00+00:00",
    )


def test_chesscom_cache_key_canonicalizes_time_classes():
    left = chesscom_cache_key(
        username=" Alice ",
        max_games=20,
        since_year=2026,
        since_month=1,
        time_classes={"rapid", "blitz"},
        rated_filter=True,
        engine_depth=10,
    )
    right = chesscom_cache_key(
        username="alice",
        max_games=20,
        since_year=2026,
        since_month=1,
        time_classes={"blitz", "rapid"},
        rated_filter=True,
        engine_depth=10,
    )

    assert left == right
    assert left["username"] == "alice"
    assert left["time_classes"] == ["blitz", "rapid"]


def test_chesscom_cache_key_changes_for_each_required_dimension():
    base = chesscom_cache_key(
        username="alice",
        max_games=20,
        since_year=2026,
        since_month=1,
        time_classes={"rapid"},
        rated_filter=True,
        engine_depth=10,
    )
    variants = [
        {**base, "username": "bob"},
        {**base, "max_games": 30},
        {**base, "since_year": 2025},
        {**base, "since_month": 2},
        {**base, "time_classes": ["blitz"]},
        {**base, "rated_filter": False},
        {**base, "rated_filter": None},
        {**base, "engine_depth": 12},
    ]

    for variant in variants:
        assert PlayerVectorCache.key_id(base) != PlayerVectorCache.key_id(variant)


def test_cache_returns_saved_vector_and_overwrites_on_set():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "vectors.json"
        cache = PlayerVectorCache(path)
        key = chesscom_cache_key(
            username="alice",
            max_games=20,
            since_year=2026,
            since_month=1,
            time_classes=None,
            rated_filter=None,
            engine_depth=10,
        )

        cache.set(cached_value(key, marker="first"))
        assert cache.get(key).metadata["marker"] == "first"

        cache.set(cached_value(key, marker="second"))
        loaded = cache.get(key)
        assert loaded.cache_hit is True
        assert loaded.metadata["marker"] == "second"


def test_pgn_cache_key_includes_file_metadata():
    with tempfile.TemporaryDirectory() as tmp:
        pgn = Path(tmp) / "games.pgn"
        pgn.write_text('[White "alice"]\n[Black "bob"]\n[Result "*"]\n\n1. e4 *\n', encoding="utf-8")
        first = pgn_cache_key(pgn_path=pgn, player_name="Alice", engine_depth=10)

        pgn.write_text('[White "alice"]\n[Black "bob"]\n[Result "*"]\n\n1. d4 d5 2. c4 *\n', encoding="utf-8")
        second = pgn_cache_key(pgn_path=pgn, player_name="Alice", engine_depth=10)

        assert first["player_name"] == "alice"
        assert first != second


class PlayerVectorCacheTests(unittest.TestCase):
    def test_chesscom_cache_key_canonicalizes_time_classes(self):
        test_chesscom_cache_key_canonicalizes_time_classes()

    def test_chesscom_cache_key_changes_for_each_required_dimension(self):
        test_chesscom_cache_key_changes_for_each_required_dimension()

    def test_cache_returns_saved_vector_and_overwrites_on_set(self):
        test_cache_returns_saved_vector_and_overwrites_on_set()

    def test_pgn_cache_key_includes_file_metadata(self):
        test_pgn_cache_key_includes_file_metadata()
