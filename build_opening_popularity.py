#!/usr/bin/env python3
"""Build the Lichess popularity snapshot used by Opening Lab.

The command is deliberately serial and resumable. Explorer responses and engine
analyses are checkpointed under ``.cache/``; only the compact CSV snapshot,
manifest, and enriched opening feature CSV are intended to be versioned.
"""

from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import chess
import chess.engine
import requests

from utils.opening_popularity import (
    MIN_POPULARITY_GAMES,
    POPULARITY_FILENAME,
    POPULARITY_MANIFEST_FILENAME,
    empirical_midrank_percentiles,
    position_key,
    weighted_practical_gamble,
)
from utils.opening_study_tree import cp_to_utility


EXPLORER_URL = "https://explorer.lichess.org/lichess"
SPEEDS = ("blitz", "rapid")
RATINGS = (1200, 1400, 1600, 1800, 2000)
MAX_MOVES = 50
ENGINE_DEPTH = 8
SNAPSHOT_COLUMNS = (
    "position_epd",
    "fen",
    "total_games",
    "covered_games",
    "coverage",
    "moves_json",
    "white_practical_gamble_raw",
    "white_practical_gamble",
    "white_practical_gamble_games",
    "white_practical_gamble_coverage",
    "black_practical_gamble_raw",
    "black_practical_gamble",
    "black_practical_gamble_games",
    "black_practical_gamble_coverage",
)
ENRICHMENT_COLUMNS = (
    "lichess_position_games",
    "lichess_position_share",
    "lichess_parent_move_share",
    "white_practical_gamble_raw",
    "white_practical_gamble",
    "white_practical_gamble_games",
    "black_practical_gamble_raw",
    "black_practical_gamble",
    "black_practical_gamble_games",
)


@dataclass(frozen=True)
class EnginePositionAnalysis:
    best_move: str | None
    white_cp_by_move: dict[str, float]


@dataclass(frozen=True)
class DirectMetric:
    target_color: str
    raw: float | None
    sample_size: int
    coverage: float


def _month_index(year: int, month: int) -> int:
    return year * 12 + month - 1


def _month_from_index(value: int) -> str:
    year, zero_month = divmod(value, 12)
    return f"{year:04d}-{zero_month + 1:02d}"


def default_window(now: datetime | None = None) -> tuple[str, str]:
    current = now or datetime.now(timezone.utc)
    last_complete = _month_index(current.year, current.month) - 1
    return _month_from_index(last_complete - 23), _month_from_index(last_complete)


def board_from_epd(epd: str) -> chess.Board:
    return chess.Board(f"{epd} 0 1")


def collect_catalog_positions(all_tsv: Path) -> dict[str, chess.Board]:
    positions: dict[str, chess.Board] = {}
    root = chess.Board()
    positions[position_key(root)] = root
    with all_tsv.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            board = chess.Board()
            for token in str(row.get("uci") or "").split():
                try:
                    move = chess.Move.from_uci(token)
                except ValueError:
                    break
                if move not in board.legal_moves:
                    break
                board.push(move)
                positions.setdefault(position_key(board), board.copy())
    return positions


def _cache_name(epd: str) -> str:
    return hashlib.sha256(epd.encode("utf-8")).hexdigest() + ".json"


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(path)


def _token() -> str | None:
    token = os.environ.get("LICHESS_API_TOKEN", "").strip()
    if token:
        return token
    if sys.stdin.isatty():
        entered = getpass.getpass("Lichess API token (not stored): ").strip()
        return entered or None
    return None


def fetch_explorer_position(
    board: chess.Board,
    *,
    cache_dir: Path,
    session: requests.Session,
    token: str | None,
    since: str,
    until: str,
    request_delay: float,
    max_retries: int = 8,
) -> dict[str, Any]:
    epd = position_key(board)
    cache_path = cache_dir / _cache_name(epd)
    cached = _read_json(cache_path)
    if isinstance(cached, dict):
        return cached
    if not token:
        raise RuntimeError(
            "LICHESS_API_TOKEN is required for uncached Explorer positions. "
            "Set it in the environment or run this command interactively."
        )

    params = {
        "variant": "standard",
        "fen": board.fen(),
        "speeds": ",".join(SPEEDS),
        "ratings": ",".join(str(rating) for rating in RATINGS),
        "since": since,
        "until": until,
        "moves": MAX_MOVES,
        "topGames": 0,
        "recentGames": 0,
    }
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    for attempt in range(max_retries + 1):
        try:
            response = session.get(EXPLORER_URL, params=params, headers=headers, timeout=45)
        except requests.RequestException as exc:
            if attempt >= max_retries:
                raise RuntimeError("Lichess Explorer transport failed after retries") from exc
            time.sleep(min(60.0, 2.0 ** attempt))
            continue
        if response.status_code == 200:
            try:
                payload = response.json()
            except requests.JSONDecodeError as exc:
                raise RuntimeError("Lichess Explorer returned malformed JSON") from exc
            if not isinstance(payload, dict) or not isinstance(payload.get("moves", []), list):
                raise RuntimeError("Lichess Explorer returned an unexpected response shape")
            _write_json_atomic(cache_path, payload)
            if request_delay > 0:
                time.sleep(request_delay)
            return payload
        if response.status_code in {401, 403}:
            raise RuntimeError("Lichess Explorer rejected the OAuth token")
        if response.status_code != 429 and response.status_code < 500:
            raise RuntimeError(f"Lichess Explorer failed with HTTP {response.status_code}")
        if attempt >= max_retries:
            raise RuntimeError(f"Lichess Explorer still failing after retries (HTTP {response.status_code})")
        retry_after = response.headers.get("Retry-After")
        try:
            if retry_after:
                wait_seconds = float(retry_after)
            elif response.status_code == 429:
                # Lichess asks clients to wait a full minute after an unannotated
                # rate-limit response rather than probing repeatedly.
                wait_seconds = 60.0
            else:
                wait_seconds = min(60.0, 2.0 ** attempt)
        except ValueError:
            wait_seconds = 60.0 if response.status_code == 429 else min(60.0, 2.0 ** attempt)
        time.sleep(max(1.0, wait_seconds))
    raise AssertionError("retry loop exhausted")


def _score_to_white_cp(score: chess.engine.PovScore | None) -> float | None:
    if score is None:
        return None
    value = score.white().score(mate_score=100_000)
    return float(value) if value is not None else None


def analyse_position(
    board: chess.Board,
    *,
    engine: chess.engine.SimpleEngine,
    depth: int,
    cache_dir: Path,
    engine_name: str,
) -> EnginePositionAnalysis:
    epd = position_key(board)
    cache_path = cache_dir / _cache_name(epd)
    cached = _read_json(cache_path)
    if (
        isinstance(cached, dict)
        and int(cached.get("depth") or 0) == depth
        and str(cached.get("engine_name") or "") == engine_name
    ):
        cp_map = cached.get("white_cp_by_move")
        if isinstance(cp_map, dict):
            return EnginePositionAnalysis(
                best_move=str(cached.get("best_move")) if cached.get("best_move") else None,
                white_cp_by_move={str(k): float(v) for k, v in cp_map.items()},
            )

    legal_count = board.legal_moves.count()
    if legal_count == 0:
        result = EnginePositionAnalysis(None, {})
    else:
        analysed = engine.analyse(
            board,
            chess.engine.Limit(depth=max(1, int(depth))),
            multipv=legal_count,
        )
        infos = analysed if isinstance(analysed, list) else [analysed]
        cp_by_move: dict[str, float] = {}
        ordered_moves: list[str] = []
        for info in infos:
            pv = info.get("pv") if isinstance(info, dict) else None
            if not pv:
                continue
            move_uci = pv[0].uci()
            white_cp = _score_to_white_cp(info.get("score"))
            if white_cp is None:
                continue
            cp_by_move[move_uci] = white_cp
            ordered_moves.append(move_uci)
        result = EnginePositionAnalysis(ordered_moves[0] if ordered_moves else None, cp_by_move)

    _write_json_atomic(
        cache_path,
        {
            "depth": depth,
            "engine_name": engine_name,
            "best_move": result.best_move,
            "white_cp_by_move": result.white_cp_by_move,
        },
    )
    return result


def _games(move: dict[str, Any]) -> int:
    return int(move.get("white") or 0) + int(move.get("draws") or 0) + int(move.get("black") or 0)


def normalized_moves(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int, int]:
    total_games = int(payload.get("white") or 0) + int(payload.get("draws") or 0) + int(payload.get("black") or 0)
    raw_moves = [move for move in payload.get("moves", []) if isinstance(move, dict) and move.get("uci")]
    covered_games = sum(_games(move) for move in raw_moves)
    moves = [
        {
            "uci": str(move["uci"]),
            "games": _games(move),
            "share": (_games(move) / covered_games) if covered_games else 0.0,
        }
        for move in raw_moves
    ]
    return moves, total_games, covered_games


def compute_direct_metric(
    board: chess.Board,
    explorer_payload: dict[str, Any],
    analysis: EnginePositionAnalysis,
    *,
    min_games: int,
) -> DirectMetric:
    target_color = "black" if board.turn == chess.WHITE else "white"
    moves, total_games, _ = normalized_moves(explorer_payload)
    move_games = {str(move["uci"]): int(move["games"]) for move in moves}
    move_utilities = {
        move: cp_to_utility(cp if target_color == "white" else -cp)
        for move, cp in analysis.white_cp_by_move.items()
    }
    if analysis.best_move is None or analysis.best_move not in move_utilities:
        return DirectMetric(target_color, None, 0, 0.0)
    raw, sample_size = weighted_practical_gamble(
        move_games,
        move_utilities,
        move_utilities[analysis.best_move],
        min_games=min_games,
    )
    coverage = sample_size / total_games if total_games else 0.0
    return DirectMetric(target_color, raw, sample_size, coverage)


def _child_after(board: chess.Board, move_uci: str | None) -> chess.Board | None:
    if not move_uci:
        return None
    try:
        move = chess.Move.from_uci(move_uci)
    except ValueError:
        return None
    if move not in board.legal_moves:
        return None
    child = board.copy()
    child.push(move)
    return child


def _metric_fields(metric: DirectMetric | None, percentile: float | None) -> dict[str, Any]:
    if metric is None:
        return {"raw": None, "percentile": None, "games": 0, "coverage": 0.0}
    return {
        "raw": metric.raw,
        "percentile": percentile,
        "games": metric.sample_size,
        "coverage": metric.coverage,
    }


def write_snapshot(
    output_path: Path,
    base_positions: dict[str, chess.Board],
    explorer_payloads: dict[str, dict[str, Any]],
    best_children: dict[str, str],
    direct_metrics: dict[str, DirectMetric],
) -> dict[str, dict[str, Any]]:
    ordered_keys = sorted(base_positions)
    assigned: dict[tuple[str, str], DirectMetric | None] = {}
    ordered_values: list[float | None] = []
    ordered_pairs: list[tuple[str, str]] = []
    for epd in ordered_keys:
        board = base_positions[epd]
        mover = "white" if board.turn == chess.WHITE else "black"
        opponent = "black" if mover == "white" else "white"
        assigned[(epd, opponent)] = direct_metrics.get(epd)
        child_epd = best_children.get(epd)
        assigned[(epd, mover)] = direct_metrics.get(child_epd) if child_epd else None
        for color in ("white", "black"):
            metric = assigned[(epd, color)]
            ordered_pairs.append((epd, color))
            ordered_values.append(metric.raw if metric else None)

    percentile_values = empirical_midrank_percentiles(ordered_values)
    percentiles = dict(zip(ordered_pairs, percentile_values))
    rows_by_epd: dict[str, dict[str, Any]] = {}
    for epd in ordered_keys:
        board = base_positions[epd]
        payload = explorer_payloads[epd]
        moves, total_games, covered_games = normalized_moves(payload)
        white = _metric_fields(assigned[(epd, "white")], percentiles[(epd, "white")])
        black = _metric_fields(assigned[(epd, "black")], percentiles[(epd, "black")])
        rows_by_epd[epd] = {
            "position_epd": epd,
            "fen": board.fen(),
            "total_games": total_games,
            "covered_games": covered_games,
            "coverage": covered_games / total_games if total_games else 0.0,
            "moves_json": json.dumps(moves, sort_keys=True, separators=(",", ":")),
            "white_practical_gamble_raw": white["raw"],
            "white_practical_gamble": white["percentile"],
            "white_practical_gamble_games": white["games"],
            "white_practical_gamble_coverage": white["coverage"],
            "black_practical_gamble_raw": black["raw"],
            "black_practical_gamble": black["percentile"],
            "black_practical_gamble_games": black["games"],
            "black_practical_gamble_coverage": black["coverage"],
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SNAPSHOT_COLUMNS)
        writer.writeheader()
        for epd in ordered_keys:
            writer.writerow(rows_by_epd[epd])
    return rows_by_epd


def _board_for_uci(uci: str) -> tuple[chess.Board, chess.Board | None, str | None]:
    board = chess.Board()
    parent: chess.Board | None = None
    last_move: str | None = None
    for token in uci.split():
        move = chess.Move.from_uci(token)
        if move not in board.legal_moves:
            raise ValueError(f"Illegal representative UCI move: {token}")
        parent = board.copy()
        last_move = token
        board.push(move)
    return board, parent, last_move


def enrich_opening_vectors(
    input_path: Path,
    output_path: Path,
    rows_by_epd: dict[str, dict[str, Any]],
) -> int:
    with input_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    for column in ENRICHMENT_COLUMNS:
        if column not in fieldnames:
            fieldnames.append(column)

    root = rows_by_epd.get(position_key(chess.Board()))
    root_games = int(root["total_games"]) if root else 0
    enriched_count = 0
    for row in rows:
        for column in ENRICHMENT_COLUMNS:
            row[column] = ""
        try:
            board, parent, last_move = _board_for_uci(str(row.get("representative_uci") or ""))
        except (ValueError, AssertionError):
            continue
        record = rows_by_epd.get(position_key(board))
        if record is None:
            continue
        enriched_count += 1
        games = int(record["total_games"])
        row["lichess_position_games"] = games
        row["lichess_position_share"] = games / root_games if root_games else ""
        if parent is not None and last_move:
            parent_record = rows_by_epd.get(position_key(parent))
            if parent_record and int(parent_record["total_games"]):
                moves = json.loads(str(parent_record["moves_json"]))
                move_games = next((int(move["games"]) for move in moves if move.get("uci") == last_move), None)
                if move_games is not None:
                    row["lichess_parent_move_share"] = move_games / int(parent_record["total_games"])
        for color in ("white", "black"):
            row[f"{color}_practical_gamble_raw"] = record[f"{color}_practical_gamble_raw"] if record[f"{color}_practical_gamble_raw"] is not None else ""
            row[f"{color}_practical_gamble"] = record[f"{color}_practical_gamble"] if record[f"{color}_practical_gamble"] is not None else ""
            row[f"{color}_practical_gamble_games"] = record[f"{color}_practical_gamble_games"]

    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(output_path)
    return enriched_count


def _engine_name(engine: chess.engine.SimpleEngine) -> str:
    identifier = getattr(engine, "id", {}) or {}
    return str(identifier.get("name") or "Stockfish")


def _progress(label: str, index: int, total: int) -> None:
    if index == 1 or index == total or index % 100 == 0:
        print(f"{label}: {index}/{total}", flush=True)


def build(args: argparse.Namespace) -> None:
    all_tsv = Path(args.all_tsv).resolve()
    vectors_path = Path(args.vectors).resolve()
    output_path = Path(args.output).resolve()
    manifest_path = Path(args.manifest).resolve()
    cohort = f"{args.since}_{args.until}_{'-'.join(SPEEDS)}_{'-'.join(map(str, RATINGS))}_moves{MAX_MOVES}"
    cache_root = Path(args.cache_dir).resolve() / cohort
    explorer_cache = cache_root / "explorer"
    engine_cache = cache_root / f"engine_depth_{args.depth}"

    base_positions = collect_catalog_positions(all_tsv)
    if args.max_positions:
        keys = sorted(base_positions)[: args.max_positions]
        base_positions = {key: base_positions[key] for key in keys}
    base_items = sorted(base_positions.items())
    if args.engine_only:
        extra_positions: dict[str, chess.Board] = {}
        with chess.engine.SimpleEngine.popen_uci(args.stockfish) as engine:
            engine_name = _engine_name(engine)
            for index, (_epd, board) in enumerate(base_items, 1):
                analysis = analyse_position(
                    board,
                    engine=engine,
                    depth=args.depth,
                    cache_dir=engine_cache,
                    engine_name=engine_name,
                )
                child = _child_after(board, analysis.best_move)
                if child is not None and position_key(child) not in base_positions:
                    extra_positions[position_key(child)] = child
                _progress("Engine base positions", index, len(base_items))
            extra_items = sorted(extra_positions.items())
            for index, (_epd, board) in enumerate(extra_items, 1):
                analyse_position(
                    board,
                    engine=engine,
                    depth=args.depth,
                    cache_dir=engine_cache,
                    engine_name=engine_name,
                )
                _progress("Engine best-move child positions", index, len(extra_items))
        return
    token = _token()
    session = requests.Session()
    explorer_payloads: dict[str, dict[str, Any]] = {}

    for index, (epd, board) in enumerate(base_items, 1):
        explorer_payloads[epd] = fetch_explorer_position(
            board,
            cache_dir=explorer_cache,
            session=session,
            token=token,
            since=args.since,
            until=args.until,
            request_delay=args.request_delay,
        )
        _progress("Explorer base positions", index, len(base_items))

    analyses: dict[str, EnginePositionAnalysis] = {}
    best_children: dict[str, str] = {}
    extra_positions: dict[str, chess.Board] = {}
    with chess.engine.SimpleEngine.popen_uci(args.stockfish) as engine:
        engine_name = _engine_name(engine)
        for index, (epd, board) in enumerate(base_items, 1):
            analysis = analyse_position(
                board,
                engine=engine,
                depth=args.depth,
                cache_dir=engine_cache,
                engine_name=engine_name,
            )
            analyses[epd] = analysis
            child = _child_after(board, analysis.best_move)
            if child is not None:
                child_epd = position_key(child)
                best_children[epd] = child_epd
                if child_epd not in base_positions:
                    extra_positions[child_epd] = child
            _progress("Engine base positions", index, len(base_items))

        extra_items = sorted(extra_positions.items())
        for index, (epd, board) in enumerate(extra_items, 1):
            explorer_payloads[epd] = fetch_explorer_position(
                board,
                cache_dir=explorer_cache,
                session=session,
                token=token,
                since=args.since,
                until=args.until,
                request_delay=args.request_delay,
            )
            analyses[epd] = analyse_position(
                board,
                engine=engine,
                depth=args.depth,
                cache_dir=engine_cache,
                engine_name=engine_name,
            )
            _progress("Best-move child positions", index, len(extra_items))

    all_evaluation_positions = {**base_positions, **extra_positions}
    direct_metrics = {
        epd: compute_direct_metric(
            board,
            explorer_payloads[epd],
            analyses[epd],
            min_games=args.min_games,
        )
        for epd, board in all_evaluation_positions.items()
    }
    rows_by_epd = write_snapshot(
        output_path,
        base_positions,
        explorer_payloads,
        best_children,
        direct_metrics,
    )
    enriched_count = 0
    if not args.skip_enrich:
        enriched_count = enrich_opening_vectors(vectors_path, vectors_path, rows_by_epd)

    valid_white = sum(row["white_practical_gamble"] is not None for row in rows_by_epd.values())
    valid_black = sum(row["black_practical_gamble"] is not None for row in rows_by_epd.values())
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": EXPLORER_URL,
        "filters": {
            "variant": "standard",
            "speeds": list(SPEEDS),
            "ratings": list(RATINGS),
            "since": args.since,
            "until": args.until,
            "moves": MAX_MOVES,
            "minimum_covered_games": args.min_games,
        },
        "engine": {"name": engine_name, "depth": args.depth, "cp_scale": 600.0},
        "coverage": {
            "tree_positions": len(base_positions),
            "best_move_child_positions": len(extra_positions),
            "white_metric_positions": valid_white,
            "black_metric_positions": valid_black,
            "opening_rows_enriched": enriched_count,
        },
        "files": {"snapshot": output_path.name, "opening_vectors": vectors_path.name},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows_by_epd)} positions to {output_path}")
    if not args.skip_enrich:
        print(f"Enriched {enriched_count} opening rows in {vectors_path}")


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    since_default, until_default = default_window()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-tsv", default="openings_dataset/all.tsv")
    parser.add_argument("--vectors", default="openings_dataset/opening_feature_vectors.csv")
    parser.add_argument("--output", default=f"openings_dataset/{POPULARITY_FILENAME}")
    parser.add_argument("--manifest", default=f"openings_dataset/{POPULARITY_MANIFEST_FILENAME}")
    parser.add_argument("--cache-dir", default=".cache/opening_popularity")
    parser.add_argument("--stockfish", default=os.environ.get("STOCKFISH_PATH", "/opt/homebrew/bin/stockfish"))
    parser.add_argument("--since", default=since_default)
    parser.add_argument("--until", default=until_default)
    parser.add_argument("--depth", type=int, default=ENGINE_DEPTH)
    parser.add_argument("--min-games", type=int, default=MIN_POPULARITY_GAMES)
    parser.add_argument("--request-delay", type=float, default=0.1)
    parser.add_argument("--max-positions", type=int, default=None, help="Smoke-test only")
    parser.add_argument("--skip-enrich", action="store_true")
    parser.add_argument("--engine-only", action="store_true", help="Precompute resumable base-position MultiPV caches without network access")
    return parser.parse_args(argv)


if __name__ == "__main__":
    build(parse_args())
