"""Plain-language explanations of Opening Study Tree scores.

The study score is a weighted average of a few criteria whose weights are
normalised to sum to 1 (``resolve_study_weights``). The gap between two moves
therefore splits exactly into one share per criterion::

    score(A) - score(B) = sum_k  weight_k * (criterion_k(A) - criterion_k(B))

Each of the player's candidate moves is compared with the top-ranked sibling
(the top move with the runner-up), and the shares are turned into a sentence
from fixed templates, so explanations are deterministic and testable. The
largest factor is traced one level further, to the opening feature that moves
it most (e.g. "fewer tactical positions").

This module only reads node attributes; it does not import the tree module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

# Shares smaller than this (in score points, 0-100) are left out of sentences.
MIN_FACTOR_POINTS = 0.5
# Score gaps below this (in points) read as "practically tied".
TIE_POINTS = 1.0
# Metric gaps (0-100 scale) for the slightly / clearly / much wording.
CLEARLY_GAP = 5.0
MUCH_GAP = 15.0
# Sibling highlights ("most aggressive of 3") need at least this many options.
MIN_HIGHLIGHT_OPTIONS = 3


@dataclass(frozen=True)
class Criterion:
    key: str  # camelCase key returned to the client
    weight_key: str  # key in the resolved study weights
    label: str
    better: str  # comparative when the move scores higher on this criterion
    worse: str
    superlative_best: str
    superlative_worst: str
    breakdown_key: str | None  # where the feature components live
    invert_breakdown: bool = False  # breakdown measures the opposite direction


CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        "playerStyleMatch", "player_style_match", "Style match",
        "closer to your style", "further from your style",
        "closest to your style", "furthest from your style",
        None,
    ),
    Criterion(
        "aggressiveness", "aggressiveness", "Aggressiveness",
        "more aggressive", "less aggressive",
        "most aggressive", "least aggressive",
        "aggressiveness",
    ),
    Criterion(
        "systemness", "systemness", "Systemness",
        "more systematic", "less systematic",
        "most systematic", "least systematic",
        "systemness",
    ),
    Criterion(
        "memorySimplicity", "memory_simplicity", "Memory simplicity",
        "easier to memorise", "harder to memorise",
        "easiest to memorise", "hardest to memorise",
        "memoryComplexity", invert_breakdown=True,
    ),
)

# (phrase when the feature value is higher, phrase when it is lower)
FEATURE_PHRASES: dict[str, tuple[str, str]] = {
    "tactical_density": ("more tactical positions", "fewer tactical positions"),
    "middlegame_complexity": ("more complex middlegames", "simpler middlegames"),
    "opposite_side_castling_tendency": ("more opposite-side castling", "less opposite-side castling"),
    "material_imbalance": ("more material imbalances", "fewer material imbalances"),
    "worst_line_count": ("more branching in its sharpest line", "less branching in its sharpest line"),
    "line_count_score": ("more catalogued lines", "fewer catalogued lines"),
    "structure_diversity": ("more varied pawn structures", "less varied pawn structures"),
    "final_structure_entropy": ("less predictable positions", "more predictable positions"),
    "final_structure_entropy_inv": ("more predictable positions", "less predictable positions"),
    "structure_diversity_inv": ("fewer distinct pawn structures", "more distinct pawn structures"),
}


def _criterion_value(node: Any, criterion: Criterion) -> float:
    """Criterion value on the 0-100 scale, oriented so higher raises the score."""
    if criterion.key == "playerStyleMatch":
        value = node.player_style_match
    elif criterion.key == "aggressiveness":
        value = node.aggressiveness
    elif criterion.key == "systemness":
        value = node.systemness
    else:
        value = 1.0 - node.memory_complexity
    return 100.0 * float(value)


def _degree(metric_gap: float) -> str:
    gap = abs(metric_gap)
    if gap > MUCH_GAP:
        return "much"
    if gap >= CLEARLY_GAP:
        return "clearly"
    return "slightly"


def _points(value: float) -> str:
    rounded = max(1, round(abs(value)))
    return f"{rounded} point" if rounded == 1 else f"{rounded} points"


def _join(parts: Sequence[str]) -> str:
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def _feature_phrase(node: Any, reference: Any, criterion: Criterion, metric_gap: float) -> str | None:
    """The opening feature that moves this criterion most in the gap's direction."""
    if criterion.breakdown_key is None:
        return None
    mine = {c.get("key"): c for c in (node.breakdown or {}).get(criterion.breakdown_key, [])}
    theirs = {c.get("key"): c for c in (reference.breakdown or {}).get(criterion.breakdown_key, [])}
    # Direction of the underlying breakdown metric (memory complexity runs
    # opposite to memory simplicity).
    direction = -1.0 if criterion.invert_breakdown else 1.0
    wanted = 1.0 if metric_gap * direction > 0 else -1.0
    best_key, best_delta, best_effect = None, 0.0, 0.0
    for key, component in mine.items():
        other = theirs.get(key)
        weight = float(component.get("weight") or 0.0)
        if other is None or weight <= 0.0 or key not in FEATURE_PHRASES:
            continue
        delta = float(component.get("value") or 0.0) - float(other.get("value") or 0.0)
        effect = weight * delta * wanted
        if effect > best_effect:
            best_key, best_delta, best_effect = key, delta, effect
    if best_key is None:
        return None
    higher, lower = FEATURE_PHRASES[best_key]
    return higher if best_delta > 0 else lower


@dataclass(frozen=True)
class _Factor:
    criterion: Criterion
    value: float
    reference_value: float
    contribution: float  # score points, signed for the explained move

    @property
    def metric_gap(self) -> float:
        return self.value - self.reference_value

    def phrase(self, feature: str | None = None) -> str:
        words = self.criterion.better if self.metric_gap > 0 else self.criterion.worse
        text = f"{_degree(self.metric_gap)} {words}"
        return f"{text} ({feature})" if feature else text


def _factors(node: Any, reference: Any, weights: dict[str, float]) -> list[_Factor]:
    factors = []
    for criterion in CRITERIA:
        weight = float(weights.get(criterion.weight_key, 0.0))
        if weight <= 0.0:
            continue
        value = _criterion_value(node, criterion)
        reference_value = _criterion_value(reference, criterion)
        factors.append(_Factor(criterion, value, reference_value, weight * (value - reference_value)))
    return factors


def _summary(node: Any, reference: Any, factors: list[_Factor]) -> str:
    gap = 100.0 * (node.study_score - reference.study_score)
    ref = reference.move_san
    shown = [f for f in factors if abs(f.contribution) >= MIN_FACTOR_POINTS]
    pros = sorted((f for f in shown if f.contribution > 0), key=lambda f: -f.contribution)
    cons = sorted((f for f in shown if f.contribution < 0), key=lambda f: f.contribution)

    if abs(gap) < TIE_POINTS:
        if pros and cons:
            return (
                f"Practically tied with {ref}: it trades being "
                f"{_join([f.phrase() for f in cons])} for being {_join([f.phrase() for f in pros])}."
            )
        if pros or cons:
            return f"Practically tied with {ref}; it is {_join([f.phrase() for f in pros or cons])}."
        return f"Practically tied with {ref}; the two score almost identically on every criterion."

    if gap < 0:
        if not cons:
            return f"Ranks about {_points(gap)} below {ref}."
        lead, rest = cons[0], cons[1:]
        lead_text = lead.phrase(_feature_phrase(node, reference, lead.criterion, lead.metric_gap))
        text = f"Ranks about {_points(gap)} below {ref}. It is {_join([lead_text] + [f.phrase() for f in rest])}"
        if pros:
            text += f", which costs more than it gains from being {_join([f.phrase() for f in pros])}"
        return text + "."

    if not pros:
        return f"Ranks about {_points(gap)} above {ref}."
    lead, rest = pros[0], pros[1:]
    lead_text = lead.phrase(_feature_phrase(node, reference, lead.criterion, lead.metric_gap))
    text = f"Ranks about {_points(gap)} above {ref}, mainly because it is {_join([lead_text] + [f.phrase() for f in rest])}"
    if cons:
        text += f", even though it is {_join([f.phrase() for f in cons])}"
    return text + "."


def _highlights(index: int, nodes: Sequence[Any], weights: dict[str, float]) -> list[str]:
    if len(nodes) < MIN_HIGHLIGHT_OPTIONS:
        return []
    out = []
    for criterion in CRITERIA:
        if float(weights.get(criterion.weight_key, 0.0)) <= 0.0:
            continue
        values = [_criterion_value(node, criterion) for node in nodes]
        mine = values[index]
        if values.count(mine) > 1:
            continue
        if mine == max(values):
            out.append(f"The {criterion.superlative_best} of the {len(nodes)} options")
        elif mine == min(values):
            out.append(f"The {criterion.superlative_worst} of the {len(nodes)} options")
    return out


def _feasibility(metric: str, threshold: float, percentile: float | None) -> str | None:
    if threshold <= 0.0 or percentile is None:
        return None
    check = "practical check" if metric == "practical" else "engine check"
    if percentile >= 0.999:
        best = "the biggest practical edge here" if metric == "practical" else "among the engine's top choices here"
        return f"Passes the {check}: {best}."
    measure = "a bigger practical edge than" if metric == "practical" else "a better engine evaluation than"
    return f"Passes the {check}: {measure} {round(percentile * 100)}% of the alternatives."


def explain_player_moves(
    nodes: Sequence[Any],
    weights: dict[str, float],
    *,
    evaluation_metric: str = "engine",
    threshold: float = 0.0,
    percentiles: dict[str, float | None] | None = None,
) -> list[dict[str, Any]]:
    """Explanations for the player's sibling moves, already sorted by score."""
    percentiles = percentiles or {}
    out: list[dict[str, Any]] = []
    for index, node in enumerate(nodes):
        feasibility = _feasibility(evaluation_metric, threshold, percentiles.get(node.move_uci))
        if len(nodes) == 1:
            out.append({
                "summary": "The only suggested move in this position.",
                "comparedTo": None,
                "scoreGap": None,
                "factors": [],
                "highlights": [],
                "feasibility": feasibility,
            })
            continue
        reference = nodes[1] if index == 0 else nodes[0]
        factors = _factors(node, reference, weights)
        out.append({
            "summary": _summary(node, reference, factors),
            "comparedTo": reference.move_san,
            "scoreGap": round(100.0 * (node.study_score - reference.study_score), 2),
            "factors": [
                {
                    "key": f.criterion.key,
                    "label": f.criterion.label,
                    "value": round(f.value, 2),
                    "referenceValue": round(f.reference_value, 2),
                    "contribution": round(f.contribution, 2),
                }
                for f in factors
            ],
            "highlights": _highlights(index, nodes, weights),
            "feasibility": feasibility,
        })
    return out


_ORDINALS = {2: "second", 3: "third", 4: "fourth", 5: "fifth"}


def explain_opponent_moves(nodes: Sequence[Any], ordering: str) -> list[dict[str, Any]]:
    """Opponent replies are not scored; say why they are listed in this order."""
    out = []
    for index, node in enumerate(nodes):
        played = f"Played in {100.0 * float(node.popularity_score):.1f}% of Lichess games from this position."
        if ordering == "engine":
            rank = "The strongest defence" if index == 0 else (
                f"The {_ORDINALS.get(index + 1, f'#{index + 1}')}-strongest defence"
            )
            summary = f"{rank} by engine evaluation. {played}"
        else:
            summary = played
        out.append({
            "summary": summary,
            "comparedTo": None,
            "scoreGap": None,
            "factors": [],
            "highlights": [],
            "feasibility": None,
        })
    return out
