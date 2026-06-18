"""
position_style_encoder.py
=========================
ResNet-based chess position style encoder with multitask distillation heads.

Architecture
------------
  Input: 18 × 8 × 8 board tensor  (board_to_tensor format)
  Encoder:
    stem:  Conv2d(18→128, 3×3, pad=1) → BN → ReLU
    body:  N residual blocks (default 8), each:
             Conv2d(128→128, 3×3, pad=1) → BN → ReLU
             Conv2d(128→128, 3×3, pad=1) → BN
             + skip → ReLU
    pool:  global average pooling → 128-d vector
    proj:  Linear(128→128) → L2-normalise  →  z  (unit-norm, cosine-native)

  Heads (each: Linear→ReLU→Linear, small MLP off z):
    style   : 9 × sigmoid  (→ [0,1]^9, MSE)
    eval    : 3-way softmax (winning / equal / losing, CE)
    phase   : 3-way softmax (opening / middlegame / endgame, CE)
    tactic  : k × sigmoid  (multi-label BCE; k=2 lightweight, k=10 stockfish)

  Loss = Σ_head  exp(-s_i) * L_i  +  s_i       (Kendall uncertainty weighting)
  where s_i = log-variance param, one per head.  Masked samples contribute 0.

Usage (quick example)
---------------------
    from utils.position_style_encoder import (
        PositionStyleEncoder, PositionStyleDataset,
        train_one_epoch, evaluate, embed_positions,
    )

    model = PositionStyleEncoder()
    # feed it labels_df from position_label_builder.build_labels()
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

from utils.position_label_builder import (
    STYLE_COLS,
    PHASE_CLASSES,
    TACTIC_COLS_LIGHTWEIGHT,
    TACTIC_COLS_STOCKFISH,
    LABEL_MODE,
)


# ---------------------------------------------------------------------------
# Encoder building blocks
# ---------------------------------------------------------------------------

class ResidualBlock(nn.Module):
    """Standard pre-activation residual block (keeps 8×8 board spatial dims)."""

    def __init__(self, channels: int = 128) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(channels, channels, kernel_size=3, padding=1, bias=False)
        self.bn1   = nn.BatchNorm2d(channels)
        self.conv2 = nn.Conv2d(channels, channels, kernel_size=3, padding=1, bias=False)
        self.bn2   = nn.BatchNorm2d(channels)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = x
        out = F.relu(self.bn1(self.conv1(x)), inplace=True)
        out = self.bn2(self.conv2(out))
        return F.relu(out + residual, inplace=True)


class BoardEncoder(nn.Module):
    """
    Shared trunk: 18×8×8 → 128-d L2-normalised embedding z.

    Parameters
    ----------
    in_channels : input channels (default 18 for board_to_tensor format)
    width       : number of filters throughout the ResNet body (default 128)
    num_blocks  : number of residual blocks (default 8)
    embed_dim   : output embedding dimension (default 128)
    """

    def __init__(
        self,
        in_channels: int = 18,
        width: int = 128,
        num_blocks: int = 8,
        embed_dim: int = 128,
    ) -> None:
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv2d(in_channels, width, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(width),
            nn.ReLU(inplace=True),
        )
        self.body = nn.Sequential(*(ResidualBlock(width) for _ in range(num_blocks)))
        # Global average pool then project to embedding
        self.proj = nn.Linear(width, embed_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, 18, 8, 8)
        h = self.stem(x)             # (B, W, 8, 8)
        h = self.body(h)             # (B, W, 8, 8)
        h = h.mean(dim=(-2, -1))    # global avg pool → (B, W)
        z = self.proj(h)             # (B, embed_dim)
        z = F.normalize(z, p=2, dim=-1)  # unit-norm → cosine geometry
        return z


def _small_head(in_dim: int, out_dim: int, hidden: int = 64) -> nn.Sequential:
    """Two-layer MLP head: in_dim → hidden → out_dim (no final activation)."""
    return nn.Sequential(
        nn.Linear(in_dim, hidden),
        nn.ReLU(inplace=True),
        nn.Linear(hidden, out_dim),
    )


# ---------------------------------------------------------------------------
# Full multitask model
# ---------------------------------------------------------------------------

class PositionStyleEncoder(nn.Module):
    """
    ResNet encoder + 4 distillation heads.

    Parameters
    ----------
    mode        : "lightweight" | "stockfish" — determines tactic head width.
    embed_dim   : embedding dimension (default 128).
    width       : ResNet filter count (default 128).
    num_blocks  : number of residual blocks (default 8).
    head_hidden : hidden units in each MLP head (default 64).
    """

    STYLE_DIM  = len(STYLE_COLS)    # 9
    PHASE_DIM  = len(PHASE_CLASSES) # 3
    EVAL_DIM   = 3                  # winning / equal / losing

    def __init__(
        self,
        mode: str = LABEL_MODE,
        embed_dim: int = 128,
        width: int = 128,
        num_blocks: int = 8,
        head_hidden: int = 64,
    ) -> None:
        super().__init__()
        self.mode = mode
        self.embed_dim = embed_dim

        tactic_cols = TACTIC_COLS_STOCKFISH if mode == "stockfish" else TACTIC_COLS_LIGHTWEIGHT
        self.tactic_cols = tactic_cols
        self.TACTIC_DIM = len(tactic_cols)

        self.encoder = BoardEncoder(
            in_channels=18,
            width=width,
            num_blocks=num_blocks,
            embed_dim=embed_dim,
        )

        # Heads
        self.head_style  = _small_head(embed_dim, self.STYLE_DIM,  head_hidden)
        self.head_phase  = _small_head(embed_dim, self.PHASE_DIM,  head_hidden)
        self.head_eval   = _small_head(embed_dim, self.EVAL_DIM,   head_hidden)
        self.head_tactic = _small_head(embed_dim, self.TACTIC_DIM, head_hidden)

        # Kendall learnable log-variance params (one per head)
        # loss_i = exp(-s_i) * task_loss_i + s_i
        self.log_var_style  = nn.Parameter(torch.zeros(1))
        self.log_var_phase  = nn.Parameter(torch.zeros(1))
        self.log_var_eval   = nn.Parameter(torch.zeros(1))
        self.log_var_tactic = nn.Parameter(torch.zeros(1))

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        """
        Parameters
        ----------
        x : (B, 18, 8, 8) float tensor

        Returns
        -------
        dict with keys:
          "z"      : (B, embed_dim)  — L2-normalised embedding
          "style"  : (B, 9)          — raw logits (apply sigmoid for [0,1])
          "phase"  : (B, 3)          — raw logits (apply softmax for probs)
          "eval"   : (B, 3)          — raw logits (apply softmax for probs)
          "tactic" : (B, k)          — raw logits (apply sigmoid per label)
        """
        z = self.encoder(x)
        return {
            "z":      z,
            "style":  self.head_style(z),
            "phase":  self.head_phase(z),
            "eval":   self.head_eval(z),
            "tactic": self.head_tactic(z),
        }

    def compute_loss(
        self,
        outputs: dict[str, torch.Tensor],
        labels: dict[str, torch.Tensor],
        masks: dict[str, torch.Tensor],
    ) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
        """
        Compute Kendall-weighted multitask loss with per-sample masking.

        Parameters
        ----------
        outputs : forward() return dict
        labels  : {
            "style"  : (B, 9) float,
            "phase"  : (B,)   long,
            "eval"   : (B,)   long,
            "tactic" : (B, k) float,
          }
        masks   : {
            "style", "phase", "eval", "tactic"  : (B,) float  (0/1)
          }

        Returns
        -------
        (total_loss, per_head_loss_dict)
        """
        per_head: dict[str, torch.Tensor] = {}

        # --- Style head: MSE with sigmoid ---
        sl = self._masked_mse(
            torch.sigmoid(outputs["style"]),
            labels["style"],
            masks["style"],
        )
        per_head["style"] = sl
        l_style = torch.exp(-self.log_var_style) * sl + self.log_var_style

        # --- Phase head: cross-entropy ---
        pl = self._masked_ce(outputs["phase"], labels["phase"], masks["phase"])
        per_head["phase"] = pl
        l_phase = torch.exp(-self.log_var_phase) * pl + self.log_var_phase

        # --- Eval head: cross-entropy (often masked in lightweight mode) ---
        el = self._masked_ce(outputs["eval"], labels["eval"], masks["eval"])
        per_head["eval"] = el
        l_eval = torch.exp(-self.log_var_eval) * el + self.log_var_eval

        # --- Tactic head: binary cross-entropy ---
        tl = self._masked_bce(
            outputs["tactic"],
            labels["tactic"],
            masks["tactic"],
        )
        per_head["tactic"] = tl
        l_tactic = torch.exp(-self.log_var_tactic) * tl + self.log_var_tactic

        total = l_style + l_phase + l_eval + l_tactic
        return total, per_head

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _masked_mse(
        pred: torch.Tensor,
        target: torch.Tensor,
        mask: torch.Tensor,
    ) -> torch.Tensor:
        """MSE averaged over masked samples; returns 0 if mask is all-zero."""
        mask = mask.bool()
        if not mask.any():
            return pred.sum() * 0.0
        return F.mse_loss(pred[mask], target[mask])

    @staticmethod
    def _masked_ce(
        logits: torch.Tensor,
        target: torch.Tensor,
        mask: torch.Tensor,
    ) -> torch.Tensor:
        """Cross-entropy averaged over masked samples."""
        mask = mask.bool()
        if not mask.any():
            return logits.sum() * 0.0
        return F.cross_entropy(logits[mask], target[mask].long())

    @staticmethod
    def _masked_bce(
        logits: torch.Tensor,
        target: torch.Tensor,
        mask: torch.Tensor,
    ) -> torch.Tensor:
        """Binary cross-entropy (multi-label) averaged over masked samples."""
        mask = mask.bool()
        if not mask.any():
            return logits.sum() * 0.0
        return F.binary_cross_entropy_with_logits(logits[mask], target[mask].float())

    def embed(self, x: torch.Tensor) -> torch.Tensor:
        """Return L2-normalised embedding z for a batch of board tensors."""
        self.eval()
        with torch.no_grad():
            return self.encoder(x)


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class PositionStyleDataset(Dataset):
    """
    PyTorch Dataset wrapping board tensors and pre-computed labels.

    Parameters
    ----------
    tensors   : np.ndarray  shape (N, 18, 8, 8) float32
    labels_df : pd.DataFrame  row-aligned, produced by build_labels()
    mode      : "lightweight" | "stockfish" (determines tactic column set)
    """

    def __init__(
        self,
        tensors: np.ndarray,
        labels_df: "pd.DataFrame",  # noqa: F821
        mode: str = LABEL_MODE,
    ) -> None:
        assert len(tensors) == len(labels_df), (
            f"tensors ({len(tensors)}) and labels_df ({len(labels_df)}) must have the same length"
        )
        self.tensors = torch.from_numpy(tensors).float()

        tactic_cols = TACTIC_COLS_STOCKFISH if mode == "stockfish" else TACTIC_COLS_LIGHTWEIGHT

        # Style targets (9 floats)
        style_arr = labels_df[[f"style_{c}" for c in STYLE_COLS]].to_numpy(dtype=np.float32).copy()
        self.style = torch.from_numpy(style_arr)

        # Phase target (long)
        self.phase = torch.from_numpy(
            labels_df["phase_idx"].to_numpy(dtype=np.int64).copy()
        )

        # Eval target (long; -1 is sentinel for masked)
        eval_raw = labels_df["eval_bucket"].to_numpy(dtype=np.int64)
        eval_safe = np.clip(eval_raw, 0, 2).copy()  # sentinel -1 → 0 (will be masked anyway)
        self.eval_target = torch.from_numpy(eval_safe)

        # Tactic targets (multi-label float)
        tact_cols_in_df = [f"tactic_{c}" for c in tactic_cols]
        # Fill missing tactic columns with 0 (lightweight mode lacks stockfish themes)
        tact_arr = np.zeros((len(labels_df), len(tactic_cols)), dtype=np.float32)
        for i, col in enumerate(tact_cols_in_df):
            if col in labels_df.columns:
                tact_arr[:, i] = labels_df[col].to_numpy(dtype=np.float32)
        self.tactic = torch.from_numpy(tact_arr)

        # Masks (float for easy multiplication)
        self.mask_style  = torch.from_numpy(labels_df["mask_style"].to_numpy(dtype=np.float32).copy())
        self.mask_phase  = torch.from_numpy(labels_df["mask_phase"].to_numpy(dtype=np.float32).copy())
        self.mask_eval   = torch.from_numpy(labels_df["mask_eval"].to_numpy(dtype=np.float32).copy())
        self.mask_tactic = torch.from_numpy(labels_df["mask_tactic"].to_numpy(dtype=np.float32).copy())

    def __len__(self) -> int:
        return len(self.tensors)

    def __getitem__(self, idx: int) -> tuple:
        return (
            self.tensors[idx],
            {
                "style":  self.style[idx],
                "phase":  self.phase[idx],
                "eval":   self.eval_target[idx],
                "tactic": self.tactic[idx],
            },
            {
                "style":  self.mask_style[idx],
                "phase":  self.mask_phase[idx],
                "eval":   self.mask_eval[idx],
                "tactic": self.mask_tactic[idx],
            },
        )


# ---------------------------------------------------------------------------
# Training & evaluation loops
# ---------------------------------------------------------------------------

def _get_device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def train_one_epoch(
    model: PositionStyleEncoder,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    device: Optional[torch.device] = None,
) -> dict[str, float]:
    """Run one training epoch. Returns dict of average losses."""
    if device is None:
        device = _get_device()
    model.train()
    model.to(device)

    total_loss = 0.0
    head_totals: dict[str, float] = {"style": 0.0, "phase": 0.0, "eval": 0.0, "tactic": 0.0}
    n_batches = 0

    for tensors, labels, masks in loader:
        tensors = tensors.to(device)
        labels  = {k: v.to(device) for k, v in labels.items()}
        masks   = {k: v.to(device) for k, v in masks.items()}

        optimizer.zero_grad()
        outputs = model(tensors)
        loss, per_head = model.compute_loss(outputs, labels, masks)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()

        total_loss += loss.item()
        for k in head_totals:
            head_totals[k] += per_head[k].item()
        n_batches += 1

    scale = 1.0 / max(n_batches, 1)
    return {
        "total": total_loss * scale,
        **{k: v * scale for k, v in head_totals.items()},
    }


@torch.no_grad()
def evaluate(
    model: PositionStyleEncoder,
    loader: DataLoader,
    device: Optional[torch.device] = None,
) -> dict[str, float]:
    """Evaluate on a DataLoader. Returns average losses (same keys as train_one_epoch)."""
    if device is None:
        device = _get_device()
    model.eval()
    model.to(device)

    total_loss = 0.0
    head_totals: dict[str, float] = {"style": 0.0, "phase": 0.0, "eval": 0.0, "tactic": 0.0}
    n_batches = 0

    for tensors, labels, masks in loader:
        tensors = tensors.to(device)
        labels  = {k: v.to(device) for k, v in labels.items()}
        masks   = {k: v.to(device) for k, v in masks.items()}

        outputs = model(tensors)
        loss, per_head = model.compute_loss(outputs, labels, masks)

        total_loss += loss.item()
        for k in head_totals:
            head_totals[k] += per_head[k].item()
        n_batches += 1

    scale = 1.0 / max(n_batches, 1)
    return {
        "total": total_loss * scale,
        **{k: v * scale for k, v in head_totals.items()},
    }


@torch.no_grad()
def embed_positions(
    model: PositionStyleEncoder,
    tensors: np.ndarray,
    batch_size: int = 512,
    device: Optional[torch.device] = None,
) -> np.ndarray:
    """
    Encode a numpy array of board tensors into L2-normalised embeddings.

    Parameters
    ----------
    tensors : (N, 18, 8, 8) float32 numpy array
    Returns : (N, embed_dim) float32 numpy array
    """
    if device is None:
        device = _get_device()
    model.eval()
    model.to(device)

    t = torch.from_numpy(tensors).float()
    embeddings = []
    for start in range(0, len(t), batch_size):
        chunk = t[start : start + batch_size].to(device)
        z = model.encoder(chunk)
        embeddings.append(z.cpu().numpy())
    return np.concatenate(embeddings, axis=0)


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def save_checkpoint(
    model: PositionStyleEncoder,
    optimizer: torch.optim.Optimizer,
    epoch: int,
    losses: dict[str, float],
    path: Path,
) -> None:
    torch.save(
        {
            "epoch": epoch,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "losses": losses,
            "mode": model.mode,
            "embed_dim": model.embed_dim,
        },
        path,
    )
    print(f"[encoder] Checkpoint saved → {path}")


def load_checkpoint(
    path: Path,
    device: Optional[torch.device] = None,
) -> tuple[PositionStyleEncoder, dict]:
    """Load a checkpoint and return (model, metadata_dict)."""
    if device is None:
        device = _get_device()
    ckpt = torch.load(path, map_location=device)
    model = PositionStyleEncoder(
        mode=ckpt.get("mode", LABEL_MODE),
        embed_dim=ckpt.get("embed_dim", 128),
    )
    model.load_state_dict(ckpt["model_state_dict"])
    model.to(device)
    return model, ckpt
