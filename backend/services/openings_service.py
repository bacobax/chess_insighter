from __future__ import annotations

import csv
from dataclasses import asdict, is_dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import chess

from backend.models import MetricPoint, OpeningCount, OpeningFeatureSet, OpeningMatch
from backend.services.cache_service import ReportCache
from backend.settings import settings
from utils.opening_feature_transformer import (
    BLACK_MATCHER_COLUMNS_V2,
    MATCHER_COLUMNS_V2,
    WHITE_MATCHER_COLUMNS_V2,
    decode_distribution_csv,
    histogram_intersection,
    normalize_distribution,
    opening_vector_for_color,
)


MATCHER_FEATURE_WEIGHTS = {
    "tactical_density": 1.00,
    "quiet_position_density": 0.80,
    "king_safety_risk": 0.80,
    "early_castling_tendency": 0.50,
    "opposite_side_castling_tendency": 0.60,
    "middlegame_complexity": 0.90,
    "pawn_structure_sharpness": 1.00,
    "material_imbalance": 0.90,
    "endgame_likelihood_proxy": 0.40,
}

OPENING_FEATURES = [
    *MATCHER_COLUMNS_V2,
    "final_structure_entropy",
]


@lru_cache(maxsize=1)
def opening_feature_rows() -> list[dict[str, Any]]:
    path = settings.opening_vectors_path
    if not path.exists():
        raise FileNotFoundError(f"Opening feature vectors not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    for row in rows:
        for feature in [
            *MATCHER_COLUMNS_V2,
            *WHITE_MATCHER_COLUMNS_V2,
            *BLACK_MATCHER_COLUMNS_V2,
            "final_structure_entropy",
            "structure_diversity",
        ]:
            row[feature] = optional_float(row.get(feature))
        for feature in MATCHER_COLUMNS_V2:
            if row.get(f"white_{feature}") is None:
                row[f"white_{feature}"] = row.get(feature)
            if row.get(f"black_{feature}") is None:
                row[f"black_{feature}"] = row.get(feature)
        if row.get("final_structure_entropy") is None:
            row["final_structure_entropy"] = row.get("structure_diversity")
        row["structure_distribution"] = decode_distribution_csv(row.get("structure_distribution"))
        row["repertoire_color"] = repertoire_color(row)
        row["line_count"] = optional_int(row.get("line_count"))
    return rows


def build_opening_charts(bundle: Any, target_color: str = "both") -> dict[str, Any]:
    profiles_by_color = getattr(bundle, "player_profiles_by_color", None) or {"both": bundle.player_profile}
    vectors_by_color = getattr(bundle, "matcher_ready_player_vectors", None) or {"both": bundle.matcher_ready_player_vector}
    profile = profiles_by_color.get("both") or bundle.player_profile
    vector = vectors_by_color.get("both") or bundle.matcher_ready_player_vector
    subfeatures = profile.subfeatures
    favourite = favourite_openings(subfeatures)
    groups = {}
    for color in ["white", "black", "both"]:
        color_profile = profiles_by_color.get(color) or profile
        color_vector = vectors_by_color.get(color) or vector
        groups[color] = {
            "top_opening_features": top_opening_features(favourite, target_color=color),
            "opening_characteristics": opening_characteristics(color_vector),
            "top_opening_matches": top_opening_matches(
                color_vector,
                profile=color_profile,
                target_color=color,
                match_mode="cosine",
            ),
        }
    return {
        "favourite_openings": favourite,
        "top_opening_features": groups["both"]["top_opening_features"],
        "opening_characteristics": groups["both"]["opening_characteristics"],
        "top_opening_matches": groups["both"]["top_opening_matches"],
        "opening_report_groups": groups,
    }


def favourite_openings(subfeatures: dict[str, Any]) -> list[OpeningCount]:
    items: list[OpeningCount] = []
    for color, key in [("white", "opening_distribution_white"), ("black", "opening_distribution_black")]:
        distribution = subfeatures.get(key) or {}
        for name, count in sorted(distribution.items(), key=lambda item: item[1], reverse=True):
            if name:
                items.append(OpeningCount(name=str(name), count=int(count), color=color))
    return items


def top_opening_features(favourites: list[OpeningCount], target_color: str = "both") -> list[OpeningFeatureSet]:
    results: list[OpeningFeatureSet] = []
    colors = [target_color] if target_color in {"white", "black"} else ["white", "black"]
    for color in colors:
        color_items = [item for item in favourites if item.color == color][:3]
        for item in color_items:
            family = find_opening_family_row(item.name)
            family_vector = opening_vector_for_color(family, target_color) if family else {}
            features = [
                MetricPoint(
                    key=feature,
                    label=pretty(feature),
                    value=family_vector.get(feature) if feature in MATCHER_COLUMNS_V2 else family.get(feature) if family else None,
                )
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
        for feature in MATCHER_COLUMNS_V2
    ]


def top_opening_matches(
    vector: dict[str, float | None],
    limit: int = 15,
    *,
    profile: Any | None = None,
    target_color: str = "both",
    match_mode: str = "cosine",
    strict_repertoire_filter: bool = False,
) -> list[OpeningMatch]:
    matches: list[OpeningMatch] = []
    normalized_target = target_color if target_color in {"white", "black", "both"} else "both"
    used_vector_color = normalized_target if normalized_target in {"white", "black"} else "global"
    for row in opening_feature_rows():
        row_color = str(row.get("repertoire_color") or "both")
        if strict_repertoire_filter and normalized_target in {"white", "black"} and row_color not in {normalized_target, "both"}:
            continue
        opening_vector = opening_vector_for_color(row, normalized_target)
        cosine_score, used = weighted_cosine_similarity(vector, opening_vector, MATCHER_FEATURE_WEIGHTS)
        dot_score, dot_used = weighted_dot_product_similarity(vector, opening_vector, MATCHER_FEATURE_WEIGHTS)
        if not used:
            used = dot_used
        score = dot_score if match_mode == "dot_product" else cosine_score
        structure_score = (
            structure_distribution_similarity(profile, row)
            if profile is not None
            else None
        )
        matches.append(
            OpeningMatch(
                opening_name=str(row.get("opening_name") or ""),
                similarity_score=score,
                weighted_cosine_score=cosine_score,
                dot_product_score=dot_score,
                match_mode="dot_product" if match_mode == "dot_product" else "cosine",
                structure_distribution_similarity=structure_score,
                target_color=normalized_target,
                used_vector_color=used_vector_color,
                eco_values=empty_to_none(row.get("eco_values")),
                line_count=row.get("line_count"),
                representative_pgn=empty_to_none(row.get("representative_pgn")),
                representative_uci=empty_to_none(row.get("representative_uci")),
                fen=uci_to_fen(empty_to_none(row.get("representative_uci"))),
                used_features=used,
            )
        )
    sorted_matches = sorted(
        matches,
        key=lambda item: item.similarity_score if item.similarity_score is not None else -1,
        reverse=True,
    )
    # Deduplicate by name: with the variation-level CSV (~3709 rows) multiple rows
    # can share the same opening_name (same eco-book entry at different plies).
    # Keep only the highest-scoring row per name.
    seen_names: set[str] = set()
    deduped: list[OpeningMatch] = []
    for match in sorted_matches:
        if match.opening_name not in seen_names:
            seen_names.add(match.opening_name)
            deduped.append(match)
        if len(deduped) >= limit:
            break
    return deduped


def top_opening_matches_from_cached_report(
    cache_hash: str,
    *,
    match_mode: str = "cosine",
    target_color: str = "both",
    limit: int = 15,
) -> list[OpeningMatch]:
    cached = ReportCache().get(cache_hash)
    if cached is None:
        raise FileNotFoundError(f"Report cache entry not found: {cache_hash}")
    statistics_bundle = ((cached.get("report") or {}).get("statistics_bundle") or {})
    normalized_target = target_color if target_color in {"white", "black", "both"} else "both"
    vectors_by_color = statistics_bundle.get("matcher_ready_player_vectors") or {}
    vector = vectors_by_color.get(normalized_target) or statistics_bundle.get("matcher_ready_player_vector") or {}
    profiles_by_color = statistics_bundle.get("player_profiles_by_color") or {}
    profile_data = profiles_by_color.get(normalized_target) or statistics_bundle.get("player_profile") or {}
    profile = type("CachedPlayerProfile", (), {"subfeatures": profile_data.get("subfeatures") or {}})()
    return top_opening_matches(
        vector,
        limit=limit,
        profile=profile,
        target_color=normalized_target,
        match_mode=match_mode,
    )


def find_opening_family_row(opening_name: str) -> dict[str, Any] | None:
    rows = opening_feature_rows()
    exact = next((row for row in rows if row.get("opening_name") == opening_name), None)
    if exact is not None:
        return exact
    family = opening_name.split(":", 1)[0].strip()
    return next((row for row in rows if row.get("opening_name") == family), None)


def cosine_similarity(row: dict[str, Any], vector: dict[str, float | None]) -> tuple[float | None, list[str]]:
    return unweighted_cosine_similarity(row, vector)


def unweighted_cosine_similarity(row: dict[str, Any], vector: dict[str, float | None]) -> tuple[float | None, list[str]]:
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


def weighted_cosine_similarity(
    a: dict[str, float | None],
    b: dict[str, Any],
    weights: dict[str, float],
) -> tuple[float | None, list[str]]:
    keys = [
        key
        for key in weights
        if a.get(key) is not None and optional_float(b.get(key)) is not None
    ]
    if not keys:
        return None, []
    dot = sum(weights[key] * float(a[key]) * float(optional_float(b.get(key))) for key in keys)
    norm_a = sum(weights[key] * float(a[key]) * float(a[key]) for key in keys) ** 0.5
    norm_b = sum(weights[key] * float(optional_float(b.get(key))) * float(optional_float(b.get(key))) for key in keys) ** 0.5
    if norm_a <= 0 or norm_b <= 0:
        return None, keys
    return dot / (norm_a * norm_b), keys


def weighted_dot_product_similarity(
    a: dict[str, float | None],
    b: dict[str, Any],
    weights: dict[str, float],
) -> tuple[float | None, list[str]]:
    keys = [
        key
        for key in weights
        if a.get(key) is not None and optional_float(b.get(key)) is not None
    ]
    if not keys:
        return None, []
    return sum(weights[key] * float(a[key]) * float(optional_float(b.get(key))) for key in keys), keys


def structure_distribution_similarity(profile: Any, opening_row: dict[str, Any]) -> float | None:
    player_counts = getattr(profile, "subfeatures", {}).get("structure_distribution", {})
    opening_counts = opening_row.get("structure_distribution") or {}
    if not player_counts or not opening_counts:
        return None
    return histogram_intersection(
        normalize_distribution({str(key): int(value) for key, value in player_counts.items()}),
        normalize_distribution({str(key): int(value) for key, value in opening_counts.items()}),
    )


def repertoire_color(row: dict[str, Any]) -> str:
    name = str(row.get("opening_name") or "").lower()
    if "defense" in name or "defence" in name or "countergambit" in name:
        return "black"
    if "opening" in name or "attack" in name or "game" in name:
        return "white"
    return "both"


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
