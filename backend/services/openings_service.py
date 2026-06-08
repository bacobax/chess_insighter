from __future__ import annotations

import csv
from dataclasses import asdict, is_dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import chess

from backend.models import MetricPoint, OpeningCount, OpeningFeatureSet, OpeningMatch
from backend.settings import settings


OPENING_FEATURES = [
    "material_imbalance",
    "quiet_position_density",
    "tactical_density",
    "middlegame_complexity",
    "endgame_likelihood_proxy",
    "opposite_side_castling_tendency",
    "early_castling_tendency",
    "pawn_structure_sharpness",
    "king_safety_risk",
]


@lru_cache(maxsize=1)
def opening_feature_rows() -> list[dict[str, Any]]:
    path = settings.opening_vectors_path
    if not path.exists():
        raise FileNotFoundError(f"Opening feature vectors not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    for row in rows:
        for feature in OPENING_FEATURES:
            row[feature] = optional_float(row.get(feature))
        row["line_count"] = optional_int(row.get("line_count"))
    return rows


def build_opening_charts(bundle: Any) -> dict[str, Any]:
    profile = bundle.player_profile
    vector = bundle.matcher_ready_player_vector
    subfeatures = profile.subfeatures
    favourite = favourite_openings(subfeatures)
    return {
        "favourite_openings": favourite,
        "top_opening_features": top_opening_features(favourite),
        "opening_characteristics": opening_characteristics(vector),
        "top_opening_matches": top_opening_matches(vector),
    }


def favourite_openings(subfeatures: dict[str, Any]) -> list[OpeningCount]:
    items: list[OpeningCount] = []
    for color, key in [("white", "opening_distribution_white"), ("black", "opening_distribution_black")]:
        distribution = subfeatures.get(key) or {}
        for name, count in sorted(distribution.items(), key=lambda item: item[1], reverse=True):
            if name:
                items.append(OpeningCount(name=str(name), count=int(count), color=color))
    return items


def top_opening_features(favourites: list[OpeningCount]) -> list[OpeningFeatureSet]:
    results: list[OpeningFeatureSet] = []
    for color in ["white", "black"]:
        color_items = [item for item in favourites if item.color == color][:3]
        for item in color_items:
            family = find_opening_family_row(item.name)
            features = [
                MetricPoint(key=feature, label=pretty(feature), value=family.get(feature) if family else None)
                for feature in OPENING_FEATURES
            ]
            results.append(
                OpeningFeatureSet(
                    opening_name=item.name,
                    color=color,
                    count=item.count,
                    family_name=family.get("opening_name") if family else None,
                    features=features,
                )
            )
    return results


def opening_characteristics(vector: dict[str, float | None]) -> list[MetricPoint]:
    return [
        MetricPoint(key=feature, label=pretty(feature), value=optional_float(vector.get(feature)))
        for feature in OPENING_FEATURES
    ]


def top_opening_matches(vector: dict[str, float | None], limit: int = 15) -> list[OpeningMatch]:
    matches: list[OpeningMatch] = []
    for row in opening_feature_rows():
        score, used = cosine_similarity(row, vector)
        matches.append(
            OpeningMatch(
                opening_name=str(row.get("opening_name") or ""),
                similarity_score=score,
                eco_values=empty_to_none(row.get("eco_values")),
                line_count=row.get("line_count"),
                representative_pgn=empty_to_none(row.get("representative_pgn")),
                representative_uci=empty_to_none(row.get("representative_uci")),
                fen=uci_to_fen(empty_to_none(row.get("representative_uci"))),
                used_features=used,
            )
        )
    return sorted(matches, key=lambda item: item.similarity_score if item.similarity_score is not None else -1, reverse=True)[:limit]


def find_opening_family_row(opening_name: str) -> dict[str, Any] | None:
    rows = opening_feature_rows()
    exact = next((row for row in rows if row.get("opening_name") == opening_name), None)
    if exact is not None:
        return exact
    family = opening_name.split(":", 1)[0].strip()
    return next((row for row in rows if row.get("opening_name") == family), None)


def cosine_similarity(row: dict[str, Any], vector: dict[str, float | None]) -> tuple[float | None, list[str]]:
    left: list[float] = []
    right: list[float] = []
    used: list[str] = []
    for feature, player_value in vector.items():
        opening_value = optional_float(row.get(feature))
        if player_value is None or opening_value is None:
            continue
        left.append(float(player_value))
        right.append(opening_value)
        used.append(feature)
    if not left or not right:
        return None, used
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return None, used
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm), used


def uci_to_fen(uci_line: str | None) -> str | None:
    if not uci_line:
        return None
    board = chess.Board()
    try:
        for token in uci_line.split():
            move = chess.Move.from_uci(token)
            if move not in board.legal_moves:
                return None
            board.push(move)
    except ValueError:
        return None
    return board.fen()


def serializable(value: Any) -> Any:
    if is_dataclass(value):
        return serializable(asdict(value))
    if isinstance(value, dict):
        return {str(key): serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def optional_float(value: Any) -> float | None:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def optional_int(value: Any) -> int | None:
    try:
        return None if value in (None, "") else int(value)
    except (TypeError, ValueError):
        return None


def empty_to_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def pretty(value: str) -> str:
    return value.replace("_", " ").title()
