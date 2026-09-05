"""Lichess opening-popularity snapshot and Practical Gamble helpers.

The runtime Opening Lab only reads the generated companion CSV. Network access
and Stockfish batch analysis live in ``build_opening_popularity.py`` so tree
requests remain fast and deterministic.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

import chess


POPULARITY_FILENAME = "opening_position_popularity.csv"
POPULARITY_MANIFEST_FILENAME = "opening_position_popularity.manifest.json"
MIN_POPULARITY_GAMES = 30


def position_key(board: chess.Board) -> str:
    """Return a clock-independent, transposition-aware position key."""
    return board.epd()


@dataclass(frozen=True)
class PracticalGambleValue:
    percentile: float | None
    raw: float | None
    sample_size: int
    coverage: float


@dataclass(frozen=True)
class PositionPopularity:
    position_epd: str
    total_games: int
    covered_games: int
    coverage: float
    moves: tuple[dict[str, Any], ...]
    white: PracticalGambleValue
    black: PracticalGambleValue


def weighted_practical_gamble(
    move_games: Mapping[str, int],
    move_utilities: Mapping[str, float],
    best_defense_utility: float,
    *,
    min_games: int = MIN_POPULARITY_GAMES,
) -> tuple[float | None, int]:
    """Return ``(weighted human utility - best defense utility, sample)``.

    Only moves with both a positive game count and an engine utility contribute.
    The tiny clamp at zero prevents independent-search noise from manufacturing a
    negative gap. There is intentionally no dispersion/sigma term.
    """
    usable = {
        move: max(0, int(games))
        for move, games in move_games.items()
        if int(games) > 0 and move in move_utilities
    }
    sample_size = sum(usable.values())
    if sample_size < max(0, int(min_games)):
        return None, sample_size
    expected = sum(
        (games / sample_size) * float(move_utilities[move])
        for move, games in usable.items()
    )
    return max(0.0, min(1.0, expected - float(best_defense_utility))), sample_size


def empirical_midrank_percentiles(values: Iterable[float | None]) -> list[float | None]:
    """Map valid values to [0, 1] empirical mid-rank percentiles.

    Equal values receive the same percentile. A singleton/all-constant population
    maps to 0.5, matching the feature-vector calibration convention.
    """
    source = list(values)
    valid = sorted(float(value) for value in source if value is not None)
    if not valid:
        return [None for _ in source]
    if valid[0] == valid[-1]:
        return [0.5 if value is not None else None for value in source]

    positions: dict[float, list[int]] = {}
    for index, value in enumerate(valid):
        positions.setdefault(value, []).append(index)
    denominator = max(1, len(valid) - 1)
    ranks = {
        value: (indices[0] + indices[-1]) / (2.0 * denominator)
        for value, indices in positions.items()
    }
    return [ranks[float(value)] if value is not None else None for value in source]


def companion_path_for(opening_vectors_path: str | Path) -> Path:
    return Path(opening_vectors_path).resolve().parent / POPULARITY_FILENAME


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


@lru_cache(maxsize=8)
def _load_popularity_snapshot_cached(path: str, modified_ns: int) -> dict[str, PositionPopularity]:
    snapshot_path = Path(path)
    result: dict[str, PositionPopularity] = {}
    with snapshot_path.open("r", encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            epd = str(raw.get("position_epd") or "").strip()
            if not epd:
                continue
            try:
                parsed_moves = json.loads(str(raw.get("moves_json") or "[]"))
            except json.JSONDecodeError:
                parsed_moves = []
            moves = tuple(item for item in parsed_moves if isinstance(item, dict))
            result[epd] = PositionPopularity(
                position_epd=epd,
                total_games=_int(raw.get("total_games")),
                covered_games=_int(raw.get("covered_games")),
                coverage=float(_optional_float(raw.get("coverage")) or 0.0),
                moves=moves,
                white=PracticalGambleValue(
                    percentile=_optional_float(raw.get("white_practical_gamble")),
                    raw=_optional_float(raw.get("white_practical_gamble_raw")),
                    sample_size=_int(raw.get("white_practical_gamble_games")),
                    coverage=float(_optional_float(raw.get("white_practical_gamble_coverage")) or 0.0),
                ),
                black=PracticalGambleValue(
                    percentile=_optional_float(raw.get("black_practical_gamble")),
                    raw=_optional_float(raw.get("black_practical_gamble_raw")),
                    sample_size=_int(raw.get("black_practical_gamble_games")),
                    coverage=float(_optional_float(raw.get("black_practical_gamble_coverage")) or 0.0),
                ),
            )
    return result


def load_popularity_snapshot(path: str) -> dict[str, PositionPopularity]:
    """Load a snapshot and automatically invalidate when generation replaces it."""
    snapshot_path = Path(path)
    if not snapshot_path.exists():
        return {}
    return _load_popularity_snapshot_cached(str(snapshot_path), snapshot_path.stat().st_mtime_ns)


def practical_gamble_for_board(
    board: chess.Board,
    target_color: str,
    opening_vectors_path: str | Path,
) -> PracticalGambleValue:
    record = load_popularity_snapshot(str(companion_path_for(opening_vectors_path))).get(position_key(board))
    if record is None:
        return PracticalGambleValue(None, None, 0, 0.0)
    return record.white if target_color == "white" else record.black


def move_popularity_for_board(
    board: chess.Board,
    opening_vectors_path: str | Path,
) -> dict[str, tuple[float, int]]:
    """Return ``uci -> (share, games)`` for moves from ``board``.

    The popularity snapshot is keyed by the position *before* the move, unlike
    Practical Gamble which describes the resulting position.  Keeping this
    lookup separate prevents the Opening Lab from accidentally treating a
    favorable resulting position as a popular opponent reply.
    """
    record = load_popularity_snapshot(str(companion_path_for(opening_vectors_path))).get(position_key(board))
    if record is None:
        return {}

    result: dict[str, tuple[float, int]] = {}
    for item in record.moves:
        uci = str(item.get("uci") or "").strip()
        if not uci:
            continue
        result[uci] = (
            max(0.0, min(1.0, float(_optional_float(item.get("share")) or 0.0))),
            max(0, _int(item.get("games"))),
        )
    return result
