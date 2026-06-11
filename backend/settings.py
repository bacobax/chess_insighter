from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    root_dir: Path = ROOT_DIR
    hparams_path: Path = ROOT_DIR / "config/global_statistics_hparams.yaml"
    openings_path: Path = ROOT_DIR / "openings_dataset/all.tsv"
    opening_vectors_path: Path = ROOT_DIR / "openings_dataset/opening_feature_vectors.csv"
    report_cache_dir: Path = ROOT_DIR / ".cache/reports"
    report_config_dir: Path = ROOT_DIR / ".cache/report_configs"
    player_vector_cache_path: Path = ROOT_DIR / ".cache/player_vectors.json"
    saved_reports_path: Path = ROOT_DIR / ".cache/saved_reports.json"
    cors_origin_regex: str = r"^http://(localhost|127\.0\.0\.1):\d+$"

    @property
    def stockfish_path(self) -> str | None:
        configured = os.environ.get("STOCKFISH_PATH")
        if configured:
            return configured
        discovered = shutil.which("stockfish")
        if discovered:
            return discovered
        fallback = "/opt/homebrew/bin/stockfish"
        return fallback if Path(fallback).exists() else None


settings = Settings()
