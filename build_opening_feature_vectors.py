from __future__ import annotations

import argparse

from utils.opening_feature_distribution_tools import (
    rank_calibrate_opening_group_features,
    write_feature_distribution_diagnostics_with_raw,
    write_group_features_with_raw,
)
from utils.opening_feature_transformer import (
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