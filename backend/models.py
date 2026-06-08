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

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        username = value.strip()
        if not username:
            raise ValueError("username is required")
        return username


class MetricPoint(BaseModel):
    key: str
    label: str
    value: float | None
    direction: Literal["higher", "lower"] = "higher"


class OpeningCount(BaseModel):
    name: str
    count: int
    color: Literal["white", "black"]


class OpeningFeatureSet(BaseModel):
    opening_name: str
    color: Literal["white", "black"]
    count: int
    family_name: str | None
    features: list[MetricPoint]


class OpeningMatch(BaseModel):
    opening_name: str
    similarity_score: float | None
    eco_values: str | None
    line_count: int | None
    representative_pgn: str | None
    representative_uci: str | None
    fen: str | None
    used_features: list[str]


class ReportCharts(BaseModel):
    skill_profile: list[MetricPoint]
    favourite_openings: list[OpeningCount]
    top_opening_features: list[OpeningFeatureSet]
    opening_characteristics: list[MetricPoint]
    top_opening_matches: list[OpeningMatch]
    opening_components: list[MetricPoint]
    time_management_indicators: list[MetricPoint]
    advantage_capitalization_components: list[MetricPoint]
    resourcefulness_components: list[MetricPoint]
    game_analysis_components: list[MetricPoint]
    average_time_by_complexity: list[MetricPoint]


class ReportPayload(BaseModel):
    metadata: JsonObject
    statistics_bundle: JsonObject
    charts: ReportCharts


class ReportBuildResponse(BaseModel):
    cache_hash: str
    cache_hit: bool
    normalized_hparams: JsonObject
    report: ReportPayload
