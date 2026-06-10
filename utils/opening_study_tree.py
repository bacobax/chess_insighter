"""Opening Study Suggestion Tree.

This is an *additive* analysis module. It powers an interactive, lazily-expanded
decision tree that suggests which opening moves a given player should study,
based on calibrated opening feature vectors and a precomputed player vector.

It is **not** an engine-best-move tree. Nodes are scored on style matching and
calibrated opening characteristics (aggressiveness, gambit volatility proxy,
memorisation cost, systemness). Engine soundness can be layered on later but must
not dominate this feature.

The module is intentionally dependency-light (csv, math, python-chess) and does
not import from the FastAPI ``backend`` package so it can be reused from scripts,
notebooks and tests.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional, Sequence

import chess

from utils.opening_feature_transformer import (
    MATCHER_COLUMNS_V2,
    opening_vector_for_color,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Weights used for the weighted-cosine style match. These mirror the weights in
# ``backend.services.openings_service.MATCHER_FEATURE_WEIGHTS`` so the study tree
# and the flat opening matcher agree on what "style similarity" means.
MATCHER_FEATURE_WEIGHTS: dict[str, float] = {
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

# Default study-score weights. Keys map to the (snake_case) request payload.
# Note: ``memory_simplicity`` is applied to ``(1 - memory_complexity)``.
DEFAULT_STUDY_WEIGHTS: dict[str, float] = {
    "player_style_match": 0.40,
    "aggressiveness": 0.18,
    "gambleness": 0.12,
    "systemness": 0.15,
    "memory_simplicity": 0.15,
}

# Common White first moves shown at the root when the target colour is Black,
# before any style-based recommendation kicks in.
COMMON_WHITE_FIRST_MOVES: tuple[str, ...] = ("e2e4", "d2d4", "c2c4", "g1f3")

# Coverage shrink: a family with ≥ COVERAGE_FULL catalogued lines is considered
# fully evidenced; sparser families are blended toward the dataset median.
COVERAGE_FULL: int = 12

# Human-readable labels for feature keys (used in breakdown data).
_FEATURE_LABELS: dict[str, str] = {
    "tactical_density": "Tactical density",
    "quiet_position_density": "Quiet positions",
    "king_safety_risk": "King risk",
    "early_castling_tendency": "Early castling",
    "opposite_side_castling_tendency": "Opp. castling",
    "middlegame_complexity": "Complexity",
    "pawn_structure_sharpness": "Pawn sharpness",
    "material_imbalance": "Material imb.",
    "endgame_likelihood_proxy": "Endgame",
    "structure_diversity": "Structure diversity",
    "final_structure_entropy": "Position entropy",
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OpeningStudyTreeRequest:
    username: str | None
    player_vector_cache_path: str | None
    opening_vectors_path: str
    target_color: str
    prefix_uci: list[str]
    top_k: int
    max_depth: int | None
    weights: dict[str, float]


@dataclass(frozen=True)
class OpeningStudyTreeNode:
    move_uci: str
    move_san: str
    fen: str
    prefix_uci: list[str]
    compatible_line_count: int
    opening_names: list[str]
    representative_uci: str | None
    representative_pgn: str | None
    player_style_match: float
    aggressiveness: float
    gambleness: float
    memory_complexity: float
    systemness: float
    study_score: float
    side_to_move: str
    target_color: str
    is_target_move: bool
    board_preview_fen: str
    stats: dict[str, float] = field(default_factory=dict)
    breakdown: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "moveUci": self.move_uci,
            "moveSan": self.move_san,
            "fen": self.fen,
            "prefixUci": list(self.prefix_uci),
            "compatibleLineCount": self.compatible_line_count,
            "openingNames": list(self.opening_names),
            "representativeUci": self.representative_uci,
            "representativePgn": self.representative_pgn,
            "playerStyleMatch": self.player_style_match,
            "aggressiveness": self.aggressiveness,
            "gambleness": self.gambleness,
            "memoryComplexity": self.memory_complexity,
            "systemness": self.systemness,
            "studyScore": self.study_score,
            "sideToMove": self.side_to_move,
            "targetColor": self.target_color,
            "isTargetMove": self.is_target_move,
            "boardPreviewFen": self.board_preview_fen,
            "stats": dict(self.stats),
            "breakdown": dict(self.breakdown),
        }


class PlayerVectorFeatureMismatch(ValueError):
    """Raised when a player vector shares no comparable features with the
    opening matcher feature space."""


# ---------------------------------------------------------------------------
# Small numeric helpers
# ---------------------------------------------------------------------------


def clamp01(value: float) -> float:
    if value != value:  # NaN guard
        return 0.0
    return max(0.0, min(1.0, value))


def _optional_float(value: Any) -> float | None:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    try:
        return None if value in (None, "") else int(value)
    except (TypeError, ValueError):
        return None


def _empty_to_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


# ---------------------------------------------------------------------------
# Opening vector loading
# ---------------------------------------------------------------------------

_AGG_FEATURES = [
    *MATCHER_COLUMNS_V2,
    *(f"white_{c}" for c in MATCHER_COLUMNS_V2),
    *(f"black_{c}" for c in MATCHER_COLUMNS_V2),
    "final_structure_entropy",
    "structure_diversity",
    # Worst-case line counts: calibrated [0,1], None on legacy CSV.
    "white_worst_line_count",
    "black_worst_line_count",
    # Raw integer counts (pre-log2), for human-readable display.
    "white_worst_line_count_raw_int",
    "black_worst_line_count_raw_int",
]


@lru_cache(maxsize=8)
def _load_opening_rows(opening_vectors_path: str) -> tuple[dict[str, Any], ...]:
    """Load and parse the feature-vector CSV (one row per opening family)."""
    path = Path(opening_vectors_path)
    if not path.exists():
        raise FileNotFoundError(f"Opening feature vectors not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        raw_rows = list(csv.DictReader(handle))

    rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        row: dict[str, Any] = dict(raw)
        for feature in _AGG_FEATURES:
            row[feature] = _optional_float(raw.get(feature))
        for feature in MATCHER_COLUMNS_V2:
            if row.get(f"white_{feature}") is None:
                row[f"white_{feature}"] = row.get(feature)
            if row.get(f"black_{feature}") is None:
                row[f"black_{feature}"] = row.get(feature)
        if row.get("final_structure_entropy") is None:
            row["final_structure_entropy"] = row.get("structure_diversity")
        row["line_count"] = _optional_int(raw.get("line_count")) or 0
        row["_uci_moves"] = _safe_uci_tokens(raw.get("representative_uci"))
        row["white_worst_line_count"] = _optional_float(raw.get("white_worst_line_count"))
        row["black_worst_line_count"] = _optional_float(raw.get("black_worst_line_count"))
        row["white_worst_line_count_raw_int"] = _optional_int(raw.get("white_worst_line_count_raw_int"))
        row["black_worst_line_count_raw_int"] = _optional_int(raw.get("black_worst_line_count_raw_int"))
        rows.append(row)
    return tuple(rows)


@lru_cache(maxsize=8)
def _load_all_lines(opening_vectors_path: str) -> tuple[dict[str, Any], ...]:
    """Load all.tsv (3 700+ individual opening lines) and attach each line to its
    family's feature vector.

    Using the full TSV instead of the 148 representative lines gives the
    expansion algorithm many more distinct next-move candidates per position.

    Each returned item has:
    - ``_uci_moves``: validated move list for this specific line
    - ``_family``:    opening family name (TSV name before the first ``:``)
    - ``_fv``:        reference to the family's feature-vector dict (for aggregation)

    Families that have no corresponding feature vector are skipped.
    """
    fv_rows = _load_opening_rows(opening_vectors_path)
    fv_by_family: dict[str, dict[str, Any]] = {
        str(row.get("opening_name") or ""): row for row in fv_rows
    }

    all_tsv = Path(opening_vectors_path).parent / "all.tsv"
    if not all_tsv.exists():
        # Graceful fallback: treat the representative lines as "all lines".
        return fv_rows

    with all_tsv.open("r", encoding="utf-8", newline="") as handle:
        tsv_rows = list(csv.DictReader(handle, delimiter="\t"))

    enriched: list[dict[str, Any]] = []
    for tsv_row in tsv_rows:
        uci_str = str(tsv_row.get("uci") or "").strip()
        uci_moves = _safe_uci_tokens(uci_str)
        if not uci_moves:
            continue
        name = str(tsv_row.get("name") or "").strip()
        family = name.split(":", 1)[0].strip()
        fv = fv_by_family.get(family) or fv_by_family.get(name)
        if fv is None:
            continue
        enriched.append({
            "_uci_moves": uci_moves,
            "_family": family,
            "_fv": fv,
        })
    return tuple(enriched)


def _compute_global_priors(
    fv_rows: Sequence[dict[str, Any]],
) -> tuple[float, float]:
    """Return (median_structure_diversity, median_final_structure_entropy) across all families.

    Used as a Bayesian prior to shrink sparse-family structure signals toward the
    dataset centre, preventing under-catalogued lines from scoring as "perfectly
    systematic / zero memory cost" just because the book records only one line.
    """
    def _median(values: list[float]) -> float:
        if not values:
            return 0.5
        n = len(values)
        mid = n // 2
        return (values[mid - 1] + values[mid]) / 2.0 if n % 2 == 0 else values[mid]

    diversities = sorted(
        float(row["structure_diversity"])
        for row in fv_rows
        if row.get("structure_diversity") is not None
    )
    entropies = sorted(
        float(row["final_structure_entropy"])
        for row in fv_rows
        if row.get("final_structure_entropy") is not None
    )
    return _median(diversities), _median(entropies)


def _safe_uci_tokens(uci_line: str | None) -> list[str]:
    if not uci_line:
        return []
    board = chess.Board()
    tokens: list[str] = []
    for token in str(uci_line).split():
        try:
            move = chess.Move.from_uci(token)
        except ValueError:
            return tokens  # stop at first invalid token, keep what is valid
        if move not in board.legal_moves:
            return tokens
        board.push(move)
        tokens.append(token)
    return tokens


# ---------------------------------------------------------------------------
# Player vector loading
# ---------------------------------------------------------------------------


def load_player_vector_from_cache(
    cache_path: str,
    username: str | None,
) -> dict[str, float]:
    """Load a generalized player vector from a ``player_vectors.json`` cache.

    The cache is keyed by an opaque hash; we look up entries by
    ``cache_key.username`` and pick the most recently created one. The stored
    vector uses generalized (color-agnostic) feature names, which is exactly the
    key space the opening matcher compares against.
    """
    path = Path(cache_path)
    if not path.exists():
        raise FileNotFoundError(f"Player vector cache not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Player vector cache is not valid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected player vector cache format: {path}")

    candidates = []
    for entry in data.values():
        if not isinstance(entry, dict):
            continue
        entry_user = str((entry.get("cache_key") or {}).get("username") or "").strip().lower()
        if username is not None and entry_user != username.strip().lower():
            continue
        vector = entry.get("vector")
        if not isinstance(vector, dict):
            continue
        candidates.append((str(entry.get("created_at") or ""), vector))

    if not candidates:
        if username is None:
            raise ValueError(
                "No username provided and player vector could not be resolved. "
                "Pass a username present in the cache or supply a player vector."
            )
        raise ValueError(f"No cached player vector found for username '{username}'.")

    candidates.sort(key=lambda item: item[0], reverse=True)
    raw_vector = candidates[0][1]
    return {str(key): float(value) for key, value in raw_vector.items() if value is not None}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _normalize_player_vector(player_vector: dict[str, float] | Sequence[float]) -> dict[str, float]:
    if isinstance(player_vector, dict):
        return {str(k): float(v) for k, v in player_vector.items() if v is not None}
    # Sequence / np.ndarray: assume ordered as MATCHER_COLUMNS_V2.
    values = list(player_vector)
    if len(values) < len(MATCHER_COLUMNS_V2):
        raise PlayerVectorFeatureMismatch(
            "Player vector array is shorter than the matcher feature space; "
            "cannot align features safely."
        )
    return {feature: float(values[idx]) for idx, feature in enumerate(MATCHER_COLUMNS_V2)}


def compute_similarity(
    player: dict[str, float],
    opening: dict[str, float | None],
    weights: dict[str, float],
    similarity_type: str = "cosine",
    weighted: bool = True,
) -> float | None:
    """Generic similarity between player and opening feature vectors.

    similarity_type: "cosine" (normalised) or "dot_product" (raw inner product).
    weighted: if False, all feature weights are treated as 1.0.
    """
    keys = [k for k in weights if player.get(k) is not None and opening.get(k) is not None]
    if not keys:
        return None
    w = {k: (weights[k] if weighted else 1.0) for k in keys}
    dot = sum(w[k] * float(player[k]) * float(opening[k]) for k in keys)
    if similarity_type == "dot_product":
        return dot
    norm_p = math.sqrt(sum(w[k] * float(player[k]) ** 2 for k in keys))
    norm_o = math.sqrt(sum(w[k] * float(opening[k]) ** 2 for k in keys))
    if norm_p <= 0 or norm_o <= 0:
        return None
    return dot / (norm_p * norm_o)


def weighted_cosine(
    player: dict[str, float],
    opening: dict[str, float | None],
    weights: dict[str, float],
) -> float | None:
    """Backwards-compatible alias: weighted cosine similarity."""
    return compute_similarity(player, opening, weights, similarity_type="cosine", weighted=True)


def _aggregate_rows(rows: Sequence[dict[str, Any]]) -> dict[str, float | None]:
    """Line-count-weighted aggregate of opening features across compatible rows."""
    aggregate: dict[str, float | None] = {}
    weights = [max(1, int(row.get("line_count") or 0)) for row in rows]
    total = float(sum(weights)) or 1.0
    for feature in _AGG_FEATURES:
        acc = 0.0
        seen = 0.0
        for row, weight in zip(rows, weights):
            value = row.get(feature)
            if value is None:
                continue
            acc += float(value) * weight
            seen += weight
        aggregate[feature] = (acc / seen) if seen > 0 else None
    return aggregate


def compute_node_metrics(
    aggregate: dict[str, float | None],
    player_vector: dict[str, float],
    target_color: str,
    compatible_line_count: int,
    max_line_count: int,
    weights: dict[str, float],
    similarity_type: str = "cosine",
    weighted_matching: bool = True,
    matcher_weights: dict[str, float] | None = None,
    prior_diversity: float = 0.5,
    prior_entropy: float = 0.5,
) -> dict[str, Any]:
    color_vector = opening_vector_for_color(aggregate, target_color)

    effective_matcher_weights = matcher_weights if matcher_weights is not None else MATCHER_FEATURE_WEIGHTS
    style = compute_similarity(
        player_vector, color_vector, effective_matcher_weights,
        similarity_type=similarity_type, weighted=weighted_matching,
    )
    if style is None:
        # No comparable features at all -> hard mismatch, surfaced loudly.
        if not any(player_vector.get(k) is not None for k in MATCHER_FEATURE_WEIGHTS):
            raise PlayerVectorFeatureMismatch(
                "Player vector shares no features with the opening matcher space "
                f"(expected any of {sorted(MATCHER_FEATURE_WEIGHTS)})."
            )
        style = 0.0

    def feat(name: str) -> float:
        value = color_vector.get(name)
        if value is None:
            value = aggregate.get(name)
        return float(value) if value is not None else 0.0

    aggressiveness = clamp01(
        0.35 * feat("tactical_density")
        + 0.25 * feat("middlegame_complexity")
        + 0.20 * feat("opposite_side_castling_tendency")
        + 0.20 * feat("material_imbalance")
    )

    gambleness = clamp01(
        0.40 * feat("material_imbalance")
        + 0.35 * feat("tactical_density")
        + 0.25 * feat("middlegame_complexity")
    )

    structure_diversity = float(aggregate.get("structure_diversity") or 0.0)
    final_entropy = float(aggregate.get("final_structure_entropy") or 0.0)

    # --- Coverage shrink (Part A) ---
    # Trust the book's structure signal in proportion to how many lines are catalogued.
    # Sparse families (lc=1) get blended toward the dataset median so they stop
    # scoring as "zero entropy / zero diversity" i.e. "perfectly systematic + free memory".
    coverage = clamp01(
        math.log2(1.0 + max(compatible_line_count, 0))
        / math.log2(1.0 + COVERAGE_FULL)
    )
    eff_diversity = coverage * structure_diversity + (1.0 - coverage) * prior_diversity
    eff_entropy   = coverage * final_entropy       + (1.0 - coverage) * prior_entropy

    denom = math.log2(1 + max(max_line_count, 1))
    line_count_score = math.log2(1 + max(compatible_line_count, 0)) / denom if denom > 0 else 0.0

    # --- Worst-case line count (Part B/C) ---
    # Calibrated [0,1]; None when the CSV pre-dates the breadth rebuild.
    worst_key = "white_worst_line_count" if target_color == "white" else "black_worst_line_count"
    worst_int_key = f"{target_color}_worst_line_count_raw_int"
    worst_raw = aggregate.get(worst_key)
    worst_val: float | None = clamp01(float(worst_raw)) if worst_raw is not None else None
    worst_int_raw = aggregate.get(worst_int_key)
    worst_int: int | None = int(round(worst_int_raw)) if worst_int_raw is not None else None

    if worst_val is not None:
        # Full formula: engine-measured branching dominates, book count corroborates.
        memory_complexity = clamp01(
            0.45 * worst_val
            + 0.20 * clamp01(line_count_score)
            + 0.20 * eff_diversity
            + 0.15 * eff_entropy
        )
    else:
        # Graceful fallback when the CSV hasn't been rebuilt yet (Part A still applies).
        memory_complexity = clamp01(
            0.55 * clamp01(line_count_score)
            + 0.25 * eff_diversity
            + 0.20 * eff_entropy
        )

    systemness = clamp01(
        0.65 * (1.0 - eff_entropy)
        + 0.35 * (1.0 - eff_diversity)
    )

    style = clamp01(style)

    w = {**DEFAULT_STUDY_WEIGHTS, **(weights or {})}
    weight_sum = sum(abs(v) for v in w.values()) or 1.0
    study_score = (
        w["player_style_match"] * style
        + w["aggressiveness"] * aggressiveness
        + w["gambleness"] * gambleness
        + w["systemness"] * systemness
        + w["memory_simplicity"] * (1.0 - memory_complexity)
    ) / weight_sum

    breakdown: dict[str, Any] = {
        "aggressiveness": [
            {"key": "tactical_density", "label": "Tactical density", "value": round(feat("tactical_density"), 4), "weight": 0.35, "rawValue": round(feat("tactical_density"), 4)},
            {"key": "middlegame_complexity", "label": "Complexity", "value": round(feat("middlegame_complexity"), 4), "weight": 0.25, "rawValue": round(feat("middlegame_complexity"), 4)},
            {"key": "opposite_side_castling_tendency", "label": "Opp. castling", "value": round(feat("opposite_side_castling_tendency"), 4), "weight": 0.20, "rawValue": round(feat("opposite_side_castling_tendency"), 4)},
            {"key": "material_imbalance", "label": "Material imb.", "value": round(feat("material_imbalance"), 4), "weight": 0.20, "rawValue": round(feat("material_imbalance"), 4)},
        ],
        "gambleness": [
            {"key": "material_imbalance", "label": "Material imb.", "value": round(feat("material_imbalance"), 4), "weight": 0.40, "rawValue": round(feat("material_imbalance"), 4)},
            {"key": "tactical_density", "label": "Tactical density", "value": round(feat("tactical_density"), 4), "weight": 0.35, "rawValue": round(feat("tactical_density"), 4)},
            {"key": "middlegame_complexity", "label": "Complexity", "value": round(feat("middlegame_complexity"), 4), "weight": 0.25, "rawValue": round(feat("middlegame_complexity"), 4)},
        ],
        "memoryComplexity": [
            *(
                [{"key": "worst_line_count", "label": "Worst-case lines", "value": round(worst_val, 4), "weight": 0.45, "rawValue": worst_int if worst_int is not None else round(worst_val, 4), "rawUnit": "lines"}]
                if worst_val is not None else []
            ),
            {"key": "line_count_score", "label": "Line count", "value": round(clamp01(line_count_score), 4), "weight": 0.20 if worst_val is not None else 0.55, "rawValue": float(compatible_line_count), "rawUnit": "lines"},
            {"key": "structure_diversity", "label": "Structure diversity", "value": round(eff_diversity, 4), "weight": 0.20 if worst_val is not None else 0.25, "rawValue": round(structure_diversity, 4)},
            {"key": "final_structure_entropy", "label": "Position entropy", "value": round(eff_entropy, 4), "weight": 0.15 if worst_val is not None else 0.20, "rawValue": round(final_entropy, 4)},
            {"key": "coverage", "label": "Evidence coverage", "value": round(coverage, 4), "weight": 0.0, "rawValue": float(compatible_line_count), "rawUnit": "lines"},
        ],
        "systemness": [
            {"key": "final_structure_entropy_inv", "label": "1 − entropy", "value": round(clamp01(1.0 - eff_entropy), 4), "weight": 0.65, "rawValue": round(final_entropy, 4), "rawUnit": "entropy"},
            {"key": "structure_diversity_inv", "label": "1 − diversity", "value": round(clamp01(1.0 - eff_diversity), 4), "weight": 0.35, "rawValue": round(structure_diversity, 4), "rawUnit": "diversity"},
            {"key": "coverage", "label": "Evidence coverage", "value": round(coverage, 4), "weight": 0.0, "rawValue": float(compatible_line_count), "rawUnit": "lines"},
        ],
        "playerStyleMatch": [
            {
                "key": k,
                "label": _FEATURE_LABELS.get(k, k),
                "playerValue": round(float(player_vector.get(k, 0.0)), 4),
                "openingValue": round(float(color_vector.get(k) if color_vector.get(k) is not None else 0.0), 4),
                "weight": float(effective_matcher_weights.get(k, 1.0) if weighted_matching else 1.0),
            }
            for k in MATCHER_COLUMNS_V2
            if k in effective_matcher_weights
        ],
        "openingFeatures": {
            k: round(float(v if v is not None else (aggregate.get(k) or 0.0)), 4)
            for k in MATCHER_COLUMNS_V2
            for v in [color_vector.get(k)]
        },
    }

    return {
        "player_style_match": style,
        "aggressiveness": aggressiveness,
        "gambleness": gambleness,
        "memory_complexity": memory_complexity,
        "systemness": systemness,
        "study_score": clamp01(study_score),
        "breakdown": breakdown,
    }


# ---------------------------------------------------------------------------
# Tree expansion (single level / lazy)
# ---------------------------------------------------------------------------


def _board_for_prefix(prefix_uci: Sequence[str]) -> chess.Board:
    board = chess.Board()
    for token in prefix_uci:
        try:
            move = chess.Move.from_uci(token)
        except ValueError as exc:
            raise ValueError(f"Invalid UCI move in prefix: '{token}'") from exc
        if move not in board.legal_moves:
            raise ValueError(f"Illegal move in prefix for current position: '{token}'")
        board.push(move)
    return board


def _color_name(turn: bool) -> str:
    return "white" if turn == chess.WHITE else "black"


def _compute_global_max_line(
    all_lines: Sequence[dict[str, Any]],
    fv_by_family: dict[str, dict[str, Any]],
) -> int:
    """Max per-first-move line count across the full corpus.

    Used as a stable normalisation denominator so line_count_score has the same
    reference point at every tree depth (avoids the single-child = 100% artifact).
    """
    depth0_groups: dict[str, dict[str, dict[str, Any]]] = {}
    for line in all_lines:
        moves: list[str] = line["_uci_moves"]
        if not moves:
            continue
        fm = moves[0]
        family: str = line.get("_family") or ""
        fv: dict[str, Any] = line.get("_fv") or fv_by_family.get(family) or {}
        if not fv:
            continue
        depth0_groups.setdefault(fm, {}).setdefault(family, fv)
    if not depth0_groups:
        return 1
    return max(
        sum(int(fv.get("line_count") or 0) for fv in fvs.values())
        for fvs in depth0_groups.values()
    )


def _root_children_for_black(
    player_vector: dict[str, float],
    rows: Sequence[dict[str, Any]],
    weights: dict[str, float],
    global_max_line: int,
    similarity_type: str = "cosine",
    weighted_matching: bool = True,
    matcher_weights: dict[str, float] | None = None,
    prior_diversity: float = 0.5,
    prior_entropy: float = 0.5,
) -> list[OpeningStudyTreeNode]:
    """At the root, when studying Black, surface the common White first moves
    (conditional recommendation): Black's repertoire depends on White's choice."""
    base_board = chess.Board()
    nodes: list[OpeningStudyTreeNode] = []
    groups: dict[str, list[dict[str, Any]]] = {}
    for move in COMMON_WHITE_FIRST_MOVES:
        groups[move] = [row for row in rows if row["_uci_moves"][:1] == [move]]
    max_line = global_max_line
    for move_uci, grp in groups.items():
        move = chess.Move.from_uci(move_uci)
        board = base_board.copy()
        san = board.san(move)
        board.push(move)
        line_count = sum(int(r.get("line_count") or 0) for r in grp)
        if grp:
            aggregate = _aggregate_rows(grp)
            metrics = compute_node_metrics(
                aggregate, player_vector, "black", line_count, max_line, weights,
                similarity_type=similarity_type,
                weighted_matching=weighted_matching,
                matcher_weights=matcher_weights,
                prior_diversity=prior_diversity,
                prior_entropy=prior_entropy,
            )
            best_row = max(grp, key=lambda r: int(r.get("line_count") or 0))
            names = _top_names(grp)
            rep_uci = _empty_to_none(best_row.get("representative_uci"))
            rep_pgn = _empty_to_none(best_row.get("representative_pgn"))
        else:
            metrics = {
                "player_style_match": 0.0,
                "aggressiveness": 0.0,
                "gambleness": 0.0,
                "memory_complexity": 0.0,
                "systemness": 0.0,
                "study_score": 0.0,
                "breakdown": {},
            }
            names, rep_uci, rep_pgn = [], None, None
        nodes.append(
            _make_node(
                move_uci=move_uci,
                move_san=san,
                board=board,
                prefix=[],
                line_count=line_count,
                names=names,
                rep_uci=rep_uci,
                rep_pgn=rep_pgn,
                metrics=metrics,
                target_color="black",
                mover_is_target=False,  # White's move, target is Black
            )
        )
    # Keep the canonical opening order (e4, d4, c4, Nf3) rather than re-sorting:
    # these are presented as fixed "pick White's first move" options.
    return nodes


def _top_names(rows: Sequence[dict[str, Any]], limit: int = 3) -> list[str]:
    ordered = sorted(rows, key=lambda r: int(r.get("line_count") or 0), reverse=True)
    names: list[str] = []
    for row in ordered:
        name = str(row.get("opening_name") or "").strip()
        if name and name not in names:
            names.append(name)
        if len(names) >= limit:
            break
    return names


def _make_node(
    *,
    move_uci: str,
    move_san: str,
    board: chess.Board,
    prefix: list[str],
    line_count: int,
    names: list[str],
    rep_uci: str | None,
    rep_pgn: str | None,
    metrics: dict[str, Any],
    target_color: str,
    mover_is_target: bool,
) -> OpeningStudyTreeNode:
    fen = board.fen()
    stats = {
        "playerStyleMatch": metrics["player_style_match"],
        "aggressiveness": metrics["aggressiveness"],
        "gambleness": metrics["gambleness"],
        "memoryComplexity": metrics["memory_complexity"],
        "systemness": metrics["systemness"],
    }
    return OpeningStudyTreeNode(
        move_uci=move_uci,
        move_san=move_san,
        fen=fen,
        prefix_uci=list(prefix) + [move_uci],
        compatible_line_count=line_count,
        opening_names=names,
        representative_uci=rep_uci,
        representative_pgn=rep_pgn,
        player_style_match=metrics["player_style_match"],
        aggressiveness=metrics["aggressiveness"],
        gambleness=metrics["gambleness"],
        memory_complexity=metrics["memory_complexity"],
        systemness=metrics["systemness"],
        study_score=metrics["study_score"],
        side_to_move=_color_name(board.turn),
        target_color=target_color,
        is_target_move=mover_is_target,
        board_preview_fen=fen,
        stats=stats,
        breakdown=metrics.get("breakdown", {}),
    )


def get_opening_study_tree_children(
    player_vector: dict[str, float],
    opening_vectors_path: str,
    target_color: str,
    prefix_uci: list[str],
    top_k: int,
    opponent_top_k: int | None = None,
    weights: dict[str, float] | None = None,
    similarity_type: str = "cosine",
    weighted_matching: bool = True,
    matcher_weights: dict[str, float] | None = None,
) -> list[OpeningStudyTreeNode]:
    """Compute child suggestion nodes for a single prefix (one level, lazy).

    ``top_k`` limits the player's own candidate moves.
    ``opponent_top_k`` limits opponent responses (defaults to ``top_k``).

    Expansion uses all.tsv (3 700+ individual lines) as the candidate corpus so
    that many distinct next-moves are available per position. Feature vectors are
    aggregated per unique opening family, then averaged across families present
    in the group — this avoids over-weighting families that happen to have many
    TSV lines.
    """
    target = (target_color or "").strip().lower()
    if target not in {"white", "black"}:
        raise ValueError(f"Invalid target color: '{target_color}'. Expected 'white' or 'black'.")

    top_k = max(1, int(top_k))
    opp_k = max(1, int(opponent_top_k)) if opponent_top_k is not None else top_k
    weights = {**DEFAULT_STUDY_WEIGHTS, **(weights or {})}
    player = _normalize_player_vector(player_vector)
    prefix = list(prefix_uci or [])

    board = _board_for_prefix(prefix)

    # Load corpora once; both are @lru_cache so repeated calls are free.
    all_lines = _load_all_lines(opening_vectors_path)
    fv_rows = _load_opening_rows(opening_vectors_path)
    fv_by_family: dict[str, dict[str, Any]] = {
        str(row.get("opening_name") or ""): row for row in fv_rows
    }
    # Compute a stable normalisation ceiling from depth-0 groups so that the
    # same line_count always maps to the same score regardless of tree depth.
    global_max_line = _compute_global_max_line(all_lines, fv_by_family)
    # Dataset-level priors for coverage shrink (see compute_node_metrics).
    prior_diversity, prior_entropy = _compute_global_priors(fv_rows)

    if target == "black" and len(prefix) == 0:
        nodes = _root_children_for_black(
            player, fv_rows, weights, global_max_line,
            similarity_type=similarity_type,
            weighted_matching=weighted_matching,
            matcher_weights=matcher_weights,
            prior_diversity=prior_diversity,
            prior_entropy=prior_entropy,
        )
        return nodes[:opp_k] if opp_k < len(nodes) else nodes

    depth = len(prefix)
    mover_is_target = _color_name(board.turn) == target
    limit = top_k if mover_is_target else opp_k

    # --- Build move groups from the full all.tsv corpus ---
    # Each group maps a next-move UCI to the set of unique opening families
    # whose lines pass through prefix + [next_move].  We collect family names
    # rather than raw rows so that families with many TSV lines don't dominate
    # the feature aggregation.

    # next_move -> ordered list of unique families (first-seen order preserves
    # rough popularity since all.tsv is ordered by eco/name).
    groups: dict[str, dict[str, dict[str, Any]]] = {}  # move -> {family: fv}
    for line in all_lines:
        moves: list[str] = line["_uci_moves"]
        if len(moves) <= depth or moves[:depth] != prefix:
            continue
        next_move = moves[depth]
        family: str = line.get("_family") or ""
        fv: dict[str, Any] = line.get("_fv") or fv_by_family.get(family) or {}
        if not fv:
            continue
        if next_move not in groups:
            groups[next_move] = {}
        # Keep only one entry per family (first seen = highest-priority line).
        if family not in groups[next_move]:
            groups[next_move][family] = fv

    if not groups:
        return []

    # Aggregate line counts per group for memory-complexity normalisation.
    def _group_line_count(family_fvs: dict[str, dict[str, Any]]) -> int:
        return sum(int(fv.get("line_count") or 0) for fv in family_fvs.values())

    max_line = global_max_line

    nodes: list[OpeningStudyTreeNode] = []
    for next_move_uci, family_fvs in groups.items():
        try:
            move = chess.Move.from_uci(next_move_uci)
        except ValueError:
            continue
        if move not in board.legal_moves:
            continue
        child_board = board.copy()
        san = child_board.san(move)
        child_board.push(move)

        fv_list = list(family_fvs.values())
        line_count = _group_line_count(family_fvs)
        aggregate = _aggregate_rows(fv_list)
        metrics = compute_node_metrics(
            aggregate, player, target, line_count, max_line, weights,
            similarity_type=similarity_type,
            weighted_matching=weighted_matching,
            matcher_weights=matcher_weights,
            prior_diversity=prior_diversity,
            prior_entropy=prior_entropy,
        )
        best_fv = max(fv_list, key=lambda r: int(r.get("line_count") or 0))
        names = [
            str(fv.get("opening_name") or "")
            for fv in sorted(fv_list, key=lambda r: -int(r.get("line_count") or 0))
            if fv.get("opening_name")
        ][:3]
        nodes.append(
            _make_node(
                move_uci=next_move_uci,
                move_san=san,
                board=child_board,
                prefix=prefix,
                line_count=line_count,
                names=names,
                rep_uci=_empty_to_none(best_fv.get("representative_uci")),
                rep_pgn=_empty_to_none(best_fv.get("representative_pgn")),
                metrics=metrics,
                target_color=target,
                mover_is_target=mover_is_target,
            )
        )

    nodes.sort(key=lambda node: node.study_score, reverse=True)
    return nodes[:limit]
