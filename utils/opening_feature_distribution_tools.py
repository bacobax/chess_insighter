from __future__ import annotations

import csv
import math
from dataclasses import replace
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable

from utils.opening_feature_transformer import (
    BLACK_MATCHER_COLUMNS_V2,
    BREADTH_COLUMNS,
    CALIBRATED_MATCHER_COLUMNS,
    MATCHER_COLUMNS_V2,
    SIDE_MATCHER_COLUMNS_V2,
    WHITE_MATCHER_COLUMNS_V2,
    OpeningGroupFeatureVector,
    encode_distribution_csv,
    round_float,
)

# All columns that should be rank-calibrated: matcher columns + breadth columns.
_ALL_CALIBRATED_COLUMNS: tuple[str, ...] = (*CALIBRATED_MATCHER_COLUMNS, *BREADTH_COLUMNS)


FEATURE_GROUPS: dict[str, list[str]] = {
    "generalized": MATCHER_COLUMNS_V2,
    "white": WHITE_MATCHER_COLUMNS_V2,
    "black": BLACK_MATCHER_COLUMNS_V2,
}


def rank_calibrate_opening_group_features(
    groups: list[OpeningGroupFeatureVector],
    *,
    columns: Iterable[str] = _ALL_CALIBRATED_COLUMNS,
) -> list[OpeningGroupFeatureVector]:
    """
    Empirical-rank calibration.

    Percentile min/max scaling can still produce bad distributions when raw features
    are sparse or clustered. Rank calibration uses the empirical CDF, so the calibrated
    matcher columns spread across [0, 1] whenever the raw feature has real ordering.

    Constant columns are set to 0.5 so they do not create fake distance.
    """
    if not groups:
        return []

    updates_by_index: list[dict[str, float]] = [dict() for _ in groups]

    for column in columns:
        values = [float(getattr(group, column)) for group in groups]
        calibrated = empirical_cdf_values(values)

        for index, value in enumerate(calibrated):
            updates_by_index[index][column] = round_float(value)

    return [
        replace(group, **updates)
        for group, updates in zip(groups, updates_by_index)
    ]


def empirical_cdf_values(values: list[float]) -> list[float]:
    if not values:
        return []

    finite_values = [value for value in values if math.isfinite(value)]
    if len(set(finite_values)) <= 1:
        return [0.5 for _ in values]

    indexed = sorted(enumerate(values), key=lambda item: item[1])
    result = [0.5 for _ in values]
    denominator = max(1, len(indexed) - 1)

    start = 0
    while start < len(indexed):
        end = start
        current_value = indexed[start][1]

        while end + 1 < len(indexed) and indexed[end + 1][1] == current_value:
            end += 1

        rank = ((start + end) / 2.0) / denominator

        for position in range(start, end + 1):
            original_index = indexed[position][0]
            result[original_index] = rank

        start = end + 1

    return result


def write_group_features_with_raw(
    path: str | Path,
    raw_groups: list[OpeningGroupFeatureVector],
    calibrated_groups: list[OpeningGroupFeatureVector],
) -> None:
    if len(raw_groups) != len(calibrated_groups):
        raise ValueError("raw_groups and calibrated_groups must have the same length")

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)

    matcher_columns = [
        *MATCHER_COLUMNS_V2,
        *SIDE_MATCHER_COLUMNS_V2,
    ]

    columns = [
        "opening_name",
        "line_count",
        "eco_values",
        "representative_pgn",
        "representative_uci",
        *[f"raw_{column}" for column in matcher_columns],
        *matcher_columns,
        "raw_final_structure_entropy",
        "final_structure_entropy",
        "raw_structure_diversity",
        "structure_diversity",
        "structure_distribution",
        "raw_white_worst_line_count",
        "white_worst_line_count",
        "white_worst_line_count_raw_int",
        "raw_black_worst_line_count",
        "black_worst_line_count",
        "black_worst_line_count_raw_int",
    ]

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()

        for raw_group, calibrated_group in zip(raw_groups, calibrated_groups):
            row: dict[str, Any] = {
                "opening_name": calibrated_group.opening_name,
                "line_count": calibrated_group.line_count,
                "eco_values": calibrated_group.eco_values,
                "representative_pgn": calibrated_group.representative_pgn,
                "representative_uci": calibrated_group.representative_uci,
                "raw_final_structure_entropy": raw_group.final_structure_entropy,
                "final_structure_entropy": calibrated_group.final_structure_entropy,
                "raw_structure_diversity": raw_group.structure_diversity,
                "structure_diversity": calibrated_group.structure_diversity,
                "structure_distribution": encode_distribution_csv(
                    calibrated_group.structure_distribution
                ),
                "raw_white_worst_line_count": raw_group.white_worst_line_count,
                "white_worst_line_count": calibrated_group.white_worst_line_count,
                "white_worst_line_count_raw_int": raw_group.white_worst_line_count_raw_int,
                "raw_black_worst_line_count": raw_group.black_worst_line_count,
                "black_worst_line_count": calibrated_group.black_worst_line_count,
                "black_worst_line_count_raw_int": raw_group.black_worst_line_count_raw_int,
            }

            for column in matcher_columns:
                row[f"raw_{column}"] = getattr(raw_group, column)
                row[column] = getattr(calibrated_group, column)

            writer.writerow(row)


def write_feature_distribution_diagnostics_with_raw(
    raw_groups: list[OpeningGroupFeatureVector],
    calibrated_groups: list[OpeningGroupFeatureVector],
    output_dir: str | Path,
    *,
    bins: int = 20,
) -> list[Path]:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib is required to write feature distribution diagnostics"
        ) from exc

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    outputs: list[Path] = []
    summary_rows: list[dict[str, Any]] = []

    for value_kind, groups in [
        ("raw", raw_groups),
        ("calibrated", calibrated_groups),
    ]:
        for group_name, columns in FEATURE_GROUPS.items():
            group_dir = destination / value_kind / group_name
            group_dir.mkdir(parents=True, exist_ok=True)

            for column in columns:
                values = [float(getattr(group, column)) for group in groups]
                if not values:
                    continue

                stats = distribution_stats(values)
                summary_rows.append(
                    {
                        "value_kind": value_kind,
                        "group": group_name,
                        "feature": column,
                        **stats,
                    }
                )

                fig, ax = plt.subplots(figsize=(7, 4))

                ax.hist(
                    values,
                    bins=[index / bins for index in range(bins + 1)],
                    range=(0, 1),
                    edgecolor="#ffffff",
                )

                ax.set_xlim(0, 1)
                ax.set_xlabel(f"{value_kind.capitalize()} feature value")
                ax.set_ylabel("Opening families")
                ax.set_title(f"{value_kind}: {group_name}: {column}")

                annotation = (
                    f"n={stats['count']}  "
                    f"mean={stats['mean']:.3f}  "
                    f"median={stats['median']:.3f}\n"
                    f"min={stats['min']:.3f}  "
                    f"p05={stats['p05']:.3f}  "
                    f"p95={stats['p95']:.3f}  "
                    f"max={stats['max']:.3f}\n"
                    f"exact0={stats['pct_exact_0']:.1f}%  "
                    f"exact1={stats['pct_exact_1']:.1f}%  "
                    f"near0={stats['pct_near_0']:.1f}%  "
                    f"near1={stats['pct_near_1']:.1f}%"
                )

                ax.text(
                    0.02,
                    0.95,
                    annotation,
                    transform=ax.transAxes,
                    va="top",
                    ha="left",
                    fontsize=8,
                    bbox={
                        "boxstyle": "round",
                        "facecolor": "white",
                        "alpha": 0.85,
                        "edgecolor": "#cbd5e1",
                    },
                )

                fig.tight_layout()

                output = group_dir / f"{column}.png"
                fig.savefig(output, dpi=140)
                plt.close(fig)

                outputs.append(output)

    summary_path = destination / "feature_distribution_summary.csv"

    if summary_rows:
        with summary_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(summary_rows[0].keys()))
            writer.writeheader()
            writer.writerows(summary_rows)

        outputs.append(summary_path)

    return outputs


def distribution_stats(values: list[float]) -> dict[str, float | int]:
    sorted_values = sorted(values)

    return {
        "count": len(sorted_values),
        "min": sorted_values[0],
        "p05": percentile(sorted_values, 0.05),
        "p25": percentile(sorted_values, 0.25),
        "median": median(sorted_values),
        "mean": mean(sorted_values),
        "p75": percentile(sorted_values, 0.75),
        "p95": percentile(sorted_values, 0.95),
        "max": sorted_values[-1],
        "std": population_std(sorted_values),
        "unique_count": len(set(sorted_values)),
        "pct_exact_0": percentage(value == 0.0 for value in sorted_values),
        "pct_exact_1": percentage(value == 1.0 for value in sorted_values),
        "pct_near_0": percentage(value <= 0.05 for value in sorted_values),
        "pct_near_1": percentage(value >= 0.95 for value in sorted_values),
    }


def percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0

    if len(sorted_values) == 1:
        return sorted_values[0]

    position = (len(sorted_values) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return sorted_values[int(position)]

    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def population_std(values: list[float]) -> float:
    if not values:
        return 0.0

    avg = mean(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) / len(values))


def percentage(flags: Iterable[bool]) -> float:
    items = list(flags)

    if not items:
        return 0.0

    return 100.0 * sum(1 for flag in items if flag) / len(items)