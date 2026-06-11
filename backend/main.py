from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from backend.models import (
    DefaultHparamsResponse,
    GamesQueryRequest,
    GamesQueryResponse,
    HealthResponse,
    OpeningMatchRequest,
    OpeningMatchResponse,
    OpeningStudyTreeChildrenRequest,
    OpeningStudyTreeChildrenResponse,
    ReportBuildRequest,
    ReportBuildResponse,
    SavedReportsList,
)
from backend.services.cache_service import ReportCache
from backend.services.saved_reports_service import SavedReportsIndex
from backend.services.chesscom_service import ChessComServiceError, UnknownChessComUser, query_games, summarize_games
from backend.services.hparams_service import load_hparams
from backend.services.opening_study_service import opening_study_tree_children
from backend.services.openings_service import top_opening_matches_from_cached_report
from backend.services.statistics_service import build_report
from backend.settings import settings


app = FastAPI(title="Chess Insighter API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(UnknownChessComUser)
async def unknown_user_handler(_request, exc: UnknownChessComUser):
    return JSONResponse(status_code=404, content={"code": "unknown_username", "message": str(exc)})


@app.exception_handler(ChessComServiceError)
async def chesscom_handler(_request, exc: ChessComServiceError):
    return JSONResponse(status_code=502, content={"code": "chesscom_error", "message": str(exc)})


@app.exception_handler(ValueError)
async def value_error_handler(_request, exc: ValueError):
    return JSONResponse(status_code=400, content={"code": "bad_request", "message": str(exc)})


@app.exception_handler(FileNotFoundError)
async def file_not_found_handler(_request, exc: FileNotFoundError):
    return JSONResponse(status_code=500, content={"code": "missing_dataset", "message": str(exc)})


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        datasets={
            "hparams": settings.hparams_path.exists(),
            "openings": settings.openings_path.exists(),
            "opening_vectors": settings.opening_vectors_path.exists(),
        },
        stockfish_available=settings.stockfish_path is not None,
    )


@app.get("/api/config/default-hparams", response_model=DefaultHparamsResponse)
def default_hparams() -> DefaultHparamsResponse:
    return DefaultHparamsResponse(hparams=load_hparams(settings.hparams_path))


@app.post("/api/games/query", response_model=GamesQueryResponse)
async def games_query(request: GamesQueryRequest) -> GamesQueryResponse:
    games, has_more, total_loaded = await run_in_threadpool(query_games, request)
    return GamesQueryResponse(
        items=summarize_games(request.username, games),
        page=request.page,
        page_size=request.page_size,
        has_more=has_more,
        total_loaded=total_loaded,
    )


@app.post("/api/report/build", response_model=ReportBuildResponse)
async def report_build(request: ReportBuildRequest) -> ReportBuildResponse:
    return await run_in_threadpool(build_report, request)


@app.post("/api/openings/matches", response_model=OpeningMatchResponse)
async def opening_matches(request: OpeningMatchRequest) -> OpeningMatchResponse:
    try:
        matches = await run_in_threadpool(
            top_opening_matches_from_cached_report,
            request.cache_hash,
            match_mode=request.match_mode,
            target_color=request.target_color,
            limit=request.limit,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return OpeningMatchResponse(
        top_opening_matches=matches,
        match_mode=request.match_mode,
        target_color=request.target_color,
    )


@app.post("/api/opening-study-tree/children", response_model=OpeningStudyTreeChildrenResponse)
async def opening_study_tree(request: OpeningStudyTreeChildrenRequest) -> OpeningStudyTreeChildrenResponse:
    payload = await run_in_threadpool(opening_study_tree_children, request)
    return OpeningStudyTreeChildrenResponse.model_validate(payload)


@app.get("/api/report/cache/{cache_hash}", response_model=ReportBuildResponse)
def report_cache(cache_hash: str) -> ReportBuildResponse:
    cached = ReportCache().get(cache_hash)
    if cached is None:
        raise HTTPException(status_code=404, detail="Report cache entry not found")
    cached["cache_hit"] = True
    return ReportBuildResponse.model_validate(cached)


@app.get("/api/reports/saved", response_model=SavedReportsList)
def list_saved_reports() -> SavedReportsList:
    return SavedReportsList(entries=SavedReportsIndex().load())


@app.delete("/api/reports/saved/{cache_hash}", status_code=204)
def delete_saved_report(cache_hash: str) -> None:
    SavedReportsIndex().delete(cache_hash)
