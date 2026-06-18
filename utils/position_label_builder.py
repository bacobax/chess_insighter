"""
position_label_builder.py
=========================
Builds per-position label arrays for training the PositionStyleEncoder.

Two modes controlled by ``LABEL_MODE``:

- ``"lightweight"``  – fully board-only / DB-header signals.  Fast, no Stockfish.
  The eval head is masked (no cp available).
- ``"stockfish"``    – runs the full engine pipeline.  High-quality labels for all
  four heads (style, eval, phase, tactic).

Label generation is a one-time precompute.  Results are saved/loaded from
``data/labels_<mode>.parquet`` keyed by FEN so training restarts instantly.

Public API
----------
    from utils.position_label_builder import build_labels, LABEL_MODE

    labels_df = build_labels(positions_df, mode=LABEL_MODE)
    # Returns a DataFrame row-aligned with positions_df containing columns
    # described in HEAD_SPECS below.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import chess
import numpy as np
import pandas as pd

try:
    from tqdm.auto import tqdm
except ImportError:
    tqdm = None  # type: ignore[assignment]

from utils.position_feature_extractor import (
    extract_position_features,
    heuristic_engine_info,
)
from utils.opening_feature_transformer import (
    MATCHER_COLUMNS_V2,
    isolated_pawns,
    doubled_pawns,
    passed_pawns,
    open_files,
    semi_open_files,
)
from utils.player_vector_cache import classify_phase

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LABEL_MODE = "lightweight"   # override to "stockfish" to enable engine labels

DATA_DIR = Path("data")

# The 9 style dimensions (same order as MATCHER_COLUMNS_V2)
STYLE_COLS = MATCHER_COLUMNS_V2  # 9 names

# Phase classes
PHASE_CLASSES = ["opening", "middlegame", "endgame"]
PHASE_TO_IDX = {c: i for i, c in enumerate(PHASE_CLASSES)}

# Tactic columns (lightweight: 2 binary; stockfish adds 8 more)
TACTIC_COLS_LIGHTWEIGHT = ["tactical", "quiet_middlegame"]
TACTIC_THEMES_STOCKFISH = [
    "check", "double_check", "discovered_check",
    "checkmate_in_k", "fork", "absolute_pin", "skewer", "king_attraction",
]
TACTIC_COLS_STOCKFISH = TACTIC_COLS_LIGHTWEIGHT + TACTIC_THEMES_STOCKFISH

# Eval bucket classes (stockfish mode only)
EVAL_CLASSES = ["losing", "equal", "winning"]   # indices 0,1,2
EVAL_CP_THRESHOLD = 200


# ---------------------------------------------------------------------------
# Structural / board-only helpers (no engine)
# ---------------------------------------------------------------------------

def _san_is_tactical(san: str) -> bool:
    """Heuristic: capture ('x'), check ('+'), checkmate ('#'), promotion ('=')."""
    return any(c in san for c in ("x", "+", "#", "="))


def _board_tactical_density_heuristic(board: chess.Board) -> float:
    """
    Lightweight tactical density proxy.
    Counts forcing moves (captures + checks + promotions) normalised by legal move count.
    Returns [0, 1].
    """
    legal = list(board.legal_moves)
    if not legal:
        return 0.0
    forcing = sum(
        1 for m in legal
        if board.is_capture(m) or board.gives_check(m) or m.promotion is not None
    )
    return min(forcing / len(legal), 1.0)


def _board_is_endgame(board: chess.Board) -> bool:
    queens = (
        len(board.pieces(chess.QUEEN, chess.WHITE))
        + len(board.pieces(chess.QUEEN, chess.BLACK))
    )
    values = {chess.KNIGHT: 300, chess.BISHOP: 300, chess.ROOK: 500, chess.QUEEN: 900}
    npm = sum(
        v * (len(board.pieces(pt, chess.WHITE)) + len(board.pieces(pt, chess.BLACK)))
        for pt, v in values.items()
    )
    return npm <= 2600 or (queens == 0 and npm <= 3600)


# ---------------------------------------------------------------------------
# Lightweight label generation (single position, no engine)
# ---------------------------------------------------------------------------

def _lightweight_labels_for_position(
    fen: str,
    ply: int,
    move_san: Optional[str],
) -> dict:
    """
    Compute all lightweight labels for one position.
    Returns a flat dict of label columns + masks.
    """
    board = chess.Board(fen)
    side = board.turn  # side whose style we capture

    # --- Style (heuristic engine info, engine-free) ---
    feats = extract_position_features(board, side)   # uses heuristic_engine_info inside
    style = {f"style_{col}": float(feats.get(col, 0.0)) for col in STYLE_COLS}

    # --- Phase ---
    in_book = ply <= 10  # conservative opening-book assumption
    phase_str = classify_phase(board, ply, in_book)
    phase_idx = PHASE_TO_IDX[phase_str]

    # --- Tactical / quiet (lightweight) ---
    tactic_density = _board_tactical_density_heuristic(board)
    tactical = int(tactic_density >= 0.30 or (move_san is not None and _san_is_tactical(move_san)))
    quiet_mg = int(
        phase_str == "middlegame"
        and not board.is_check()
        and tactic_density < 0.20
    )

    return {
        **style,
        "phase_idx": phase_idx,
        "tactic_tactical": tactical,
        "tactic_quiet_middlegame": quiet_mg,
        # Masks: 1 = label available, 0 = mask this head
        "mask_style": 1,
        "mask_phase": 1,
        "mask_tactic": 1,
        "mask_eval": 0,      # eval masked in lightweight mode
        "eval_bucket": -1,   # sentinel: not available
    }


# ---------------------------------------------------------------------------
# Stockfish label generation (single position, engine required)
# ---------------------------------------------------------------------------

def _stockfish_labels_for_position(
    fen: str,
    ply: int,
    move_uci: Optional[str],
    engine: "chess.engine.SimpleEngine",  # type: ignore[name-defined]
    engine_cache: Optional[dict] = None,
) -> dict:
    """
    Full engine-assisted labels.  Requires a live Stockfish engine.
    """
    import chess.engine  # local import so module is importable without engine

    from utils.opening_feature_transformer import (
        EnginePositionInfo,
        analyse_position,
    )
    from utils.tactic_detector import detect_tactics, TacticDetectorConfig

    board = chess.Board(fen)
    side = board.turn

    cache: dict = engine_cache if engine_cache is not None else {}

    # --- Engine analysis ---
    try:
        engine_info = analyse_position(
            engine,
            board,
            limit=chess.engine.Limit(depth=12),
            multipv=3,
            cache=cache,
        )
    except Exception:
        engine_info = heuristic_engine_info(board)

    # --- Style (full Stockfish-assisted) ---
    from utils.position_feature_extractor import extract_position_features as _epf
    feats = _epf(board, side, engine, engine_cache=cache)
    style = {f"style_{col}": float(feats.get(col, 0.0)) for col in STYLE_COLS}

    # --- Phase ---
    in_book = ply <= 10
    phase_str = classify_phase(board, ply, in_book)
    phase_idx = PHASE_TO_IDX[phase_str]

    # --- Eval bucket (side-to-move oriented) ---
    raw_cp = engine_info.eval_cp  # White-relative
    if raw_cp is not None:
        cp = raw_cp if side == chess.WHITE else -raw_cp
        if cp >= EVAL_CP_THRESHOLD:
            eval_bucket = 2   # winning
        elif cp <= -EVAL_CP_THRESHOLD:
            eval_bucket = 0   # losing
        else:
            eval_bucket = 1   # equal
        mask_eval = 1
    else:
        eval_bucket = 1   # default equal; mask it
        mask_eval = 0

    # --- Tactics ---
    tactic_density = feats.get("tactical_density", 0.0)
    tactical = int(tactic_density >= 0.55)
    quiet_mg = int(
        phase_str == "middlegame"
        and not board.is_check()
        and feats.get("quiet_position_density", 0.0) >= 0.60
    )

    theme_flags: dict[str, int] = {t: 0 for t in TACTIC_THEMES_STOCKFISH}
    if move_uci is not None:
        try:
            move = chess.Move.from_uci(move_uci)
            gain_cp = engine_info.best_move_cp_gain
            tags = detect_tactics(
                board, move,
                ply_offset=0,
                engine_gain_cp=int(gain_cp) if gain_cp is not None else None,
                config=TacticDetectorConfig(min_engine_gain_cp=80),
            )
            for tag in tags:
                if tag.theme in theme_flags:
                    theme_flags[tag.theme] = 1
        except Exception:
            pass

    return {
        **style,
        "phase_idx": phase_idx,
        "tactic_tactical": tactical,
        "tactic_quiet_middlegame": quiet_mg,
        **{f"tactic_{t}": v for t, v in theme_flags.items()},
        "mask_style": 1,
        "mask_phase": 1,
        "mask_tactic": 1,
        "mask_eval": mask_eval,
        "eval_bucket": eval_bucket,
    }


# ---------------------------------------------------------------------------
# Batch builder
# ---------------------------------------------------------------------------

def build_labels(
    positions_df: pd.DataFrame,
    *,
    mode: str = LABEL_MODE,
    cache_path: Optional[Path] = None,
    stockfish_path: str = "/opt/homebrew/bin/stockfish",
    engine_depth: int = 12,
) -> pd.DataFrame:
    """
    Build (or load from cache) a label DataFrame row-aligned with ``positions_df``.

    Parameters
    ----------
    positions_df : pd.DataFrame
        Must have columns: ``fen``, ``ply`` (int), ``move_san`` (str or None).
        In stockfish mode also uses ``move_uci``.
    mode : "lightweight" | "stockfish"
    cache_path : optional parquet path; defaults to ``data/labels_<mode>.parquet``.
    stockfish_path : path to Stockfish binary (stockfish mode only).
    engine_depth : Stockfish search depth (stockfish mode only).

    Returns
    -------
    pd.DataFrame with the same row count as ``positions_df``, columns:
        style_<feature>  (9 floats, all [0,1])
        phase_idx        (int 0/1/2)
        tactic_tactical  (int 0/1)
        tactic_quiet_middlegame (int 0/1)
        [tactic_<theme>  (int 0/1)  — stockfish mode only]
        eval_bucket      (int 0/1/2 or -1 if masked)
        mask_style, mask_phase, mask_tactic, mask_eval  (int 0/1)
    """
    if cache_path is None:
        cache_path = DATA_DIR / f"labels_{mode}.parquet"

    if cache_path.exists():
        print(f"[label_builder] Loading cached labels from {cache_path}")
        return pd.read_parquet(cache_path)
    # Check CSV fallback
    csv_fallback = cache_path.with_suffix(".csv")
    if csv_fallback.exists():
        print(f"[label_builder] Loading cached labels from {csv_fallback}")
        return pd.read_csv(csv_fallback)

    print(f"[label_builder] Building labels in '{mode}' mode for {len(positions_df)} positions…")

    if mode == "stockfish":
        import chess.engine
        engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)
        engine_cache: dict = {}
    else:
        engine = None
        engine_cache = {}

    rows = []
    iterable = positions_df.itertuples(index=False)
    if tqdm is not None:
        iterable = tqdm(iterable, total=len(positions_df), desc=f"labels/{mode}")

    try:
        for row in iterable:
            fen = row.fen
            ply = int(getattr(row, "ply", 0))
            move_san = getattr(row, "move_san", None)
            move_uci = getattr(row, "move_uci", None)

            try:
                if mode == "stockfish":
                    labels = _stockfish_labels_for_position(
                        fen, ply, move_uci, engine, engine_cache
                    )
                else:
                    labels = _lightweight_labels_for_position(fen, ply, move_san)
            except Exception as exc:
                # Fallback: all-zero labels, all masked
                labels = _fallback_labels(mode, str(exc))

            rows.append(labels)
    finally:
        if engine is not None:
            try:
                engine.quit()
            except Exception:
                pass

    labels_df = pd.DataFrame(rows)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        labels_df.to_parquet(cache_path, index=False)
    except ImportError:
        # Fall back to CSV if pyarrow / fastparquet not installed
        csv_path = cache_path.with_suffix(".csv")
        labels_df.to_csv(csv_path, index=False)
        print(f"[label_builder] pyarrow not found; saved as CSV to {csv_path}")
        return labels_df
    print(f"[label_builder] Saved labels to {cache_path}")
    return labels_df


def _fallback_labels(mode: str, reason: str = "") -> dict:
    """All-zero labels with all heads masked (used on error)."""
    base = {
        **{f"style_{col}": 0.0 for col in STYLE_COLS},
        "phase_idx": 0,
        "tactic_tactical": 0,
        "tactic_quiet_middlegame": 0,
        "eval_bucket": -1,
        "mask_style": 0,
        "mask_phase": 0,
        "mask_tactic": 0,
        "mask_eval": 0,
    }
    if mode == "stockfish":
        base.update({f"tactic_{t}": 0 for t in TACTIC_THEMES_STOCKFISH})
    return base
