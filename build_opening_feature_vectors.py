from __future__ import annotations

import argparse

from utils.opening_feature_distribution_tools import (
    rank_calibrate_opening_group_features,
    write_feature_distribution_diagnostics_with_raw,
    write_group_features_with_raw,
)
from utils.opening_feature_transformer import (
    BREADTH_CP_THRESHOLD,
    BREADTH_DEPTH,
    BREADTH_MAX_PLIES,
    BREADTH_MAX_START_PLY,
    BREADTH_MULTIPV,
    BREADTH_NODE_BUDGET,
    DEFAULT_STOCKFISH_PATH,
    compute_opening_groups,
    load_opening_lines,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build raw/calibrated opening feature vectors and feature distribution diagnostics."
    )

    parser.add_argument("--dataset", default="openings_dataset/all.tsv")
    parser.add_argument("--stockfish-path", default=DEFAULT_STOCKFISH_PATH)
    parser.add_argument("--output", default="openings_dataset/opening_feature_vectors.csv")
    parser.add_argument(
        "--diagnostics-dir",
        default="openings_dataset/diagnostics/feature_distributions",
    )
    parser.add_argument("--engine-depth", type=int, default=10)
    parser.add_argument("--multipv", type=int, default=3)

    parser.add_argument(
        "--calibration",
        choices=["rank", "percentile", "none"],
        default="rank",
        help=(
            "Calibration strategy for matcher columns. "
            "rank spreads ordered values by empirical CDF; "
            "percentile uses the existing transformer percentile calibration; "
            "none writes raw values as matcher values."
        ),
    )

    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable tqdm progress bars.",
    )

    parser.add_argument(
        "--max-lines-per-group",
        type=int,
        default=None,
        help="Optional cap for faster exploratory runs. Omit for full production output.",
    )

    parser.add_argument(
        "--no-breadth",
        action="store_true",
        help="Skip the worst-case line-count post-pass (faster; leaves breadth columns at 0).",
    )
    parser.add_argument(
        "--breadth-depth",
        type=int,
        default=BREADTH_DEPTH,
        help="Engine depth used for branching estimation during the breadth post-pass.",
    )
    parser.add_argument(
        "--breadth-multipv",
        type=int,
        default=BREADTH_MULTIPV,
        help="Number of top moves sampled per position during the breadth post-pass.",
    )
    parser.add_argument(
        "--breadth-cp-threshold",
        type=int,
        default=BREADTH_CP_THRESHOLD,
        help="CP gap from best move; moves within threshold count as 'reasonable'.",
    )
    parser.add_argument(
        "--breadth-max-plies",
        type=int,
        default=BREADTH_MAX_PLIES,
        help="Walk plies from the truncated start position (default 4; keep ≤6 for tractability).",
    )
    parser.add_argument(
        "--breadth-max-start-ply",
        type=int,
        default=BREADTH_MAX_START_PLY,
        help=(
            "Truncate representative UCI to this many half-moves before starting the walk. "
            "Prevents long lines (e.g. Ruy Lopez at ply 36) from yielding remaining=0. "
            "Default 8 — all families get a full BREADTH_MAX_PLIES walk."
        ),
    )
    parser.add_argument(
        "--breadth-node-budget",
        type=int,
        default=BREADTH_NODE_BUDGET,
        help="Per-(family, color) node limit to cap breadth-pass runtime.",
    )

    parser.add_argument(
        "--grouping",
        choices=["variation", "family"],
        default="variation",
        help=(
            "Aggregation strategy. "
            "'variation' (default) emits one row per named opening line (~3709 rows), "
            "aggregated over the line's subtree — gives the study tree distinct feature "
            "vectors per variation. "
            "'family' emits one row per opening family (148 rows, legacy behaviour)."
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    lines = load_opening_lines(args.dataset)

    raw_groups, _line_features = compute_opening_groups(
        lines,
        stockfish_path=args.stockfish_path,
        engine_depth=args.engine_depth,
        multipv=args.multipv,
        max_lines_per_group=args.max_lines_per_group,
        show_progress=not args.no_progress,
        calibrate=False,
        compute_breadth=not args.no_breadth,
        breadth_depth=args.breadth_depth,
        breadth_multipv=args.breadth_multipv,
        breadth_cp_threshold=args.breadth_cp_threshold,
        breadth_max_plies=args.breadth_max_plies,
        breadth_max_start_ply=args.breadth_max_start_ply,
        breadth_node_budget=args.breadth_node_budget,
        grouping=args.grouping,
    )

    if args.calibration == "rank":
        calibrated_groups = rank_calibrate_opening_group_features(raw_groups)
    elif args.calibration == "percentile":
        calibrated_groups, _ = compute_opening_groups(
            lines,
            stockfish_path=args.stockfish_path,
            engine_depth=args.engine_depth,
            multipv=args.multipv,
            max_lines_per_group=args.max_lines_per_group,
            show_progress=not args.no_progress,
            calibrate=True,
            grouping=args.grouping,
        )
    else:
        calibrated_groups = raw_groups

    write_group_features_with_raw(args.output, raw_groups, calibrated_groups)

    diagnostics = write_feature_distribution_diagnostics_with_raw(
        raw_groups,
        calibrated_groups,
        args.diagnostics_dir,
    )

    print(f"Wrote {len(calibrated_groups)} opening feature rows to {args.output}")
    print(f"Wrote {len(diagnostics)} feature distribution diagnostics to {args.diagnostics_dir}")
    print(f"Calibration strategy: {args.calibration}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())