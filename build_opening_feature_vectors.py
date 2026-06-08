from __future__ import annotations

import argparse

from utils.opening_feature_transformer import (
    DEFAULT_STOCKFISH_PATH,
    compute_opening_groups,
    load_opening_lines,
    write_feature_distribution_diagnostics,
    write_group_features,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build calibrated aggregated opening feature vectors and feature distribution diagnostics."
    )
    parser.add_argument("--dataset", default="openings_dataset/all.tsv")
    parser.add_argument("--stockfish-path", default=DEFAULT_STOCKFISH_PATH)
    parser.add_argument("--output", default="openings_dataset/opening_feature_vectors.csv")
    parser.add_argument("--diagnostics-dir", default="openings_dataset/diagnostics/feature_distributions")
    parser.add_argument("--engine-depth", type=int, default=10)
    parser.add_argument("--multipv", type=int, default=3)
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

    groups, _line_features = compute_opening_groups(
        lines,
        stockfish_path=args.stockfish_path,
        engine_depth=args.engine_depth,
        multipv=args.multipv,
        max_lines_per_group=args.max_lines_per_group,
        show_progress=not args.no_progress,
    )
    write_group_features(args.output, groups)
    diagnostics = write_feature_distribution_diagnostics(groups, args.diagnostics_dir)

    print(f"Wrote {len(groups)} opening feature rows to {args.output}")
    print(f"Wrote {len(diagnostics)} feature distribution diagnostics to {args.diagnostics_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
