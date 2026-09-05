from __future__ import annotations

from contextlib import nullcontext
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import threading
from typing import Any
from uuid import uuid4

import chess.engine

from backend.models import (
    GameSummary,
    GamesQueryRequest,
    ReportAnalysisContext,
    ReportGamesCatalogRequest,
    ReportGamesCatalogResponse,
    ReportMistakeDetailResponse,
    ReportMistakesResponse,
    ReportMistakesSelectionRequest,
)
from backend.services.cache_service import stable_hash
from backend.services.chesscom_service import query_games, summarize_game, summarize_games
from backend.services.openings_service import serializable
from backend.settings import settings
from utils.game_enrichment_transformer import (
    EnrichedGame,
    EnrichedMove,
    GameEnrichmentTransformer,
    TopEngineMove,
)
from utils.mistakes_analyzer import MistakeAnalyzerConfig, analyze_mistakes
from utils.opening_repository import OpeningRepository


SIDECAR_VERSION = 1
ANALYZER_VERSION = "mistakes-v5"
_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


class ReportAnalysisUnavailable(RuntimeError):
    pass


def _report_lock(cache_hash: str) -> threading.RLock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(cache_hash, threading.RLock())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _game_identifier(game: Any) -> str | None:
    if isinstance(game, dict):
        return game.get("uuid") or game.get("url") or game.get("id")
    return getattr(game, "uuid", None) or getattr(game, "url", None)


def _artifact_key(game_id: str) -> str:
    return stable_hash({"game_id": game_id})


def _mistake_id(mistake: dict[str, Any]) -> str:
    game_id = mistake.get("game_uuid") or mistake.get("game_url") or "unknown-game"
    return stable_hash(
        {
            "game_id": game_id,
            "ply": mistake.get("ply"),
            "move": mistake.get("uci") or mistake.get("san"),
        }
    )


class ReportAnalysisStore:
    def __init__(self, cache_hash: str, root: Path | None = None):
        self.cache_hash = cache_hash
        self.root = (root or settings.report_analysis_cache_dir) / cache_hash

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    @property
    def active_path(self) -> Path:
        return self.root / "active.json"

    def lock(self) -> threading.RLock:
        return _report_lock(self.cache_hash)

    def exists(self) -> bool:
        return self.manifest_path.exists()

    def manifest(self) -> dict[str, Any]:
        if not self.exists():
            raise ReportAnalysisUnavailable(
                "This report predates reusable game analysis. Rebuild it with the engine enabled."
            )
        return _read_json(self.manifest_path)

    def write_manifest(self, manifest: dict[str, Any]) -> None:
        manifest["updated_at"] = _now()
        _atomic_write_json(self.manifest_path, manifest)

    def raw_path(self, game_id: str) -> Path:
        return self.root / "raw" / f"{_artifact_key(game_id)}.json"

    def enriched_path(self, game_id: str, depth: int) -> Path:
        return self.root / "enriched" / f"depth-{depth}" / f"{_artifact_key(game_id)}.json"

    def per_game_path(self, game_id: str, depth: int, plies: int) -> Path:
        return (
            self.root
            / "per_game"
            / ANALYZER_VERSION
            / f"depth-{depth}-plies-{plies}"
            / f"{_artifact_key(game_id)}.json"
        )

    def analysis_path(self, analysis_hash: str) -> Path:
        return self.root / "analyses" / f"{analysis_hash}.json"


def initialize_report_analysis(
    *,
    cache_hash: str,
    username: str,
    raw_games: list[dict[str, Any]],
    enriched_games: list[Any],
    engine_depth: int,
    engine_enriched: bool,
    filters: dict[str, Any],
    refresh: bool,
) -> ReportAnalysisContext:
    store = ReportAnalysisStore(cache_hash)
    with store.lock():
        if refresh and store.root.exists():
            shutil.rmtree(store.root)

        raw_by_id = {
            identifier: game
            for game in raw_games
            if (identifier := _game_identifier(game)) is not None
        }
        records: dict[str, Any] = {}
        context_games: list[GameSummary] = []
        default_ids: list[str] = []

        for enriched in enriched_games:
            game_id = _game_identifier(enriched)
            raw = raw_by_id.get(game_id or "")
            if game_id is None or raw is None:
                continue
            summary = summarize_game(username, raw)
            records[game_id] = {
                "id": game_id,
                "aliases": sorted({value for value in [raw.get("uuid"), raw.get("url")] if value}),
                "summary": summary.model_dump(),
                "source": "report",
            }
            _atomic_write_json(store.raw_path(game_id), raw)
            _atomic_write_json(store.enriched_path(game_id, engine_depth), _dataclass_payload(enriched))
            context_games.append(summary)
            default_ids.append(game_id)

        if not default_ids:
            raise ValueError("No report games could be stored for mistakes analysis.")

        sidecar_id = uuid4().hex
        manifest = {
            "version": SIDECAR_VERSION,
            "cache_hash": cache_hash,
            "sidecar_id": sidecar_id,
            "username": username,
            "created_at": _now(),
            "report_engine_depth": engine_depth,
            "engine_enriched": bool(engine_enriched),
            "filters": filters,
            "default_game_ids": default_ids,
            "games": records,
        }
        store.write_manifest(manifest)
        return ReportAnalysisContext(
            games=context_games,
            default_game_ids=default_ids,
            engine_depth=engine_depth,
            engine_enriched=bool(engine_enriched),
            sidecar_id=sidecar_id,
        )


def query_report_games(
    cache_hash: str,
    request: ReportGamesCatalogRequest,
) -> ReportGamesCatalogResponse:
    store = ReportAnalysisStore(cache_hash)
    with store.lock():
        manifest = store.manifest()
        query_key = stable_hash(
            {
                "time_classes": request.time_classes,
                "rated_filter": request.rated_filter,
                "since_year": request.since_year,
                "since_month": request.since_month,
                "until_year": request.until_year,
                "until_month": request.until_month,
            }
        )
        catalog_path = store.root / "catalogs" / f"{query_key}.json"
        cache_hit = catalog_path.exists()
        if cache_hit:
            raw_games = _read_json(catalog_path)["games"]
        else:
            raw_games, _has_more, _total = query_games(
                GamesQueryRequest(
                    username=manifest["username"],
                    page=1,
                    page_size=500,
                    time_classes=request.time_classes,
                    rated_filter=request.rated_filter,
                    since_year=request.since_year,
                    since_month=request.since_month,
                    until_year=request.until_year,
                    until_month=request.until_month,
                )
            )
            _atomic_write_json(catalog_path, {"created_at": _now(), "games": raw_games})

        summaries = summarize_games(manifest["username"], raw_games)
        if request.result_filter:
            allowed = set(request.result_filter)
            pairs = [pair for pair in zip(raw_games, summaries) if pair[1].result in allowed]
        else:
            pairs = list(zip(raw_games, summaries))

        records = manifest["games"]
        for raw, summary in pairs:
            game_id = _game_identifier(raw)
            if game_id is None:
                continue
            previous = records.get(game_id, {})
            records[game_id] = {
                "id": game_id,
                "aliases": sorted({value for value in [raw.get("uuid"), raw.get("url")] if value}),
                "summary": summary.model_dump(),
                "source": previous.get("source", "catalog"),
            }
            if not store.raw_path(game_id).exists():
                _atomic_write_json(store.raw_path(game_id), raw)
        store.write_manifest(manifest)

        start = (request.page - 1) * request.page_size
        end = start + request.page_size
        items = [summary for _raw, summary in pairs]
        return ReportGamesCatalogResponse(
            items=items[start:end],
            page=request.page,
            page_size=request.page_size,
            has_more=end < len(items),
            total_loaded=len(items),
            cache_hit=cache_hit,
        )


def build_report_mistakes(
    cache_hash: str,
    request: ReportMistakesSelectionRequest,
) -> ReportMistakesResponse:
    store = ReportAnalysisStore(cache_hash)
    with store.lock():
        manifest = store.manifest()
        if not manifest.get("engine_enriched"):
            raise ReportAnalysisUnavailable(
                "Mistakes analysis requires an engine-enriched report. Rebuild with engine enabled and refresh cache."
            )
        selected_ids = _resolve_selected_ids(manifest, request.selected_game_ids)
        analysis_hash = stable_hash(
            {
                "version": ANALYZER_VERSION,
                "games": sorted(selected_ids),
                "engine_depth": request.engine_depth,
                "max_punishment_plies": request.max_punishment_plies,
            }
        )
        aggregate_path = store.analysis_path(analysis_hash)
        if aggregate_path.exists():
            payload = _read_json(aggregate_path)
            payload["cache_hit"] = True
            _write_active(store, payload, request)
            return ReportMistakesResponse.model_validate(payload)

        missing_enrichment = [
            game_id
            for game_id in selected_ids
            if not store.enriched_path(game_id, request.engine_depth).exists()
        ]
        missing_analysis = [
            game_id
            for game_id in selected_ids
            if not store.per_game_path(
                game_id,
                request.engine_depth,
                request.max_punishment_plies,
            ).exists()
        ]

        engine_path = settings.stockfish_path
        if (missing_enrichment or missing_analysis) and not engine_path:
            raise ValueError("Stockfish is required for mistakes analysis.")

        engine_context = (
            chess.engine.SimpleEngine.popen_uci(engine_path)
            if missing_enrichment or missing_analysis
            else nullcontext(None)
        )
        with engine_context as engine:
            if missing_enrichment:
                _enrich_missing_games(
                    store,
                    missing_enrichment,
                    request.engine_depth,
                    engine,
                    engine_path or "",
                )
            if missing_analysis:
                _analyze_missing_games(store, manifest, missing_analysis, request, engine)

        payload = _aggregate_analysis(store, manifest, selected_ids, request, analysis_hash)
        _atomic_write_json(aggregate_path, payload)
        _write_active(store, payload, request)
        return ReportMistakesResponse.model_validate(payload)


def get_active_report_mistakes(cache_hash: str) -> ReportMistakesResponse:
    store = ReportAnalysisStore(cache_hash)
    with store.lock():
        store.manifest()
        if not store.active_path.exists():
            raise FileNotFoundError("No mistakes analysis has been run for this report.")
        active = _read_json(store.active_path)
        if active.get("analyzer_version") != ANALYZER_VERSION:
            raise FileNotFoundError("The saved mistakes analysis uses an older analyzer version.")
        payload = _read_json(store.analysis_path(active["analysis_hash"]))
        if payload.get("metadata", {}).get("analyzer_version") != ANALYZER_VERSION:
            raise FileNotFoundError("The saved mistakes analysis uses an older analyzer version.")
        payload["cache_hit"] = True
        payload["metadata"]["picker_filters"] = active.get("picker_filters")
        return ReportMistakesResponse.model_validate(payload)


def get_report_mistake_detail(
    cache_hash: str,
    analysis_hash: str,
    mistake_id: str,
) -> ReportMistakeDetailResponse:
    store = ReportAnalysisStore(cache_hash)
    with store.lock():
        manifest = store.manifest()
        path = store.analysis_path(analysis_hash)
        if not path.exists():
            raise FileNotFoundError("Mistakes analysis not found.")
        payload = _read_json(path)
        if payload.get("metadata", {}).get("analyzer_version") != ANALYZER_VERSION:
            raise FileNotFoundError("Mistakes analysis not found for the current analyzer version.")
        mistake = next(
            (item for item in payload["mistakes"] if item.get("mistake_id") == mistake_id),
            None,
        )
        if mistake is None:
            raise FileNotFoundError("Mistake not found in this analysis.")
        selected_games = [
            GameSummary.model_validate(manifest["games"][game_id]["summary"])
            for game_id in payload["metadata"]["selected_game_ids"]
        ]
        return ReportMistakeDetailResponse(
            analysis_hash=analysis_hash,
            mistake=mistake,
            selected_games=selected_games,
            metadata=payload["metadata"],
        )


def _resolve_selected_ids(manifest: dict[str, Any], requested: list[str]) -> list[str]:
    aliases = {
        alias: game_id
        for game_id, record in manifest["games"].items()
        for alias in [game_id, *record.get("aliases", [])]
    }
    missing = sorted({game_id for game_id in requested if game_id not in aliases})
    if missing:
        raise ValueError("Selected games are not in this report catalog: " + ", ".join(missing))
    resolved = [aliases[game_id] for game_id in requested]
    if len(resolved) != len(set(resolved)):
        raise ValueError("Selected game IDs resolve to duplicate games")
    return resolved


def _enrich_missing_games(
    store: ReportAnalysisStore,
    game_ids: list[str],
    depth: int,
    engine: Any,
    engine_path: str,
) -> None:
    transformer = GameEnrichmentTransformer(
        stockfish_path=engine_path,
        opening_repository=OpeningRepository(settings.openings_path),
        engine_limit=chess.engine.Limit(depth=depth),
    )
    position_cache: dict[str, Any] = {}
    for game_id in game_ids:
        raw = _read_json(store.raw_path(game_id))
        enriched = transformer.transform_game(
            game_data=raw,
            engine=engine,
            position_analysis_cache=position_cache,
        )
        _atomic_write_json(store.enriched_path(game_id, depth), asdict(enriched))


def _analyze_missing_games(
    store: ReportAnalysisStore,
    manifest: dict[str, Any],
    game_ids: list[str],
    request: ReportMistakesSelectionRequest,
    engine: Any,
) -> None:
    config = MistakeAnalyzerConfig(
        engine_depth=request.engine_depth,
        max_punishment_plies=request.max_punishment_plies,
    )
    for game_id in game_ids:
        game = _load_enriched(store.enriched_path(game_id, request.engine_depth))
        analysis = analyze_mistakes(
            [game],
            username=manifest["username"],
            config=config,
            engine=engine,
        )
        _atomic_write_json(
            store.per_game_path(game_id, request.engine_depth, request.max_punishment_plies),
            {"summary": serializable(analysis.summary), "mistakes": serializable(analysis.mistakes)},
        )


def _aggregate_analysis(
    store: ReportAnalysisStore,
    manifest: dict[str, Any],
    selected_ids: list[str],
    request: ReportMistakesSelectionRequest,
    analysis_hash: str,
) -> dict[str, Any]:
    summaries: list[dict[str, Any]] = []
    mistakes: list[dict[str, Any]] = []
    for game_id in selected_ids:
        per_game = _read_json(
            store.per_game_path(game_id, request.engine_depth, request.max_punishment_plies)
        )
        summaries.append(per_game["summary"])
        for item in per_game["mistakes"]:
            item["mistake_id"] = _mistake_id(item)
            mistakes.append(item)
    mistakes.sort(key=lambda item: ((item.get("wp_loss") or 0), (item.get("cp_loss") or 0)), reverse=True)
    depths = [item["theoretical_punishment_depth"] for item in mistakes]
    severity_counts = _sum_count_maps(summaries, "severity_counts")
    theme_counts = _sum_count_maps(summaries, "theme_counts")
    summary = {
        "games_analyzed": len(selected_ids),
        "target_moves_analyzed": sum(item["target_moves_analyzed"] for item in summaries),
        "mistake_count": len(mistakes),
        "severity_counts": severity_counts,
        "theme_counts": theme_counts,
        "average_theoretical_punishment_depth": sum(depths) / len(depths) if depths else None,
        "actual_punished_count": sum(1 for item in mistakes if item.get("actual_punished")),
    }
    return {
        "analysis_hash": analysis_hash,
        "cache_hit": False,
        "selected_games": [manifest["games"][game_id]["summary"] for game_id in selected_ids],
        "metadata": {
            "username": manifest["username"],
            "selected_game_ids": selected_ids,
            "engine_used": True,
            "engine_depth": request.engine_depth,
            "max_punishment_plies": request.max_punishment_plies,
            "analyzer_version": ANALYZER_VERSION,
            "picker_filters": request.picker_filters,
            "created_at": _now(),
        },
        "summary": summary,
        "mistakes": mistakes,
    }


def _sum_count_maps(summaries: list[dict[str, Any]], key: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for summary in summaries:
        for name, count in summary.get(key, {}).items():
            result[name] = result.get(name, 0) + int(count)
    return result


def _write_active(
    store: ReportAnalysisStore,
    payload: dict[str, Any],
    request: ReportMistakesSelectionRequest,
) -> None:
    _atomic_write_json(
        store.active_path,
        {
            "analysis_hash": payload["analysis_hash"],
            "selected_game_ids": request.selected_game_ids,
            "engine_depth": request.engine_depth,
            "max_punishment_plies": request.max_punishment_plies,
            "analyzer_version": ANALYZER_VERSION,
            "picker_filters": request.picker_filters,
            "updated_at": _now(),
        },
    )


def _dataclass_payload(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return value
    raise TypeError(f"Unsupported enriched game payload: {type(value).__name__}")


def _load_enriched(path: Path) -> EnrichedGame:
    payload = _read_json(path)
    moves = []
    for move in payload.pop("moves"):
        move["top_engine_moves"] = [TopEngineMove(**item) for item in move["top_engine_moves"]]
        moves.append(EnrichedMove(**move))
    return EnrichedGame(moves=moves, **payload)
