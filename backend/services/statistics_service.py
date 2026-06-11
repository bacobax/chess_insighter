from __future__ import annotations

from typing import Any

from backend.models import MetricPoint, ReportBuildRequest, ReportBuildResponse, ReportCharts, ReportPayload
from backend.services.cache_service import ReportCache, report_cache_key, stable_hash, update_player_vector_cache
from backend.services.chesscom_service import fetch_latest_games_for_report
from backend.services.enrichment_service import enrich_games
from backend.services.hparams_service import dump_simple_yaml, load_hparams, validate_numeric_hparams
from backend.services.openings_service import build_opening_charts, serializable
from backend.settings import settings
from utils.player_statistics import PlayerStatisticsBuilder


def build_report(request: ReportBuildRequest) -> ReportBuildResponse:
    default_hparams = load_hparams(settings.hparams_path)
    effective_hparams = deep_merge(default_hparams, request.hparams)
    validate_numeric_hparams(effective_hparams)

    filters = {
        "time_classes": request.time_classes,
        "rated_filter": request.rated_filter,
        "since_year": request.since_year,
        "since_month": request.since_month,
        "until_year": request.until_year,
        "until_month": request.until_month,
    }
    key = report_cache_key(
        username=request.username,
        hparams=effective_hparams,
        filters=filters,
        max_games=request.max_games,
        engine_depth=request.engine_depth,
        use_engine=request.use_engine,
    )
    cache_hash = stable_hash(key)
    cache = ReportCache()

    if not request.refresh_cache:
        cached = cache.get(cache_hash)
        if cached is not None:
            cached["cache_hit"] = True
            return ReportBuildResponse.model_validate(cached)

    settings.report_config_dir.mkdir(parents=True, exist_ok=True)
    hparams_path = settings.report_config_dir / f"{cache_hash}.yaml"
    hparams_path.write_text(dump_simple_yaml(effective_hparams), encoding="utf-8")

    raw_games = fetch_latest_games_for_report(
        username=request.username,
        max_games=request.max_games,
        time_classes=request.time_classes,
        rated_filter=request.rated_filter,
        since_year=request.since_year,
        since_month=request.since_month,
        until_year=request.until_year,
        until_month=request.until_month,
    )
    if not raw_games:
        raise ValueError("No games found for the requested username and filters.")

    enriched_games, enrichment_metadata = enrich_games(
        raw_games,
        engine_depth=request.engine_depth,
        use_engine=request.use_engine,
    )
    if not enriched_games:
        raise ValueError("No games could be enriched for the requested username and filters.")

    bundle = PlayerStatisticsBuilder(hparams_path).build(enriched_games, player_name=request.username)
    bundle_json = serializable(bundle)
    stats = bundle.global_statistics
    opening_charts = build_opening_charts(bundle)

    metadata = {
        "username": request.username,
        "games_selected": len(raw_games),
        "games_enriched": len(enriched_games),
        "filters": filters,
        **enrichment_metadata,
    }
    charts = ReportCharts(
        skill_profile=skill_profile(stats),
        favourite_openings=opening_charts["favourite_openings"],
        top_opening_features=opening_charts["top_opening_features"],
        opening_characteristics=opening_charts["opening_characteristics"],
        top_opening_matches=opening_charts["top_opening_matches"],
        opening_report_groups=opening_charts["opening_report_groups"],
        opening_components=opening_components(stats),
        time_management_indicators=time_management_indicators(stats),
        advantage_capitalization_components=advantage_components(stats),
        resourcefulness_components=resourcefulness_components(stats),
        game_analysis_components=game_analysis_components(stats),
        average_time_by_complexity=average_time_by_complexity(stats),
    )
    response = ReportBuildResponse(
        cache_hash=cache_hash,
        cache_hit=False,
        normalized_hparams=effective_hparams,
        report=ReportPayload(
            metadata=metadata,
            statistics_bundle=bundle_json,
            charts=charts,
        ),
    )
    payload = response.model_dump()
    cache.set(cache_hash, payload)
    update_player_vector_cache(
        cache_key=key,
        vector=bundle.matcher_ready_player_vector,
        confidence=bundle.player_profile.confidence,
        metadata={
            **metadata,
            "cache_hash": cache_hash,
            "player_name": bundle.player_profile.player_name,
            "games_analyzed": bundle.player_profile.games_analyzed,
            "moves_analyzed": bundle.player_profile.moves_analyzed,
        },
    )
    return response


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key, value in base.items():
        if isinstance(value, dict):
            merged[key] = deep_merge(value, override.get(key, {}) if isinstance(override.get(key), dict) else {})
        else:
            merged[key] = override.get(key, value)
    for key, value in override.items():
        if key not in merged:
            merged[key] = value
    return merged


def point(key: str, label: str, value: float | None, direction: str = "higher") -> MetricPoint:
    return MetricPoint(key=key, label=label, value=value, direction=direction)


def score(section: Any) -> float | None:
    return None if section is None else section.score


def skill_profile(stats: Any) -> list[MetricPoint]:
    return [
        point("middlegame_strategy", "Middlegame Strategy", score(stats.middlegame_strategy_score)),
        point("openings", "Openings", score(stats.openings_score)),
        point("calculation", "Calculation", score(stats.calculation_score)),
        point("tactics", "Tactics", score(stats.tactics_score)),
        point("resourcefulness", "Resourcefulness", score(stats.resourcefulness_score)),
        point("advantage_capitalization", "Advantage Capitalization", score(stats.advantage_capitalization_score)),
        point("game_analysis", "Game Analysis", score(stats.game_analysis_score)),
        point("time_management", "Time Management", score(stats.time_management_score)),
        point("endgame", "Endgame", score(stats.endgame_score)),
    ]


def opening_components(stats: Any) -> list[MetricPoint]:
    section = stats.openings_score
    return [
        point("book_accuracy", "Book Accuracy", section.book_accuracy),
        point("post_opening_stability", "Post-Opening Stability", section.eval_stability_after_opening),
        point("opening_result", "Opening Result", section.result_from_opening_positions),
    ]


def time_management_indicators(stats: Any) -> list[MetricPoint]:
    section = stats.time_management_score
    return [
        point("time_trouble", "Time Trouble", section.time_trouble_frequency, "lower"),
        point("pressure_blunders", "Pressure Blunders", section.blunder_rate_in_time_pressure, "lower"),
        point("underthinking_critical", "Underthinking Critical", section.critical_position_underthinking_rate, "lower"),
        point("overthinking_simple", "Overthinking Simple", section.overthinking_simple_positions_rate, "lower"),
    ]


def advantage_components(stats: Any) -> list[MetricPoint]:
    section = stats.advantage_capitalization_score
    return [
        point("conversion_plus_2", "Conversion +2", section.conversion_rate_from_plus_2),
        point("conversion_plus_5", "Conversion +5", section.conversion_rate_from_plus_5),
        point("eval_preservation", "Eval Preservation", section.eval_preservation_when_ahead),
        point("low_blunder_rate", "Low Blunder Rate", section.low_blunder_rate_when_ahead),
    ]


def resourcefulness_components(stats: Any) -> list[MetricPoint]:
    section = stats.resourcefulness_score
    return [
        point("save_rate_minus_2", "Save Rate -2", section.save_rate_from_minus_2),
        point("draw_win_from_lost", "Draw/Win From Lost", section.draw_or_win_rate_from_lost_positions),
        point("eval_recovery", "Eval Recovery", section.eval_recovery_rate),
        point("low_collapse_rate", "Low Collapse Rate", section.low_collapse_rate_when_worse),
    ]


def game_analysis_components(stats: Any) -> list[MetricPoint]:
    section = stats.game_analysis_score
    return [
        point("improvement_rate", "Improvement Rate", section.weakness_improvement_rate),
        point("mistake_repetition", "Mistake Repetition", section.mistake_repetition_rate, "lower"),
        point("post_loss_improvement", "Post-Loss Improvement", section.post_loss_improvement),
    ]


def average_time_by_complexity(stats: Any) -> list[MetricPoint]:
    values = stats.time_management_score.average_time_spent_by_complexity
    return [
        point(key, key.replace("_", " ").title(), values.get(key))
        for key in ["simple", "normal", "complex", "high_complexity"]
    ]
