from __future__ import annotations

import asyncio
import re

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.models import (
    DefaultHparamsResponse,
    GamesQueryRequest,
    GamesQueryResponse,
    HealthResponse,
    AuthSessionResponse,
    AuthUser,
    DashboardResponse,
    LoginRequest,
    PlayerReportsResponse,
    RegisterRequest,
    RegisterResponse,
    ReportTitleRequest,
    ResendVerificationRequest,
    VerifyEmailRequest,
    MistakePositionRequest,
    MistakePositionResponse,
    ReportGamesCatalogRequest,
    ReportGamesCatalogResponse,
    ReportMistakeDetailResponse,
    ReportMistakesResponse,
    ReportMistakesSelectionRequest,
    OpeningMatchRequest,
    OpeningMatchResponse,
    OpeningStudyTreeChildrenRequest,
    OpeningStudyTreeChildrenResponse,
    ReportBuildRequest,
    ReportBuildResponse,
    ReportBuildJobAccepted,
    ReportBuildJobStatus,
    ReportSummary,
)
from backend.services.auth_service import (
    AuthError,
    AuthRepository,
    CsrfError,
    EmailAlreadyRegistered,
    EmailNotVerified,
    InvalidCredentials,
    InvalidSession,
    InvalidVerification,
    VerificationCooldown,
    session_cookie_options,
)
from backend.services.email_service import EmailDeliveryUnavailable, send_verification_email
from backend.services.report_repository import ReportNotFound, ReportsRepository
from backend.services.chesscom_service import ChessComServiceError, UnknownChessComUser, query_games, summarize_games
from backend.services.hparams_service import load_hparams
from backend.services.mistakes_service import analyse_position
from backend.services.opening_study_service import opening_study_tree_children
from backend.services.openings_service import top_opening_matches_from_cached_report
from backend.services.statistics_service import build_report
from backend.services.report_build_job_service import (
    BuildJobNotFound,
    report_build_jobs,
    run_report_build_job,
)
from backend.services.report_analysis_service import (
    ReportAnalysisUnavailable,
    build_report_mistakes,
    get_active_report_mistakes,
    get_report_mistake_detail,
    query_report_games,
)
from backend.settings import settings


app = FastAPI(title="Chess Insighter API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


PUBLIC_HTTP_PATHS = {
    "/api/health",
    "/api/auth/register",
    "/api/auth/verify-email",
    "/api/auth/resend-verification",
    "/api/auth/login",
}


@app.middleware("http")
async def authentication_boundary(request: Request, call_next):
    if not request.url.path.startswith("/api/") or request.url.path in PUBLIC_HTTP_PATHS:
        return await call_next(request)
    encoded = request.cookies.get(settings.auth_cookie_name)
    if not encoded:
        return JSONResponse(status_code=401, content={"code": "not_authenticated", "message": "Sign in to continue."})
    try:
        user, session = AuthRepository().resolve_session(encoded)
        request.state.auth_user = user
        request.state.auth_session = session
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and origin != settings.frontend_url and re.fullmatch(settings.cors_origin_regex, origin) is None:
                raise InvalidSession("Request origin is not allowed.")
            AuthRepository().validate_csrf(
                session,
                request.cookies.get(settings.csrf_cookie_name),
                request.headers.get("x-csrf-token"),
            )
    except InvalidSession as exc:
        response_status = 403 if isinstance(exc, CsrfError) else 401
        response = JSONResponse(status_code=response_status, content={"code": exc.code, "message": str(exc)})
        if not isinstance(exc, CsrfError):
            response.delete_cookie(settings.auth_cookie_name, path="/")
            response.delete_cookie(settings.csrf_cookie_name, path="/")
        return response
    return await call_next(request)


def request_user(request: Request) -> AuthUser:
    return request.state.auth_user


@app.exception_handler(UnknownChessComUser)
async def unknown_user_handler(_request, exc: UnknownChessComUser):
    return JSONResponse(status_code=404, content={"code": "unknown_username", "message": str(exc)})


@app.exception_handler(ChessComServiceError)
async def chesscom_handler(_request, exc: ChessComServiceError):
    return JSONResponse(status_code=502, content={"code": "chesscom_error", "message": str(exc)})


@app.exception_handler(ValueError)
async def value_error_handler(_request, exc: ValueError):
    return JSONResponse(status_code=400, content={"code": "bad_request", "message": str(exc)})


@app.exception_handler(AuthError)
async def auth_error_handler(_request, exc: AuthError):
    error_status = 400
    if isinstance(exc, CsrfError):
        error_status = 403
    elif isinstance(exc, (InvalidCredentials, InvalidSession)):
        error_status = 401
    elif isinstance(exc, EmailNotVerified):
        error_status = 403
    elif isinstance(exc, EmailAlreadyRegistered):
        error_status = 409
    elif isinstance(exc, VerificationCooldown):
        error_status = 429
    return JSONResponse(status_code=error_status, content={"code": exc.code, "message": str(exc)})


@app.exception_handler(EmailDeliveryUnavailable)
async def email_delivery_handler(_request, exc: EmailDeliveryUnavailable):
    return JSONResponse(status_code=503, content={"code": "email_unavailable", "message": str(exc)})


@app.exception_handler(ReportNotFound)
async def report_not_found_handler(_request, _exc: ReportNotFound):
    return JSONResponse(status_code=404, content={"code": "report_not_found", "message": "Report not found"})


@app.exception_handler(BuildJobNotFound)
async def build_job_not_found_handler(_request, _exc: BuildJobNotFound):
    return JSONResponse(status_code=404, content={"code": "build_not_found", "message": "Build not found"})


@app.post("/api/auth/register", response_model=RegisterResponse, status_code=202)
async def register(body: RegisterRequest) -> RegisterResponse:
    response, verification_token, email = await run_in_threadpool(
        AuthRepository().prepare_registration,
        body.email,
        body.password,
    )
    await send_verification_email(recipient=email, token=verification_token)
    return response


@app.post("/api/auth/resend-verification", status_code=202)
async def resend_verification(body: ResendVerificationRequest) -> None:
    token, email, _expires_at = await run_in_threadpool(
        AuthRepository().rotate_verification,
        body.registration_id,
        body.socket_token,
    )
    await send_verification_email(recipient=email, token=token)


@app.post("/api/auth/verify-email", response_model=AuthUser)
async def verify_email(body: VerifyEmailRequest) -> AuthUser:
    return await run_in_threadpool(AuthRepository().verify_email, body.token)


@app.websocket("/api/auth/registrations/{registration_id}/status")
async def registration_status(websocket: WebSocket, registration_id: str, token: str) -> None:
    await websocket.accept()
    previous: str | None = None
    try:
        while True:
            try:
                current = await run_in_threadpool(AuthRepository().registration_status, registration_id, token)
            except InvalidVerification:
                await websocket.send_json({"status": "invalid"})
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            if current != previous:
                await websocket.send_json({"status": current})
                previous = current
            if current in {"verified", "expired"}:
                await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
                return
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return


@app.post("/api/auth/login", response_model=AuthSessionResponse)
async def login(body: LoginRequest, response: Response) -> AuthSessionResponse:
    user, stored_user = await run_in_threadpool(AuthRepository().authenticate, body.email, body.password)
    encoded, csrf_token = await run_in_threadpool(AuthRepository().create_session, stored_user["id"])
    response.set_cookie(settings.auth_cookie_name, encoded, **session_cookie_options())
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
        max_age=settings.auth_session_days * 24 * 60 * 60,
    )
    return AuthSessionResponse(user=user)


@app.get("/api/auth/me", response_model=AuthSessionResponse)
def auth_me(request: Request) -> AuthSessionResponse:
    return AuthSessionResponse(user=request_user(request))


@app.post("/api/auth/logout", status_code=204)
def logout(request: Request, response: Response) -> None:
    AuthRepository().revoke_session(request.state.auth_session["id"])
    response.delete_cookie(settings.auth_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


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
async def games_query(body: GamesQueryRequest) -> GamesQueryResponse:
    games, has_more, total_loaded = await run_in_threadpool(query_games, body)
    return GamesQueryResponse(
        items=summarize_games(body.username, games),
        page=body.page,
        page_size=body.page_size,
        has_more=has_more,
        total_loaded=total_loaded,
    )


@app.post("/api/report/build", response_model=ReportBuildResponse)
async def report_build(body: ReportBuildRequest, request: Request) -> ReportBuildResponse:
    response = await run_in_threadpool(build_report, body)
    record = await run_in_threadpool(
        ReportsRepository().record_build,
        owner_id=request_user(request).id,
        request=body,
        response=response,
    )
    response.report_id = record["id"]
    response.saved = record["status"] == "saved"
    response.title = record.get("title")
    response.request_params = record["request_params"]
    return response


@app.post("/api/report/builds", response_model=ReportBuildJobAccepted, status_code=202)
async def start_report_build(
    body: ReportBuildRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> ReportBuildJobAccepted:
    accepted, job = report_build_jobs.create(request_user(request).id, body)
    background_tasks.add_task(run_report_build_job, job)
    return accepted


@app.get("/api/report/builds/{build_id}", response_model=ReportBuildJobStatus)
async def report_build_status(build_id: str, request: Request) -> ReportBuildJobStatus:
    job = report_build_jobs.get(build_id, request_user(request).id)
    return report_build_jobs.snapshot(job)


@app.post("/api/report/builds/{build_id}/cancel", response_model=ReportBuildJobStatus)
async def cancel_report_build(build_id: str, request: Request) -> ReportBuildJobStatus:
    job = report_build_jobs.get(build_id, request_user(request).id)
    report_build_jobs.cancel(job)
    return report_build_jobs.snapshot(job)


@app.websocket("/api/report/builds/{build_id}/status")
async def report_build_status_socket(websocket: WebSocket, build_id: str, token: str) -> None:
    try:
        origin = websocket.headers.get("origin")
        if origin and origin != settings.frontend_url and re.fullmatch(settings.cors_origin_regex, origin) is None:
            raise InvalidSession("WebSocket origin is not allowed.")
        encoded = websocket.cookies.get(settings.auth_cookie_name)
        if not encoded:
            raise InvalidSession("Sign in to continue.")
        user, _session = await run_in_threadpool(AuthRepository().resolve_session, encoded)
        job = report_build_jobs.authorize_socket(build_id, user.id, token)
    except (InvalidSession, BuildJobNotFound):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    report_build_jobs.subscribe(job)
    revision = -1
    try:
        while True:
            snapshot = report_build_jobs.snapshot(job)
            if snapshot.revision != revision:
                await websocket.send_json(snapshot.model_dump())
                revision = snapshot.revision
            if snapshot.status in {"completed", "failed", "cancelled"}:
                await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
                return
            await asyncio.sleep(0.25)
    except WebSocketDisconnect:
        return
    finally:
        report_build_jobs.unsubscribe(job)


@app.exception_handler(ReportAnalysisUnavailable)
async def report_analysis_unavailable_handler(_request, exc: ReportAnalysisUnavailable):
    return JSONResponse(status_code=409, content={"code": "report_analysis_unavailable", "message": str(exc)})


@app.post("/api/reports/{report_id}/mistakes", response_model=ReportMistakesResponse)
async def report_mistakes(
    report_id: str,
    body: ReportMistakesSelectionRequest,
    request: Request,
) -> ReportMistakesResponse:
    record = ReportsRepository().get_record(request_user(request).id, report_id)
    return await run_in_threadpool(build_report_mistakes, record["cache_hash"], body)


@app.get("/api/reports/{report_id}/mistakes", response_model=ReportMistakesResponse)
async def active_report_mistakes(report_id: str, request: Request) -> ReportMistakesResponse:
    record = ReportsRepository().get_record(request_user(request).id, report_id)
    try:
        return await run_in_threadpool(get_active_report_mistakes, record["cache_hash"])
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/reports/{report_id}/mistakes/games/query", response_model=ReportGamesCatalogResponse)
async def report_mistakes_games_query(
    report_id: str,
    body: ReportGamesCatalogRequest,
    request: Request,
) -> ReportGamesCatalogResponse:
    record = ReportsRepository().get_record(request_user(request).id, report_id)
    return await run_in_threadpool(query_report_games, record["cache_hash"], body)


@app.get(
    "/api/reports/{report_id}/mistakes/{analysis_hash}/{mistake_id}",
    response_model=ReportMistakeDetailResponse,
)
async def report_mistake_detail(
    report_id: str,
    analysis_hash: str,
    mistake_id: str,
    request: Request,
) -> ReportMistakeDetailResponse:
    record = ReportsRepository().get_record(request_user(request).id, report_id)
    try:
        return await run_in_threadpool(
            get_report_mistake_detail,
            record["cache_hash"],
            analysis_hash,
            mistake_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/mistakes/position", response_model=MistakePositionResponse)
async def mistakes_position(request: MistakePositionRequest) -> MistakePositionResponse:
    return await run_in_threadpool(analyse_position, request)


@app.post("/api/openings/matches", response_model=OpeningMatchResponse)
async def opening_matches(body: OpeningMatchRequest, request: Request) -> OpeningMatchResponse:
    record = ReportsRepository().get_record(request_user(request).id, body.report_id)
    try:
        matches = await run_in_threadpool(
            top_opening_matches_from_cached_report,
            record["cache_hash"],
            match_mode=body.match_mode,
            target_color=body.target_color,
            limit=body.limit,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return OpeningMatchResponse(
        top_opening_matches=matches,
        match_mode=body.match_mode,
        target_color=body.target_color,
    )


@app.post("/api/opening-study-tree/children", response_model=OpeningStudyTreeChildrenResponse)
async def opening_study_tree(body: OpeningStudyTreeChildrenRequest, request: Request) -> OpeningStudyTreeChildrenResponse:
    if body.report_id:
        record = ReportsRepository().get_record(request_user(request).id, body.report_id)
        body = body.model_copy(update={"cache_hash": record["cache_hash"]})
    elif body.cache_hash:
        ReportsRepository().get_by_cache_hash(request_user(request).id, body.cache_hash)
    payload = await run_in_threadpool(opening_study_tree_children, body)
    return OpeningStudyTreeChildrenResponse.model_validate(payload)


@app.get("/api/dashboard", response_model=DashboardResponse)
def dashboard(request: Request) -> DashboardResponse:
    return ReportsRepository().dashboard(request_user(request).id)


@app.get("/api/players/{username}/reports", response_model=PlayerReportsResponse)
def player_reports(username: str, request: Request) -> PlayerReportsResponse:
    return PlayerReportsResponse(
        username=username,
        reports=ReportsRepository().list_player(request_user(request).id, username),
    )


@app.get("/api/reports/{report_id}", response_model=ReportBuildResponse)
def get_report(report_id: str, request: Request) -> ReportBuildResponse:
    return ReportsRepository().load_report(request_user(request).id, report_id)


@app.post("/api/reports/{report_id}/save", response_model=ReportSummary)
def save_report(report_id: str, body: ReportTitleRequest, request: Request) -> ReportSummary:
    return ReportsRepository().save(request_user(request).id, report_id, body.title)


@app.patch("/api/reports/{report_id}", response_model=ReportSummary)
def rename_report(report_id: str, body: ReportTitleRequest, request: Request) -> ReportSummary:
    return ReportsRepository().rename(request_user(request).id, report_id, body.title)


@app.delete("/api/reports/{report_id}", status_code=204)
def delete_report(report_id: str, request: Request) -> None:
    ReportsRepository().delete(request_user(request).id, report_id)
