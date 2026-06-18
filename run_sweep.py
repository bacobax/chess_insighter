"""
Hyperparameter sweep for the Position Style Encoder.

Runs 4 configs sequentially with a cooldown between each, logs all losses
to per-run CSVs, and generates comparison plots + a master summary CSV.

Output layout:
    data/runs/<run_name>/losses.csv      — per-epoch loss table
    data/runs/<run_name>/summary.json    — final metrics + config
    data/runs/<run_name>/checkpoint.pt   — best val checkpoint
    data/sweep/loss_curves.png           — train+val curves for all heads
    data/sweep/final_metrics.png         — bar chart of final val metrics
    data/sweep/summary.csv               — one row per run

Usage:
    python -u run_sweep.py
"""
import copy
import json
import time
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import yaml

from train_encoder import load_training_data, run_training

# ── sweep config ───────────────────────────────────────────────────────────────

BASE_CONFIG_PATH = "config/position_encoder_train.yaml"
COOLDOWN_SECONDS = 90   # seconds to rest the Mac between runs

# Each dict deep-merges into the base YAML.
# Only keys that differ from the base need to be listed.
SWEEP_CONFIGS = [
    {
        "run": {"name": "base_50ep"},
        "model": {"num_blocks": 8, "width": 128},
        "optim": {"lr": 3e-4},
        "train": {"epochs": 50},
        "scheduler": {"t_max": 50},
    },
    {
        "run": {"name": "small_50ep"},
        "model": {"num_blocks": 4, "width": 64},
        "optim": {"lr": 3e-4},
        "train": {"epochs": 50},
        "scheduler": {"t_max": 50},
    },
    {
        "run": {"name": "lr_high_50ep"},
        "model": {"num_blocks": 8, "width": 128},
        "optim": {"lr": 1e-3},
        "train": {"epochs": 50},
        "scheduler": {"t_max": 50},
    },
    {
        "run": {"name": "lr_low_50ep"},
        "model": {"num_blocks": 8, "width": 128},
        "optim": {"lr": 1e-4},
        "train": {"epochs": 50},
        "scheduler": {"t_max": 50},
    },
]

# ── helpers ────────────────────────────────────────────────────────────────────

def deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result


def cooldown(seconds: int, run_name: str) -> None:
    print(f"\n{'─'*60}", flush=True)
    print(f"  Cooldown {seconds}s after '{run_name}' — letting Mac rest …", flush=True)
    for remaining in range(seconds, 0, -10):
        print(f"  {remaining}s …", flush=True)
        time.sleep(min(10, remaining))
    print(f"  Resuming.\n{'─'*60}\n", flush=True)


# ── plotting ───────────────────────────────────────────────────────────────────

PALETTE = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
HEAD_METRICS = ["total", "style", "phase", "tactic"]
HEAD_LABELS  = ["Total loss", "Style MSE", "Phase CE", "Tactic BCE"]


def plot_loss_curves(histories: dict[str, list[dict]], out_dir: Path) -> None:
    """4-panel plot: one panel per head metric, all runs overlaid."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    axes = axes.flatten()

    for ax, metric, label in zip(axes, HEAD_METRICS, HEAD_LABELS):
        for (run_name, history), color in zip(histories.items(), PALETTE):
            epochs    = [r["epoch"]          for r in history]
            train_val = [r[f"train_{metric}"] for r in history]
            val_val   = [r[f"val_{metric}"]   for r in history]
            ax.plot(epochs, train_val, color=color, linestyle="--", alpha=0.5,
                    linewidth=1.2, label=f"{run_name} train")
            ax.plot(epochs, val_val,   color=color, linestyle="-",
                    linewidth=1.8, label=f"{run_name} val")
        ax.set_title(label, fontsize=12)
        ax.set_xlabel("Epoch")
        ax.grid(True, alpha=0.3)

    # Single legend below the figure
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, fontsize=8,
               bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("Sweep: loss curves (dashed=train, solid=val)", fontsize=14)
    plt.tight_layout(rect=[0, 0.06, 1, 1])
    path = out_dir / "loss_curves.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[plot] Saved {path}", flush=True)


def plot_final_metrics(summaries: list[dict], out_dir: Path) -> None:
    """Grouped bar chart of final val metrics per run."""
    run_names = [s["run_name"] for s in summaries]
    metrics   = ["final_val_total", "final_val_style", "final_val_phase", "final_val_tactic"]
    labels    = ["Total",           "Style MSE",       "Phase CE",        "Tactic BCE"]

    x      = np.arange(len(run_names))
    width  = 0.18
    offsets = [-1.5, -0.5, 0.5, 1.5]

    fig, ax = plt.subplots(figsize=(12, 5))
    for offset, metric, label, color in zip(offsets, metrics, labels, PALETTE):
        vals = [s[metric] for s in summaries]
        ax.bar(x + offset * width, vals, width, label=label, color=color, alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels(run_names, fontsize=10)
    ax.set_ylabel("Loss (final val, epoch 50)")
    ax.set_title("Final validation metrics by config")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.3f"))
    plt.tight_layout()
    path = out_dir / "final_metrics.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[plot] Saved {path}", flush=True)


def plot_val_total_comparison(histories: dict[str, list[dict]], out_dir: Path) -> None:
    """Clean single-panel comparison of val_total across all runs."""
    fig, ax = plt.subplots(figsize=(10, 5))
    for (run_name, history), color in zip(histories.items(), PALETTE):
        epochs = [r["epoch"]      for r in history]
        vals   = [r["val_total"]  for r in history]
        ax.plot(epochs, vals, color=color, linewidth=2, label=run_name)
    ax.set_xlabel("Epoch")
    ax.set_ylabel("val_total (Kendall-weighted)")
    ax.set_title("Validation total loss — all configs")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    path = out_dir / "val_total_comparison.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[plot] Saved {path}", flush=True)


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    base_cfg = yaml.safe_load(open(BASE_CONFIG_PATH))
    sweep_dir = Path("data/sweep")
    sweep_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'#'*60}", flush=True)
    print(f"  Hyperparameter sweep — {len(SWEEP_CONFIGS)} configs", flush=True)
    print(f"  Cooldown between runs: {COOLDOWN_SECONDS}s", flush=True)
    est_min = len(SWEEP_CONFIGS) * 50 * 25 / 60 + len(SWEEP_CONFIGS) * COOLDOWN_SECONDS / 60
    print(f"  Rough ETA: ~{est_min:.0f} min total", flush=True)
    print(f"{'#'*60}\n", flush=True)

    # Load data once — reused across all configs
    tensors_all, labels_df = load_training_data(base_cfg)

    histories:  dict[str, list[dict]] = {}
    summaries:  list[dict]            = []

    for i, sweep_override in enumerate(SWEEP_CONFIGS):
        cfg      = deep_merge(base_cfg, sweep_override)
        run_name = cfg["run"]["name"]

        print(f"\n[sweep {i+1}/{len(SWEEP_CONFIGS)}] Starting '{run_name}' …\n", flush=True)
        history = run_training(cfg, tensors_all, labels_df)
        histories[run_name] = history

        # Load summary produced by run_training
        summary_path = Path("data/runs") / run_name / "summary.json"
        summaries.append(json.loads(summary_path.read_text()))

        # Cooldown between runs (skip after the last one)
        if i < len(SWEEP_CONFIGS) - 1:
            cooldown(COOLDOWN_SECONDS, run_name)

    # ── aggregate summary CSV ─────────────────────────────────────────────────
    summary_df = pd.DataFrame(summaries)
    summary_csv = sweep_dir / "summary.csv"
    summary_df.to_csv(summary_csv, index=False)
    print(f"\n[sweep] Summary CSV → {summary_csv}", flush=True)
    print(summary_df.to_string(index=False), flush=True)

    # ── plots ─────────────────────────────────────────────────────────────────
    print("\n[sweep] Generating plots …", flush=True)
    plot_loss_curves(histories, sweep_dir)
    plot_val_total_comparison(histories, sweep_dir)
    plot_final_metrics(summaries, sweep_dir)

    print(f"\n{'#'*60}", flush=True)
    print(f"  Sweep complete. Results in data/sweep/ and data/runs/", flush=True)
    print(f"{'#'*60}\n", flush=True)


if __name__ == "__main__":
    main()
