from __future__ import annotations

import argparse

from utils.opening_feature_transformer import (
    DEFAULT_STOCKFISH_PATH,
    compute_gt_groups,
    compute_opening_groups,
    diagonal_failures,
    diagonal_report,
    load_gt_rows,
    load_opening_lines,
    similarity_matrix,
    write_group_features,
    write_similarity_matrix,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build aggregated opening feature vectors and validate them against a GT testset."
    )
    parser.add_argument("--dataset", default="openings_dataset/all.tsv")
    parser.add_argument("--testset", default="openings_dataset/chess_opening_vector_testset_20_rows.csv")
    parser.add_argument("--stockfish-path", default=DEFAULT_STOCKFISH_PATH)
    parser.add_argument("--output", default="openings_dataset/opening_feature_vectors.csv")
    parser.add_argument("--similarity-output", default="openings_dataset/opening_feature_similarity_matrix.csv")
    parser.add_argument("--engine-depth", type=int, default=10)
    parser.add_argument("--multipv", type=int, default=3)
    parser.add_argument(
        "--strict-similarity",
        action="store_true",
        help="Exit non-zero when any GT row's diagonal similarity is not its row maximum.",
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

    groups, _line_features = compute_opening_groups(
        lines,
        stockfish_path=args.stockfish_path,
        engine_depth=args.engine_depth,
        multipv=args.multipv,
        max_lines_per_group=args.max_lines_per_group,
        show_progress=not args.no_progress,
    )
    write_group_features(args.output, groups)

    gt_rows = load_gt_rows(args.testset)
    gt_groups = compute_gt_groups(
        lines,
        gt_rows,
        stockfish_path=args.stockfish_path,
        engine_depth=args.engine_depth,
        multipv=args.multipv,
        max_lines_per_group=args.max_lines_per_group,
        show_progress=not args.no_progress,
    )
    matrix = similarity_matrix(gt_rows, gt_groups)
    write_similarity_matrix(args.similarity_output, gt_rows, gt_groups, matrix)

    print(f"Wrote {len(groups)} opening feature rows to {args.output}")
    print(f"Wrote {len(matrix)}x{len(gt_groups)} similarity matrix to {args.similarity_output}")
    print("GT diagonal check:")
    for line in diagonal_report(gt_rows, matrix):
        print(line)

    failures = diagonal_failures(gt_rows, matrix)
    if args.strict_similarity and failures:
        print(f"Strict similarity failed for {len(failures)} openings.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
