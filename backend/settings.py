from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    root_dir: Path = ROOT_DIR
    hparams_path: Path = ROOT_DIR / "config/global_statistics_hparams.yaml"
    openings_path: Path = ROOT_DIR / "openings_dataset/all.tsv"
    opening_vectors_path: Path = ROOT_DIR / "openings_dataset/opening_feature_vectors.csv"
    mongodb_uri: str | None = os.environ.get("MONGODB_URI")
    mongodb_db: str = os.environ.get("MONGODB_DB", "chess_insighter")
    cors_origin_regex: str = r"^http://(localhost|127\.0\.0\.1):\d+$"
    frontend_url: str = os.environ.get("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    auth_jwt_secret: str = os.environ.get("AUTH_JWT_SECRET", "development-only-change-me-before-deploying")
    auth_jwt_issuer: str = os.environ.get("AUTH_JWT_ISSUER", "chess-insighter")
    auth_session_days: int = int(os.environ.get("AUTH_SESSION_DAYS", "7"))
    auth_verification_hours: int = int(os.environ.get("AUTH_VERIFICATION_HOURS", "24"))
    auth_cookie_secure: bool = os.environ.get("AUTH_COOKIE_SECURE", "false").lower() in {"1", "true", "yes"}
    auth_cookie_name: str = "chess_insighter_session"
    csrf_cookie_name: str = "chess_insighter_csrf"
    resend_api_key: str | None = os.environ.get("RESEND_API_KEY")
    resend_from_email: str | None = os.environ.get("RESEND_FROM_EMAIL")
    # Live Lichess opening explorer (repertoire positions past the named lines).
    lichess_api_token: str | None = os.environ.get("LICHESS_API_TOKEN", "").strip() or None

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
