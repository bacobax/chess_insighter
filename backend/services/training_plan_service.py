from __future__ import annotations

import io
import threading
from datetime import date, datetime, timezone
from typing import Any, Callable
from uuid import uuid4

import chess.engine
import chess.pgn

from backend.models import TrainingCardReviewRequest, TrainingPlanBuildRequest, TrainingPlanResponse
from backend.services.cache_service import stable_hash
from backend.services.mongo_service import blob_get, blob_put
from backend.services.chesscom_service import fetch_latest_games_for_report
from backend.services.openings_service import serializable
from backend.services.report_analysis_service import (
    TRAINING_ANALYSIS_NAMESPACE,
    ReportAnalysisStore,
    _atomic_write_json,
    _dataclass_payload,
    _load_enriched,
    _mistake_id,
    _read_json,
)
from backend.services.report_repository import username_key
from backend.settings import settings
from utils.game_enrichment_transformer import GameEnrichmentTransformer
from utils.mistakes_analyzer import MistakeAnalyzerConfig, analyze_mistakes
from utils.opening_repository import OpeningRepository
from utils.training_plan import build_training_plan, game_id, review_card


ProgressCallback = Callable[[str, float, str, int | None, int | None], None]
MIN_FULL_MOVES = 10
_LOCK = threading.RLock()


class TrainingPlanCancelled(RuntimeError):
    pass


TRAINING_PLANS_NAMESPACE = "training_plans"


class TrainingPlanNotFound(FileNotFoundError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TrainingPlanStore:
    """Latest plan per (account, Chess.com player), with review state on its cards."""

    def key(self, owner_id: str, username: str) -> str:
        return f"{stable_hash({'owner': owner_id})}/{stable_hash({'username': username_key(username)})}"

    def get(self, owner_id: str, username: str) -> dict[str, Any]:
        plan = blob_get(TRAINING_PLANS_NAMESPACE, self.key(owner_id, username))
        if plan is None:
            raise TrainingPlanNotFound("No training plan has been built for this player yet.")
        return plan

    def find(self, owner_id: str, username: str) -> dict[str, Any] | None:
        try:
            return self.get(owner_id, username)
        except TrainingPlanNotFound:
            return None

    def save(self, owner_id: str, username: str, plan: dict[str, Any]) -> None:
        blob_put(
            TRAINING_PLANS_NAMESPACE,
            self.key(owner_id, username),
            plan,
            owner_id=owner_id,
            username_key=username_key(username),
        )

    def review(self, owner_id: str, username: str, card_id: str, request: TrainingCardReviewRequest) -> dict[str, Any]:
        with _LOCK:
            plan = self.get(owner_id, username)
            for index, card in enumerate(plan["cards"]):
                if card["card_id"] == card_id:
                    updated = review_card(card, request.grade)
                    if request.label is not None:
                        updated["label"] = request.label or None
                    if request.note is not None:
                        updated["note"] = request.note.strip() or None
                    plan["cards"][index] = updated
                    plan["updated_at"] = _now()
                    self.save(owner_id, username, plan)
                    return updated
        raise TrainingPlanNotFound("Card not found in this training plan.")


def is_standard_game(game: dict[str, Any]) -> bool:
    if game.get("rules", "chess") != "chess":
        return False
    try:
        parsed = chess.pgn.read_game(io.StringIO(game.get("pgn") or ""))
    except Exception:
        return False
    if parsed is None:
        return False
    plies = sum(1 for _ in parsed.mainline_moves())
    return plies >= MIN_FULL_MOVES * 2


def build_training_plan_for_player(
    request: TrainingPlanBuildRequest,
    *,
    owner_id: str,
    progress_callback: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    store: TrainingPlanStore | None = None,
) -> dict[str, Any]:
    store = store or TrainingPlanStore()

    def check_cancel() -> None:
        if cancel_event and cancel_event.is_set():
            raise TrainingPlanCancelled("Training plan build cancelled.")

    def emit(stage: str, progress: float, message: str, processed: int | None = None, total: int | None = None) -> None:
        check_cancel()
        if progress_callback:
            progress_callback(stage, progress, message, processed, total)

    engine_path = settings.stockfish_path
    if not engine_path:
        raise ValueError("Stockfish is required to build a training plan.")

    emit("fetching_games", 0.02, "Fetching Chess.com games")
    fetched = fetch_latest_games_for_report(
        username=request.username,
        max_games=min(500, request.max_games + max(10, request.max_games // 4)),
        time_classes=request.time_classes,
        rated_filter=None,
        since_year=None,
        since_month=None,
        until_year=None,
        until_month=None,
        progress_callback=lambda processed, total: emit(
            "fetching_games", 0.02 + 0.06 * (processed / max(total, 1)),
            f"Scanning Chess.com archive {processed} of {total}", processed, total,
        ),
        cancel_check=check_cancel,
    )
    raw_games = [game for game in fetched if is_standard_game(game) and game_id(game)][: request.max_games]
    removed = len(fetched) - len(raw_games)
    emit("filtering", 0.09, f"Selected {len(raw_games)} games", len(raw_games), len(raw_games))
    if not raw_games:
        raise ValueError("No standard games with 10 or more moves were found for this player.")

    analysis = ReportAnalysisStore(
        stable_hash({"training": username_key(request.username)}),
        namespace=TRAINING_ANALYSIS_NAMESPACE,
    )
    config = MistakeAnalyzerConfig(engine_depth=request.engine_depth)
    transformer = GameEnrichmentTransformer(
        stockfish_path=engine_path,
        opening_repository=OpeningRepository(settings.openings_path),
        engine_limit=chess.engine.Limit(depth=request.engine_depth),
    )
    enriched_games = []
    mistakes: list[dict[str, Any]] = []
    total = len(raw_games)
    with analysis.lock(), chess.engine.SimpleEngine.popen_uci(engine_path) as engine:
        position_cache: dict[str, Any] = {}
        for index, raw in enumerate(raw_games, start=1):
            gid = game_id(raw)
            enriched_path = analysis.enriched_path(gid, request.engine_depth)
            if enriched_path.exists():
                enriched = _load_enriched(enriched_path)
            else:
                enriched = transformer.transform_game(
                    game_data=raw,
                    engine=engine,
                    position_analysis_cache=position_cache,
                    progress_callback=lambda ply, plies, i=index: emit(
                        "engine", 0.10 + 0.80 * ((i - 1) + 0.6 * ply / max(plies, 1)) / total,
                        f"Analysing game {i} of {total}", i, total,
                    ),
                    cancel_check=check_cancel,
                )
                _atomic_write_json(enriched_path, _dataclass_payload(enriched))
            enriched_games.append(enriched)

            per_game_path = analysis.per_game_path(gid, request.engine_depth, config.max_punishment_plies)
            if per_game_path.exists():
                items = _read_json(per_game_path)["mistakes"]
            else:
                emit("mistakes", 0.10 + 0.80 * (index - 0.4) / total, f"Finding mistakes in game {index} of {total}", index, total)
                result = analyze_mistakes([enriched], username=request.username, config=config, engine=engine)
                items = serializable(result.mistakes)
                _atomic_write_json(per_game_path, {"summary": serializable(result.summary), "mistakes": items})
            for item in items:
                item["mistake_id"] = _mistake_id(item)
                mistakes.append(item)
            emit("engine", 0.10 + 0.80 * index / total, f"Analysed game {index} of {total}", index, total)

    emit("plan", 0.93, "Building your training plan")
    previous = store.find(owner_id, request.username)
    previous_cards = {card["card_id"]: card for card in (previous or {}).get("cards", [])}
    plan = build_training_plan(enriched_games, mistakes, request.username, today=date.today(), previous_cards=previous_cards)
    plan["metadata"].update(
        games_removed=removed,
        engine_depth=request.engine_depth,
        requested_games=request.max_games,
        requested_time_classes=request.time_classes,
    )
    record = {
        "id": str(uuid4()),
        "username": request.username,
        "request_params": request.model_dump(),
        "created_at": _now(),
        "updated_at": _now(),
        **plan,
    }
    TrainingPlanResponse.model_validate(record)
    check_cancel()
    store.save(owner_id, request.username, record)
    emit("complete", 1.0, "Training plan ready")
    return record


def run_training_plan_job(job: Any) -> None:
    from backend.services.report_build_job_service import training_plan_jobs

    training_plan_jobs.update(job, status="running", stage="fetching_games", progress=0.01, message="Starting training plan")
    try:
        record = build_training_plan_for_player(
            job.request,
            owner_id=job.owner_id,
            progress_callback=lambda stage, progress, message, processed, total: training_plan_jobs.update(
                job, status="running", stage=stage, progress=progress, message=message, processed=processed, total=total,
            ),
            cancel_event=job.cancel_event,
        )
        training_plan_jobs.update(
            job, status="completed", stage="complete", progress=1.0, message="Training plan ready", report_id=record["id"],
        )
    except TrainingPlanCancelled:
        training_plan_jobs.update(job, status="cancelled", stage="cancelled", message="Training plan build cancelled")
    except Exception as exc:
        training_plan_jobs.update(job, status="failed", stage="failed", message="Training plan build failed", error=str(exc))
