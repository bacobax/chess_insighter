from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


JsonObject = dict[str, Any]


class ApiError(BaseModel):
    code: str
    message: str
    details: JsonObject | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    datasets: dict[str, bool]
    stockfish_available: bool


class DefaultHparamsResponse(BaseModel):
    hparams: JsonObject


class GameFilters(BaseModel):
    time_classes: list[str] | None = None
    rated_filter: bool | None = None
    since_year: int | None = None
    since_month: int | None = None
    until_year: int | None = None
    until_month: int | None = None

    @field_validator("time_classes")
    @classmethod
    def normalize_time_classes(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = sorted({item.strip().lower() for item in value if item.strip()})
        return normalized or None

    @field_validator("since_month", "until_month")
    @classmethod
    def validate_month(cls, value: int | None) -> int | None:
        if value is not None and not 1 <= value <= 12:
            raise ValueError("month must be between 1 and 12")
        return value


class GamesQueryRequest(GameFilters):
    username: str
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=500)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        username = value.strip()
        if not username:
            raise ValueError("username is required")
        return username


class GameSummary(BaseModel):
    id: str | None
    url: str | None
    result: Literal["win", "loss", "draw", "unknown"]
    player_username: str
    player_color: Literal["white", "black"]
    player_elo_before: int | None
    player_elo_after: int | None
    opponent_username: str | None
    opponent_elo_before: int | None
    opponent_elo_after: int | None
    opponent_result: str | None
    end_time: int | None
    end_time_iso: str | None
    time_class: str | None
    time_control: str | None
    rated: bool | None
    opening_eco: str | None
    opening_name: str | None


class GamesQueryResponse(BaseModel):
    items: list[GameSummary]
    page: int
    page_size: int
    has_more: bool
    total_loaded: int


class ReportBuildRequest(GameFilters):
    username: str
    hparams: JsonObject
    max_games: int = Field(default=20, ge=1, le=500)
    engine_depth: int = Field(default=10, ge=1, le=30)
    use_engine: bool = True
    refresh_cache: bool = False
    target_color: Literal["white", "black", "both"] = "both"

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        username = value.strip()
        if not username:
            raise ValueError("username is required")
        return username


class ReportMistakesSelectionRequest(BaseModel):
    selected_game_ids: list[str] = Field(min_length=1, max_length=500)
    engine_depth: int = Field(default=10, ge=1, le=30)
    max_punishment_plies: int = Field(default=8, ge=1, le=20)
    picker_filters: JsonObject | None = None

    @field_validator("selected_game_ids")
    @classmethod
    def normalize_selected_game_ids(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if not normalized:
            raise ValueError("at least one game is required")
        if len(normalized) != len(set(normalized)):
            raise ValueError("selected game IDs must be unique")
        return normalized


class ReportGamesCatalogRequest(GameFilters):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)
    result_filter: list[Literal["win", "loss", "draw", "unknown"]] | None = None

    @field_validator("result_filter")
    @classmethod
    def normalize_result_filter(
        cls,
        value: list[Literal["win", "loss", "draw", "unknown"]] | None,
    ) -> list[Literal["win", "loss", "draw", "unknown"]] | None:
        if value is None:
            return None
        normalized = sorted(set(value))
        return normalized or None


class ReportMistakesResponse(BaseModel):
    analysis_hash: str
    cache_hit: bool
    selected_games: list[GameSummary]
    metadata: JsonObject
    summary: JsonObject
    mistakes: list[JsonObject]


class ReportGamesCatalogResponse(GamesQueryResponse):
    cache_hit: bool


class ReportMistakeDetailResponse(BaseModel):
    analysis_hash: str
    mistake: JsonObject
    selected_games: list[GameSummary]
    metadata: JsonObject


class MetricPoint(BaseModel):
    key: str
    label: str
    value: float | None
    direction: Literal["higher", "lower"] = "higher"


class OpeningCount(BaseModel):
    name: str
    count: int
    color: Literal["white", "black"]


class OpeningMatch(BaseModel):
    opening_name: str
    similarity_score: float | None
    weighted_cosine_score: float | None = None
    dot_product_score: float | None = None
    match_mode: Literal["cosine", "dot_product"] = "cosine"
    structure_distribution_similarity: float | None = None
    target_color: Literal["white", "black", "both"] | None = None
    used_vector_color: Literal["white", "black", "global"] = "global"
    eco_values: str | None
    line_count: int | None
    representative_pgn: str | None
    representative_uci: str | None
    fen: str | None
    used_features: list[str]


class OpeningMatchRequest(BaseModel):
    report_id: str
    match_mode: Literal["cosine", "dot_product"] = "cosine"
    target_color: Literal["white", "black", "both"] = "both"
    limit: int = Field(default=15, ge=1, le=50)


class OpeningMatchResponse(BaseModel):
    top_opening_matches: list[OpeningMatch]
    match_mode: Literal["cosine", "dot_product"]
    target_color: Literal["white", "black", "both"]


class OpeningStudyWeights(BaseModel):
    player_style_match: float | None = Field(default=None, alias="playerStyleMatch")
    engine_soundness: float | None = Field(default=None, alias="engineSoundness")
    aggressiveness: float | None = None
    practical_gamble: float | None = Field(default=None, alias="practicalGamble")
    systemness: float | None = None
    memory_simplicity: float | None = Field(default=None, alias="memorySimplicity")

    model_config = {"populate_by_name": True}

    def to_weights(self) -> dict[str, float]:
        mapping = {
            "player_style_match": self.player_style_match,
            "engine_soundness": self.engine_soundness,
            "aggressiveness": self.aggressiveness,
            "practical_gamble": self.practical_gamble,
            "systemness": self.systemness,
            "memory_simplicity": self.memory_simplicity,
        }
        return {key: float(value) for key, value in mapping.items() if value is not None}


class OpeningStudyTreeChildrenRequest(BaseModel):
    # Preferred: cache_hash from a previously built player report. The player
    # vector is then loaded from the report cache, respecting the exact game
    # filters (time class, rated, date range, max games) used in that report.
    cache_hash: str | None = Field(default=None, alias="cacheHash")
    report_id: str | None = Field(default=None, alias="reportId")
    # Fallback: resolve from the flat player_vectors.json by username. Ignores
    # game filters — uses whichever vector was most recently cached.
    username: str | None = None
    player_vector_cache_path: str | None = Field(default=None, alias="playerVectorCachePath")
    opening_vectors_path: str | None = Field(default=None, alias="openingVectorsPath")
    target_color: Literal["white", "black"] = Field(alias="targetColor")
    prefix_uci: list[str] = Field(default_factory=list, alias="prefixUci")
    top_k: int = Field(default=4, ge=1, le=20, alias="topK")
    opponent_top_k: int = Field(default=8, ge=1, le=30, alias="opponentTopK")
    opponent_move_ordering: Literal["engine", "popularity"] = Field(
        default="engine", alias="opponentMoveOrdering"
    )
    weights: OpeningStudyWeights | None = None
    similarity_type: Literal["cosine", "dot_product"] = Field(default="cosine", alias="similarityType")
    weighted_matching: bool = Field(default=True, alias="weightedMatching")
    matcher_weights: dict[str, float] | None = Field(default=None, alias="matcherWeights")
    # Match mode controls the non-evaluation scoring dimensions. The separate
    # evaluationMetric field selects exactly one of Engine or Practical Gamble.
    #   "style"  — player_style_match + selected evaluation + systemness + memory
    #   "custom" — selected evaluation + aggro + systemness + memory
    match_mode: Literal["style", "custom"] = Field(default="style", alias="matchMode")
    evaluation_metric: Literal["engine", "practical"] = Field(default="engine", alias="evaluationMetric")

    model_config = {"populate_by_name": True}


class OpeningStudyNodeStats(BaseModel):
    playerStyleMatch: float
    engineSoundness: float
    aggressiveness: float
    practicalGamble: float | None = None
    memoryComplexity: float
    systemness: float


class MetricComponent(BaseModel):
    key: str
    label: str
    value: float
    weight: float
    rawValue: float | None = None
    rawUnit: str | None = None


class StyleMatchComponent(BaseModel):
    key: str
    label: str
    playerValue: float
    openingValue: float
    weight: float


class NodeBreakdown(BaseModel):
    aggressiveness: list[MetricComponent] = Field(default_factory=list)
    memoryComplexity: list[MetricComponent] = Field(default_factory=list)
    systemness: list[MetricComponent] = Field(default_factory=list)
    engineSoundness: list[MetricComponent] = Field(default_factory=list)
    playerStyleMatch: list[StyleMatchComponent] = Field(default_factory=list)
    openingFeatures: dict[str, float] = Field(default_factory=dict)


class OpeningStudyTreeNodeModel(BaseModel):
    moveUci: str
    moveSan: str
    fen: str
    prefixUci: list[str]
    compatibleLineCount: int
    openingNames: list[str]
    representativeUci: str | None = None
    representativePgn: str | None = None
    playerStyleMatch: float
    engineSoundness: float
    popularityScore: float = 0.0
    popularityGames: int = 0
    aggressiveness: float
    practicalGamble: float | None = None
    practicalGambleRaw: float | None = None
    practicalGambleSampleSize: int = 0
    practicalGambleCoverage: float = 0.0
    memoryComplexity: float
    systemness: float
    studyScore: float
    sideToMove: Literal["white", "black"]
    targetColor: Literal["white", "black"]
    isTargetMove: bool
    boardPreviewFen: str
    stats: OpeningStudyNodeStats
    breakdown: NodeBreakdown = Field(default_factory=NodeBreakdown)


class OpeningStudyTreeChildrenResponse(BaseModel):
    targetColor: Literal["white", "black"]
    prefixUci: list[str]
    children: list[OpeningStudyTreeNodeModel]
    vectorSource: str | None = None
    playerVector: dict[str, float] | None = None


class OpeningReportGroup(BaseModel):
    opening_characteristics: list[MetricPoint]


class ReportCharts(BaseModel):
    skill_profile: list[MetricPoint]
    favourite_openings: list[OpeningCount]
    opening_characteristics: list[MetricPoint]
    opening_report_groups: dict[str, OpeningReportGroup] = Field(default_factory=dict)
    opening_components: list[MetricPoint]
    time_management_indicators: list[MetricPoint]
    advantage_capitalization_components: list[MetricPoint]
    resourcefulness_components: list[MetricPoint]
    game_analysis_components: list[MetricPoint]
    average_time_by_complexity: list[MetricPoint]


class ReportAnalysisContext(BaseModel):
    games: list[GameSummary]
    default_game_ids: list[str]
    engine_depth: int
    engine_enriched: bool
    sidecar_id: str | None = None


class ReportPayload(BaseModel):
    metadata: JsonObject
    statistics_bundle: JsonObject
    charts: ReportCharts
    analysis_context: ReportAnalysisContext | None = None


class ReportBuildResponse(BaseModel):
    cache_hash: str
    cache_hit: bool
    normalized_hparams: JsonObject
    report: ReportPayload
    report_id: str | None = None
    saved: bool = False
    title: str | None = None
    request_params: JsonObject | None = None


class ReportBuildJobAccepted(BaseModel):
    build_id: str
    socket_token: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]


class ReportBuildJobStatus(BaseModel):
    build_id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    stage: str
    progress: float = Field(ge=0, le=1)
    message: str
    revision: int
    processed: int | None = None
    total: int | None = None
    report_id: str | None = None
    error: str | None = None


class SavedReportEntry(BaseModel):
    cache_hash: str
    username: str
    created_at: str
    last_refreshed_at: str
    games_analyzed: int
    request_params: JsonObject


class SavedReportsList(BaseModel):
    entries: list[SavedReportEntry]


class SaveReportRequest(BaseModel):
    cache_hash: str
    username: str
    games_analyzed: int
    request_params: JsonObject


class AuthUser(BaseModel):
    id: str
    email: str
    created_at: str
    verified_at: str


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise ValueError("Enter a valid email address")
        return email


class RegisterResponse(BaseModel):
    registration_id: str
    socket_token: str
    expires_at: str


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)


class ResendVerificationRequest(BaseModel):
    registration_id: str
    socket_token: str


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthSessionResponse(BaseModel):
    user: AuthUser


class ReportTitleRequest(BaseModel):
    title: str | None = Field(default=None, max_length=80)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        title = value.strip()
        return title or None


class ReportSummary(BaseModel):
    id: str
    username: str
    generated_label: str
    title: str | None = None
    cache_hash: str
    games_analyzed: int
    request_params: JsonObject
    created_at: str
    updated_at: str
    saved_at: str


class PlayerReportsResponse(BaseModel):
    username: str
    reports: list[ReportSummary]


class DashboardPlayer(BaseModel):
    username: str
    report_count: int
    latest_report_at: str
    reports: list[ReportSummary]


class DashboardResponse(BaseModel):
    user: AuthUser
    report_count: int
    player_count: int
    latest_activity_at: str | None
    players: list[DashboardPlayer]


class MistakePositionRequest(BaseModel):
    fen: str
    player_color: Literal["white", "black"]
    rating: int = Field(default=1500, ge=100, le=3500)
    engine_depth: int = Field(default=10, ge=1, le=30)
    max_plies: int = Field(default=6, ge=1, le=20)


class MistakePositionResponse(BaseModel):
    top_lines: list[JsonObject]
    optimal_line: list[JsonObject]
