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
    # Match mode controls the soft-ranking dimensions. The separate selected
    # evaluation signal is a hard feasibility threshold for the player's moves.
    #   "style"  — player_style_match + systemness + memory
    #   "custom" — aggro + systemness + memory
    # "style" is in development and currently coerced to "custom" by the service.
    match_mode: Literal["style", "custom"] = Field(default="custom", alias="matchMode")
    evaluation_metric: Literal["engine", "practical"] = Field(default="engine", alias="evaluationMetric")
    evaluation_threshold: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        alias="evaluationThreshold",
    )

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


class NodeExplanationFactor(BaseModel):
    key: str
    label: str
    value: float
    referenceValue: float
    # Share of the score gap to `comparedTo`, in score points (0-100 scale).
    contribution: float


class NodeExplanation(BaseModel):
    summary: str = ""
    comparedTo: str | None = None
    scoreGap: float | None = None
    factors: list[NodeExplanationFactor] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    feasibility: str | None = None


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
    explanation: NodeExplanation = Field(default_factory=NodeExplanation)


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


class TrainingPlanBuildRequest(BaseModel):
    username: str
    max_games: int = Field(default=80, ge=10, le=150)
    time_classes: list[Literal["bullet", "blitz", "rapid", "daily"]] | None = None
    engine_depth: int = Field(default=12, ge=6, le=22)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        username = value.strip()
        if not username:
            raise ValueError("username is required")
        return username

    @field_validator("time_classes")
    @classmethod
    def normalize_time_classes(cls, value: list[str] | None) -> list[str] | None:
        return sorted(set(value)) or None if value else None


class TrainingProcessTag(BaseModel):
    tag: str
    title: str
    count: int
    rate_per_100: float
    share: float
    avg_wp_loss: float | None = None


class TrainingWeakness(TrainingProcessTag):
    definition: str
    training: str
    secondary: str


class TrainingDomainCount(BaseModel):
    domain: Literal["opening", "middlegame_tactics", "middlegame_positional", "endgame"]
    count: int
    share: float


class TrainingMotif(BaseModel):
    motif: str
    count: int
    games: int
    own_block: bool


class TrainingContextRow(BaseModel):
    bucket: str
    moves: int
    errors: int
    rate_per_100: float


class TrainingInsight(BaseModel):
    headline: str
    detail: str


class TrainingDiagnosis(BaseModel):
    moves_analyzed: int
    error_count: int
    blunder_count: int
    rate_per_100: float
    process_tags: list[TrainingProcessTag]
    top_weaknesses: list[TrainingWeakness]
    domains: list[TrainingDomainCount]
    motifs: list[TrainingMotif]
    context: dict[str, list[TrainingContextRow]]
    insights: list[TrainingInsight]


class TrainingOpeningPlayed(BaseModel):
    slot: str
    slot_label: str
    choice: str
    name: str
    eco: str | None = None
    moves: str
    games: int
    score: float
    avg_eval_at_15: int | None = None
    first_error_move: int | None = None
    verdict: Literal["fix_first", "middlegame", "keep", "consolidate", "ignore"]


class TrainingOpeningRecommendation(BaseModel):
    slot: str
    slot_label: str
    name: str
    line: str
    learn_depth: str
    why: str
    plans: str | None = None
    trap: str | None = None
    your_games: int
    your_score: float | None = None
    replaces: list[str]


class TrainingRepertoire(BaseModel):
    mode: Literal["simple", "theory"]
    reasons: list[str]
    played: list[TrainingOpeningPlayed]
    recommended: list[TrainingOpeningRecommendation]


class TrainingBlock(BaseModel):
    kind: str
    label: str
    minutes: int
    text: str


class TrainingDay(BaseModel):
    day: str
    focus: str
    session: str
    weakness: str | None = None
    blocks: list[TrainingBlock]
    minutes: int


class TrainingRoutine(BaseModel):
    base_minutes: int
    days: list[TrainingDay]
    puzzle_split: JsonObject
    rules: list[str]


class TrainingCard(BaseModel):
    card_id: str
    game_url: str | None = None
    game_end_time: int | None = None
    opponent: str | None = None
    player_color: Literal["white", "black"]
    move_number: int
    ply: int
    fen_before: str
    played_san: str
    played_uci: str
    best_san: str | None = None
    best_uci: str | None = None
    refutation_san: list[str]
    wp_loss: float | None = None
    severity: str
    process: str
    domain: str
    motifs: list[str]
    clock_fraction: float | None = None
    eval_before_cp: int | None = None
    due_on: str
    interval_days: int
    streak: int
    reviews: int
    retired: bool
    label: str | None = None
    note: str | None = None


class TrainingPlanMetadata(BaseModel):
    username: str
    games_analyzed: int
    moves_analyzed: int
    rating: int | None = None
    time_classes: dict[str, int]
    score: float
    created_on: str
    reevaluate_on: str
    games_removed: int = 0
    engine_depth: int | None = None
    requested_games: int | None = None
    requested_time_classes: list[str] | None = None


class TrainingPlanResponse(BaseModel):
    id: str
    username: str
    request_params: JsonObject
    created_at: str
    updated_at: str
    metadata: TrainingPlanMetadata
    diagnosis: TrainingDiagnosis
    repertoire: TrainingRepertoire
    routine: TrainingRoutine
    cards: list[TrainingCard]


class TrainingCardReviewRequest(BaseModel):
    grade: Literal["again", "hard", "good"]
    label: str | None = Field(default=None, max_length=40)
    note: str | None = Field(default=None, max_length=500)


class OpeningDrillRequest(BaseModel):
    line: str = Field(min_length=2, max_length=400)
    side: Literal["white", "black"]


class OpeningDrillChoice(BaseModel):
    ply: int
    san: str
    share: float | None = None
    main_line: bool
    alternatives: list[JsonObject]


class OpeningDrillLine(BaseModel):
    id: str
    probability: float
    main_line: bool
    moves: list[str]
    user_color: Literal["white", "black"]
    eco: str | None = None
    variation: str | None = None
    deviates_at: int | None = None
    opponent_choices: list[OpeningDrillChoice]


class OpeningDrillCatalog(BaseModel):
    lines: list[OpeningDrillLine]


class RepertoirePositionRequest(BaseModel):
    color: Literal["white", "black"]
    prefix_uci: list[str] = Field(default_factory=list, max_length=60, alias="prefixUci")
    cp_tolerance: int | None = Field(default=None, ge=0, le=300, alias="cpTolerance")
    min_eval_cp: int | None = Field(default=None, ge=-500, le=200, alias="minEvalCp")

    model_config = {"populate_by_name": True}


class RepertoireMove(BaseModel):
    uci: str
    san: str
    games: int
    share: float
    cp: int | None = None
    mate: int | None = None
    cpLoss: int | None = None
    engineRank: int | None = None
    playable: bool | None = None
    openingEco: str | None = None
    openingName: str | None = None
    inCatalog: bool


class RepertoireOpening(BaseModel):
    eco: str | None = None
    name: str
    ply: int
    exact: bool


class RepertoirePopularity(BaseModel):
    source: Literal["snapshot", "live", "none"]
    status: Literal["ready", "pending", "unavailable"]
    totalGames: int
    fetchedAt: str | None = None
    outOfBook: bool


class RepertoireEngine(BaseModel):
    status: Literal["ready", "pending", "unavailable", "skipped"]
    depth: int
    bestMove: str | None = None
    evalCp: int | None = None


class RepertoireSettings(BaseModel):
    cpTolerance: int
    minEvalCp: int


class RepertoirePositionResponse(BaseModel):
    status: Literal["ready", "pending"]
    retryAfter: float | None = None
    messages: list[str]
    color: Literal["white", "black"]
    prefixUci: list[str]
    fen: str
    epd: str
    ply: int
    sideToMove: Literal["white", "black"]
    ownTurn: bool
    opening: RepertoireOpening | None = None
    inCatalog: bool
    labPrefixUci: list[str] | None = None
    popularity: RepertoirePopularity
    engine: RepertoireEngine
    moves: list[RepertoireMove]
    settings: RepertoireSettings


class RepertoireChoice(BaseModel):
    uci: str
    san: str
    prefixUci: list[str]
    cp: int | None = None
    cpLoss: int | None = None
    depth: int | None = None
    source: Literal["user", "seed"]
    chosenAt: str


class RepertoireUserSettings(BaseModel):
    cpTolerance: int = Field(ge=0, le=300)
    minEvalCp: int = Field(ge=-500, le=200)
    minReach: float = Field(ge=0.005, le=0.5)
    maxOwnMoves: int = Field(ge=1, le=30)


class RepertoireSettingsPatch(BaseModel):
    cpTolerance: int | None = Field(default=None, ge=0, le=300)
    minEvalCp: int | None = Field(default=None, ge=-500, le=200)
    minReach: float | None = Field(default=None, ge=0.005, le=0.5)
    maxOwnMoves: int | None = Field(default=None, ge=1, le=30)


class RepertoireResponse(BaseModel):
    color: Literal["white", "black"]
    # Keyed by position (EPD).
    choices: dict[str, RepertoireChoice]
    settings: RepertoireUserSettings
    updatedAt: str | None = None


class RepertoireChoiceRequest(BaseModel):
    prefix_uci: list[str] = Field(default_factory=list, max_length=60, alias="prefixUci")
    move_uci: str = Field(min_length=4, max_length=5, alias="moveUci")

    model_config = {"populate_by_name": True}


class RepertoireSeedRequest(BaseModel):
    # SAN lines such as "1.e4 e5 2.Nf3 Nc6"; omitted = the training plan's simple repertoire.
    lines: list[str] | None = Field(default=None, max_length=10)


class RepertoireLinesRequest(BaseModel):
    start_prefix_uci: list[str] = Field(default_factory=list, max_length=60, alias="startPrefixUci")
    fetch_budget: int = Field(default=3, ge=0, le=10, alias="fetchBudget")

    model_config = {"populate_by_name": True}


class RepertoireLine(BaseModel):
    id: str
    prefixUci: list[str]
    san: list[str]
    reach: float
    status: Literal["complete", "out_of_book", "needs_choice", "pending", "no_data"]
    endReason: Literal["move_cap", "no_common_reply", "game_over", "depth_limit"] | None = None
    ownMoves: int
    epd: str
    openingEco: str | None = None
    openingName: str | None = None


class RepertoireCoverage(BaseModel):
    complete: float
    outOfBook: float
    needsChoice: float
    pending: float
    noData: float
    pruned: float


class RepertoireLineSettings(BaseModel):
    minReach: float
    maxOwnMoves: int


class RepertoireLinesResponse(BaseModel):
    color: Literal["white", "black"]
    startPrefixUci: list[str]
    lines: list[RepertoireLine]
    coverage: RepertoireCoverage
    status: Literal["ready", "pending"]
    retryAfter: float | None = None
    choicesUsed: int
    truncated: bool
    settings: RepertoireLineSettings
