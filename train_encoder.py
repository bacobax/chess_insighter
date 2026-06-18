"""
Standalone training script for the Position Style Encoder.
Reads hyperparameters from config/position_encoder_train.yaml.

Usage:
    python train_encoder.py
    python train_encoder.py --config config/position_encoder_train.yaml

Also importable — run_sweep.py calls load_training_data() and run_training() directly
so that data is loaded only once across multiple configs.
"""
import argparse
import csv
import copy
import io
import json
import random
import sys
import time
from pathlib import Path

import chess
import chess.pgn
import numpy as np
import pandas as pd
import torch
import yaml
import zstandard as zstd
from torch.utils.data import DataLoader, random_split
from tqdm.auto import tqdm

from utils.position_label_builder import build_labels
from utils.position_style_encoder import (
    PositionStyleEncoder,
    PositionStyleDataset,
    _get_device,
    evaluate,
    save_checkpoint,
    train_one_epoch,
)

# ── board_to_tensor ────────────────────────────────────────────────────────────
_PIECE_TO_CH = {
    (chess.PAWN,   chess.WHITE): 0,  (chess.KNIGHT, chess.WHITE): 1,
    (chess.BISHOP, chess.WHITE): 2,  (chess.ROOK,   chess.WHITE): 3,
    (chess.QUEEN,  chess.WHITE): 4,  (chess.KING,   chess.WHITE): 5,
    (chess.PAWN,   chess.BLACK): 6,  (chess.KNIGHT, chess.BLACK): 7,
    (chess.BISHOP, chess.BLACK): 8,  (chess.ROOK,   chess.BLACK): 9,
    (chess.QUEEN,  chess.BLACK): 10, (chess.KING,   chess.BLACK): 11,
}

def board_to_tensor(fen: str) -> np.ndarray:
    board = chess.Board(fen)
    x = np.zeros((18, 8, 8), dtype=np.float32)
    for sq, piece in board.piece_map().items():
        ch = _PIECE_TO_CH[(piece.piece_type, piece.color)]
        x[ch, chess.square_rank(sq), chess.square_file(sq)] = 1.0
    x[12, :, :] = 1.0 if board.turn == chess.WHITE else 0.0
    x[13, :, :] = 1.0 if board.has_kingside_castling_rights(chess.WHITE)  else 0.0
    x[14, :, :] = 1.0 if board.has_queenside_castling_rights(chess.WHITE) else 0.0
    x[15, :, :] = 1.0 if board.has_kingside_castling_rights(chess.BLACK)  else 0.0
    x[16, :, :] = 1.0 if board.has_queenside_castling_rights(chess.BLACK) else 0.0
    x[17, :, :] = min(board.fullmove_number, 100) / 100.0
    return x


# ── game streaming ─────────────────────────────────────────────────────────────

def stream_pgn_games(path: Path):
    dctx = zstd.ZstdDecompressor()
    with open(path, "rb") as f:
        with dctx.stream_reader(f) as r:
            ts = io.TextIOWrapper(r, encoding="utf-8", errors="replace")
            while True:
                game = chess.pgn.read_game(ts)
                if game is None:
                    break
                yield game


def build_positions(zst_path: Path, max_games: int, max_positions: int) -> pd.DataFrame:
    rows = []
    pbar = tqdm(total=max_positions, desc="positions", unit="pos")
    for i, game in enumerate(stream_pgn_games(zst_path)):
        if i >= max_games or len(rows) >= max_positions:
            break
        board = chess.Board()
        for ply, move in enumerate(game.mainline_moves(), start=1):
            if len(rows) >= max_positions:
                break
            rows.append({
                "fen":      board.fen(),
                "ply":      ply,
                "move_san": board.san(move),
                "move_uci": move.uci(),
            })
            board.push(move)
            pbar.update(1)
    pbar.close()
    return pd.DataFrame(rows)


# ── public API ─────────────────────────────────────────────────────────────────

def load_training_data(cfg: dict) -> tuple[np.ndarray, pd.DataFrame]:
    """
    Load (or build + cache) positions, labels, and board tensors.
    Returns (tensors_all, labels_df) ready to pass to run_training().
    Call this once and reuse across multiple configs.
    """
    data_cfg = cfg["data"]
    year, month = data_cfg["year"], data_cfg["month"]
    zst_path = Path(f"data/lichess/lichess_db_standard_rated_{year}-{month:02d}.pgn.zst")
    if not zst_path.exists():
        sys.exit(f"[error] PGN not found: {zst_path}")

    print(f"[data] Streaming up to {data_cfg['max_games']} games / "
          f"{data_cfg['max_positions']} positions …", flush=True)
    positions_df = build_positions(zst_path, data_cfg["max_games"], data_cfg["max_positions"])
    print(f"[data] {len(positions_df)} positions extracted\n", flush=True)

    labels_cache = Path(data_cfg["labels_cache"])
    labels_df = build_labels(
        positions_df,
        mode=data_cfg["label_mode"],
        cache_path=labels_cache,
        stockfish_path=data_cfg.get("stockfish_path", "/opt/homebrew/bin/stockfish"),
        engine_depth=data_cfg.get("engine_depth", 12),
    )

    tensors_cache = labels_cache.with_suffix(".tensors.npy")
    if tensors_cache.exists() and tensors_cache.stat().st_size > 0:
        print(f"[data] Loading cached tensors from {tensors_cache}", flush=True)
        tensors_all = np.load(str(tensors_cache))
    else:
        print("[data] Building board tensors …", flush=True)
        tensors_all = np.stack([
            board_to_tensor(fen)
            for fen in tqdm(positions_df["fen"], desc="tensors", unit="pos")
        ])
        np.save(str(tensors_cache), tensors_all)
        print(f"[data] Tensors saved to {tensors_cache}", flush=True)

    print(f"[data] Tensor array : {tensors_all.shape}\n", flush=True)
    return tensors_all, labels_df


def run_training(
    cfg: dict,
    tensors_all: np.ndarray,
    labels_df: pd.DataFrame,
) -> list[dict]:
    """
    Train one config. Outputs go to data/runs/<run_name>/:
      losses.csv     — one row per epoch
      summary.json   — final metrics + config snapshot
      checkpoint.pt  — best val_total checkpoint

    Returns the per-epoch history list.
    """
    run_cfg   = cfg["run"]
    data_cfg  = cfg["data"]
    model_cfg = cfg["model"]
    opt_cfg   = cfg["optim"]
    sch_cfg   = cfg["scheduler"]
    tr_cfg    = cfg["train"]

    run_name = run_cfg["name"]
    seed     = run_cfg.get("seed", 42)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    device = _get_device() if run_cfg.get("device", "auto") == "auto" \
             else torch.device(run_cfg["device"])

    # ── output directory ──────────────────────────────────────────────────────
    run_dir = Path(run_cfg.get("output_dir", "data")) / "runs" / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = run_dir / "checkpoint.pt"
    csv_path  = run_dir / "losses.csv"

    print(f"\n{'='*60}", flush=True)
    print(f"  Run        : {run_name}", flush=True)
    print(f"  Device     : {device}", flush=True)
    print(f"  Blocks     : {model_cfg['num_blocks']}  Width: {model_cfg['width']}", flush=True)
    print(f"  LR         : {opt_cfg['lr']}", flush=True)
    print(f"  Epochs     : {tr_cfg['epochs']}", flush=True)
    print(f"  Output dir : {run_dir}", flush=True)
    print(f"{'='*60}\n", flush=True)

    # ── dataset / loaders ─────────────────────────────────────────────────────
    dataset = PositionStyleDataset(tensors_all, labels_df, mode=data_cfg["label_mode"])
    n_val   = int(len(dataset) * data_cfg["val_split"])
    n_train = len(dataset) - n_val
    train_ds, val_ds = random_split(
        dataset, [n_train, n_val],
        generator=torch.Generator().manual_seed(seed),
    )

    batch_size = tr_cfg["batch_size"]
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True,
                              num_workers=tr_cfg.get("num_workers", 0))
    val_loader   = DataLoader(val_ds,   batch_size=batch_size, shuffle=False,
                              num_workers=tr_cfg.get("num_workers", 0))

    steps_per_epoch = len(train_loader)
    print(f"[data] Train: {n_train}  Val: {n_val}  "
          f"batch_size={batch_size}  steps/epoch={steps_per_epoch}\n", flush=True)

    # ── model ──────────────────────────────────────────────────────────────────
    model = PositionStyleEncoder(
        mode=data_cfg["label_mode"],
        embed_dim=model_cfg["embed_dim"],
        width=model_cfg["width"],
        num_blocks=model_cfg["num_blocks"],
        head_hidden=model_cfg["head_hidden"],
    )
    n_params = sum(p.numel() for p in model.parameters())
    print(f"[model] Parameters : {n_params:,}", flush=True)
    print(f"[model] {model_cfg['num_blocks']} blocks × {model_cfg['width']} "
          f"filters → {model_cfg['embed_dim']}-d z\n", flush=True)

    # ── optimizer / scheduler ─────────────────────────────────────────────────
    n_epochs = tr_cfg["epochs"]
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=opt_cfg["lr"],
        weight_decay=opt_cfg.get("weight_decay", 1e-5),
        betas=tuple(opt_cfg.get("betas", [0.9, 0.999])),
    )
    # Optional linear warmup then cosine decay.
    # Set scheduler.warmup_epochs > 0 in config to enable.
    warmup_epochs = cfg["scheduler"].get("warmup_epochs", 0)
    cosine_epochs = n_epochs - warmup_epochs
    cosine_sched = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer,
        T_max=max(cosine_epochs, 1),
        eta_min=cfg["scheduler"].get("eta_min", 1e-5),
    )
    if warmup_epochs > 0:
        warmup_sched = torch.optim.lr_scheduler.LinearLR(
            optimizer,
            start_factor=0.1,
            end_factor=1.0,
            total_iters=warmup_epochs,
        )
        scheduler = torch.optim.lr_scheduler.SequentialLR(
            optimizer,
            schedulers=[warmup_sched, cosine_sched],
            milestones=[warmup_epochs],
        )
        print(f"[optim] Warmup {warmup_epochs} ep → cosine {cosine_epochs} ep", flush=True)
    else:
        scheduler = cosine_sched

    # ── CSV header ─────────────────────────────────────────────────────────────
    csv_fields = [
        "epoch",
        "train_total", "train_style", "train_phase", "train_tactic", "train_eval",
        "val_total",   "val_style",   "val_phase",   "val_tactic",   "val_eval",
        "lr", "elapsed_s",
    ]
    csv_file = open(csv_path, "w", newline="")
    writer = csv.DictWriter(csv_file, fieldnames=csv_fields)
    writer.writeheader()
    csv_file.flush()

    # ── training loop ──────────────────────────────────────────────────────────
    log_every = tr_cfg.get("log_every", 5)
    best_val  = float("inf")
    history   = []
    t0 = time.time()

    for epoch in range(1, n_epochs + 1):
        tr = train_one_epoch(model, train_loader, optimizer, device)
        vl = evaluate(model, val_loader, device)
        scheduler.step()

        elapsed = time.time() - t0
        current_lr = optimizer.param_groups[0]["lr"]
        row = {
            "epoch": epoch,
            "train_total":  tr["total"],  "train_style":  tr["style"],
            "train_phase":  tr["phase"],  "train_tactic": tr["tactic"],
            "train_eval":   tr["eval"],
            "val_total":    vl["total"],  "val_style":    vl["style"],
            "val_phase":    vl["phase"],  "val_tactic":   vl["tactic"],
            "val_eval":     vl["eval"],
            "lr": current_lr,
            "elapsed_s": round(elapsed, 1),
        }
        history.append(row)
        writer.writerow(row)
        csv_file.flush()

        if vl["total"] < best_val:
            best_val = vl["total"]
            save_checkpoint(model, optimizer, epoch, row, ckpt_path)

        if epoch % log_every == 0 or epoch == 1:
            eta = elapsed / epoch * (n_epochs - epoch)
            print(
                f"  Epoch {epoch:3d}/{n_epochs} | "
                f"train={tr['total']:.4f}  style={tr['style']:.4f}  "
                f"phase={tr['phase']:.4f}  tactic={tr['tactic']:.4f} | "
                f"val={vl['total']:.4f} | "
                f"{elapsed:.0f}s  ETA {eta:.0f}s",
                flush=True,
            )

    csv_file.close()
    total_time = time.time() - t0

    summary = {
        "run_name":   run_name,
        "n_params":   n_params,
        "num_blocks": model_cfg["num_blocks"],
        "width":      model_cfg["width"],
        "lr":         opt_cfg["lr"],
        "epochs":     n_epochs,
        "batch_size": batch_size,
        "best_val_total":   best_val,
        "final_val_total":  history[-1]["val_total"],
        "final_val_style":  history[-1]["val_style"],
        "final_val_phase":  history[-1]["val_phase"],
        "final_val_tactic": history[-1]["val_tactic"],
        "total_time_s": round(total_time, 1),
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print(f"\n  Done in {total_time:.0f}s ({total_time/60:.1f} min) | "
          f"best val_total={best_val:.4f}", flush=True)
    print(f"  CSV        → {csv_path}", flush=True)
    print(f"  Checkpoint → {ckpt_path}\n", flush=True)

    return history


# ── CLI entry point ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/position_encoder_train.yaml")
    args = parser.parse_args()

    cfg = yaml.safe_load(open(args.config))
    tensors_all, labels_df = load_training_data(cfg)
    run_training(cfg, tensors_all, labels_df)


if __name__ == "__main__":
    main()
