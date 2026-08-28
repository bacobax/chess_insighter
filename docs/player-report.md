# Player Report Implementation Guide

This document describes the current player report backend and frontend implementation and the files to update when changing it.

## Purpose

The player report builds a cached, player-focused analysis from recent Chess.com games. It combines global skill statistics, player style vectors, learning priorities from mistakes, opening repertoire preferences, and report visualizations.

It has eight related flows:

1. Build or refresh a full report: `POST /api/report/build`.
2. Restore a cached report: `GET /api/report/cache/{cache_hash}`.
3. Save a built report in the saved reports index: `POST /api/reports/saved`.
4. List/delete saved reports: `GET /api/reports/saved` and `DELETE /api/reports/saved/{cache_hash}`.
5. Build report-scoped mistakes: `POST /api/report/{cache_hash}/mistakes`.
6. Restore active mistakes: `GET /api/report/{cache_hash}/mistakes`.
7. Browse additional report-scoped games: `POST /api/report/{cache_hash}/mistakes/games/query`.
8. Load a direct mistake detail: `GET /api/report/{cache_hash}/mistakes/{analysis_hash}/{mistake_id}`.

The profile can run with Stockfish-backed enrichment or heuristic fallback enrichment. The integrated mistakes chapter requires an engine-enriched report and otherwise offers a rebuild action.

## Backend Entry Points

### API Routes

Defined in `backend/main.py`.

- `POST /api/report/build`
  - Request model: `ReportBuildRequest`
  - Response model: `ReportBuildResponse`
  - Service: `backend.services.statistics_service.build_report`
- `GET /api/report/cache/{cache_hash}`
  - Response model: `ReportBuildResponse`
  - Service: `backend.services.cache_service.ReportCache`
- `GET /api/reports/saved`
  - Response model: `SavedReportsList`
  - Service: `backend.services.saved_reports_service.SavedReportsIndex`
- `POST /api/reports/saved`
  - Request model: `SaveReportRequest`
  - Service: `backend.services.saved_reports_service.save_report_entry`
- `DELETE /api/reports/saved/{cache_hash}`
  - Service: `backend.services.saved_reports_service.SavedReportsIndex.delete`
- report-scoped mistakes routes
  - Service: `backend.services.report_analysis_service`
  - Full API and cache details: `docs/mistakes-analyzer.md`

The build handler runs synchronously inside `run_in_threadpool`.

### Request/Response Models

Defined in `backend/models.py`.

`ReportBuildRequest` contains:

- `username`
- `hparams`
- `max_games`
- `engine_depth`
- `use_engine`
- `refresh_cache`
- `target_color`
- inherited game filters: `time_classes`, `rated_filter`, `since_year`, `since_month`, `until_year`, `until_month`

`ReportBuildResponse` contains:

- `cache_hash`
- `cache_hit`
- `normalized_hparams`
- `report`

`ReportPayload` contains:

- `metadata`
- `statistics_bundle`
- `charts`
- optional `analysis_context` with exact report game summaries, default IDs, report depth, and engine availability

`ReportCharts` contains:

- `skill_profile`
- `favourite_openings`
- `opening_characteristics`
- `opening_report_groups`
- `opening_components`
- `time_management_indicators`
- `advantage_capitalization_components`
- `resourcefulness_components`
- `game_analysis_components`
- `average_time_by_complexity`

Saved report models:

- `SavedReportEntry`
- `SavedReportsList`
- `SaveReportRequest`

Frontend TypeScript types in `frontend/app/lib/types.ts` mirror these Pydantic models and are the practical UI contract. Keep backend model changes synchronized with TypeScript.

## Backend Service Flow

Implemented in `backend/services/statistics_service.py`.

### Full Report Build

`build_report(request)`:

1. Loads default hparams from `settings.hparams_path`.
2. Merges default hparams with `request.hparams` via `deep_merge`.
3. Validates numeric hparams with `validate_numeric_hparams`.
4. Builds a deterministic cache key with:
   - normalized username
   - effective hparams
   - game filters
   - `max_games`
   - `engine_depth`
   - `use_engine`
   - dataset identity for openings and opening vectors
   - report feature model version
5. Hashes the key with `stable_hash`.
6. Returns a cached `ReportBuildResponse` if `refresh_cache` is false and the cache exists.
7. Writes the effective hparams to `.cache/report_configs/<hash>.yaml`.
8. Fetches raw Chess.com games through `fetch_latest_games_for_report`.
9. Enriches games through `backend.services.enrichment_service.enrich_games`.
10. Builds a `PlayerStatisticsBundle` through `utils.player_statistics.PlayerStatisticsBuilder`.
11. Serializes the bundle with `backend.services.openings_service.serializable`.
12. Builds opening charts with `build_opening_charts`.
13. Builds the report chart lists from global statistics.
14. Initializes `.cache/report_analysis/<hash>/` with the exact raw and enriched report games.
15. Writes the full response to `.cache/reports/<hash>.json`.
16. Writes the matcher-ready player vector to `.cache/player_vectors.json`.
17. Returns the response.

`target_color` is currently part of the request model but is not included in the report cache key. Color-specific opening sections are all produced in one report.

### Hparams

Default hparams live in `config/global_statistics_hparams.yaml`.

Important backend files:

- `backend/services/hparams_service.py`
  - `load_hparams`
  - `dump_simple_yaml`
  - `validate_numeric_hparams`
- `config/README.md`
  - documents the meaning of the hparams values

When a report is built, the merged hparams are persisted to `.cache/report_configs/<hash>.yaml`. `PlayerStatisticsBuilder` receives this generated file so all downstream transformers use the exact same effective configuration as the response.

### Enrichment

Implemented in `backend/services/enrichment_service.py`.

`enrich_games(raw_games, engine_depth, use_engine)`:

1. Creates an `OpeningRepository` from `settings.openings_path`.
2. Sets metadata fields:
   - `engine_used`
   - `engine_depth`
   - `engine_path`
   - `fallback_reason`
3. If `use_engine` is true and Stockfish is configured, it uses `GameEnrichmentTransformer`.
4. If engine enrichment is disabled, unavailable, or raises, it falls back to `heuristic_enrich_game_data`.

The report expects enriched games to expose move-level facts such as phase, opening data, evals, win-probability loss, clock data, complexity, tactics, quiet-position flags, and castling flags.

## Core Statistics Flow

Implemented in `utils/player_statistics.py`.

`PlayerStatisticsBuilder.build(enriched_games, player_name)` creates a `PlayerStatisticsBundle`:

- `global_statistics`
- `player_samples`
- `castling_summaries`
- `player_profile`
- `matcher_ready_player_vector`
- `player_profiles_by_color`
- `matcher_ready_player_vectors`

The builder composes three transformers:

- `GlobalStatisticsTransformer`
- `PlayerSampleBuilder`
- `PlayerFeatureAggregator`

### Global Statistics

Implemented in `utils/global_statistics_transformer.py`.

`GlobalStatisticsTransformer.compute(games, username)`:

1. Resolves target games and target moves for the username.
2. Computes complexity percentiles used by several metric sections.
3. Builds skill and section dataclasses:
   - `tactics_score`
   - `calculation_score`
   - `openings_score`
   - `middlegame_strategy_score`
   - `endgame_score`
   - `time_management_score`
   - `game_analysis_score`
   - `advantage_capitalization_score`
   - `resourcefulness_score`
4. Normalizes loss-based scores to `0..1`.
5. Returns `None` for metrics that do not have enough qualifying samples.

The chart helper functions in `statistics_service.py` convert these dataclasses into `MetricPoint` lists for the frontend.

### Player Profile

Implemented in `utils/player_feature_transformer.py`.

`PlayerSampleBuilder.build(games, player_name)`:

- Produces one `PlayerMoveSample` per target-player move.
- Produces one `GameCastlingSummary` per target-player game.
- Orients centipawn values to the player.
- Carries opening, result, loss, complexity, tactical, and descriptor data into sample form.

`PlayerFeatureAggregator.aggregate(samples, castling_summaries, player_name)`:

- Computes style vector fields.
- Computes skill vector fields.
- Computes subfeatures such as opening distributions, structure distribution, skill sample counts, skill scores, and matcher vector.
- Estimates confidence per profile dimension.
- Returns a `PlayerProfile`.

`PlayerStatisticsBuilder` also aggregates separate white, black, and combined profiles. The report uses their vectors for color-aware opening tendencies.

### Matcher-Ready Player Vector

Implemented in `utils/player_feature_transformer.player_opening_vector`.

The player profile style fields are mapped to opening-vector fields with `PLAYER_TO_OPENING_MAP_V2`:

- `tactical_density`
- `quiet_position_density`
- `king_safety_risk`
- `early_castling_tendency`
- `opposite_side_castling_tendency`
- `middlegame_complexity`
- `pawn_structure_sharpness`
- `material_imbalance`
- `endgame_likelihood_proxy`

This vector is stored in the report bundle and written to `.cache/player_vectors.json`. Opening study prefers a report `cache_hash` so it can use the vector from the same games and filters as the report.

## Opening Repertoire Data

Implemented in `backend/services/openings_service.py`.

`build_opening_charts(bundle)` returns:

- `favourite_openings`
- `opening_characteristics`
- `opening_report_groups`

`opening_report_groups` contains `white`, `black`, and `both` entries. Each entry contains only `opening_characteristics`. Recommendations and per-opening top-feature data are intentionally excluded from the report payload.

The backend still exposes `POST /api/openings/matches` as standalone compatibility tooling, but the player report does not call it or render its results.

## Caching And Persistence

Implemented in `backend/services/cache_service.py` and `backend/services/saved_reports_service.py`.

### Report Cache

`ReportCache` stores full report JSON at:

```text
.cache/reports/<cache_hash>.json
```

The cache hash is based on the deterministic report cache key. Dataset identity includes file size and mtime for the opening datasets, so changing those datasets invalidates report caches.

### Report Config Snapshots

Merged hparams are stored at:

```text
.cache/report_configs/<cache_hash>.yaml
```

These snapshots make a report's metric configuration inspectable and reproducible.

### Player Vector Cache

`update_player_vector_cache` writes a `CachedPlayerVector` to:

```text
.cache/player_vectors.json
```

The entry includes:

- vector
- feature order
- metadata
- confidence
- cache key
- creation timestamp

### Saved Reports

Saved reports are an index of cache hashes, not a second copy of the report payload. The backend rejects saving a report if the referenced report cache entry does not exist.

### Report Analysis Sidecar

Reusable raw games, depth-specific enriched moves, per-game mistakes, aggregate analyses, catalog results, and the active mistakes pointer live under `.cache/report_analysis/<cache_hash>/`. Refreshing a report replaces this sidecar, preventing newly fetched report games from being mixed with stale artifacts. See `docs/mistakes-analyzer.md` for layout and invalidation rules.

## Frontend Flow

### API Client

Defined in `frontend/app/lib/api.ts`.

- `getDefaultHparams()` calls `/api/config/default-hparams`.
- `buildReport(request)` calls `/api/report/build`.
- `getReportByHash(cacheHash)` calls `/api/report/cache/{cacheHash}`.
- `saveReport(request)` calls `/api/reports/saved`.
- `getSavedReports()` calls `/api/reports/saved`.
- `deleteSavedReport(cacheHash)` calls `/api/reports/saved/{cacheHash}`.
- `getActiveReportMistakes(cacheHash)` restores the active mistakes result.
- `analyzeReportMistakes(cacheHash, request)` builds a report-scoped selection.
- `queryReportMistakeGames(cacheHash, request)` browses independently filtered games.
- `getReportMistakeDetail(...)` loads direct mistake details.

Types are defined in `frontend/app/lib/types.ts`.

Important report types:

- `Hparams`
- `MetricPoint`
- `OpeningCount`
- `OpeningReportGroup`
- `ReportCharts`
- `ReportPayload`
- `ReportBuildRequest`
- `ReportBuildResponse`
- `SavedReportEntry`
- `SavedReportsList`
- `SaveReportRequest`

### Report Route

Defined in `frontend/app/routes/report.$username.tsx`.

Responsibilities:

- Reads `username` from route params.
- Reads optional `restore` cache hash from query params.
- Reads optional `rebuildParams` from navigation state.
- Fetches default hparams.
- If restoring, fetches the cached report with `getReportByHash`.
- Shows loading/error states.
- Renders `CompareReportView` once hparams and optional restored report are ready.

### Compare View

Defined in `frontend/app/components/report/compare-report-view.tsx`.

Responsibilities:

- Lets the user edit the primary username.
- Optionally enables a side-by-side second-player report.
- Passes restored report and rebuild params only to the primary report.
- Renders one or two `PlayerReport` instances.
- Enables mistakes analysis only for the primary player.

### Player Report Component

Defined in `frontend/app/components/report/player-report.tsx`.

Responsibilities:

- Holds report form state:
  - `hparams`
  - `maxGames`
  - `timeClass`
  - `ratedFilter`
  - `sinceYear`
  - `sinceMonth`
  - `engineDepth`
  - `useEngine`
  - `refreshCache`
- Shows advanced hparams via `ReportConfigForm`.
- Builds a `ReportBuildRequest` and calls `buildReport`.
- Stores the response in component state.
- Updates local hparams from `response.normalized_hparams`.
- Renders `ReportDashboard` when a report exists.

`ReportDashboard`:

- Shows cache hit/miss and short hash.
- Saves the report through `saveReport`.
- Renders `SkillProfileSection`, which pairs the radar with a readable score list.
- Groups opening, time management, advantage conversion, resourcefulness, and game-analysis component charts under score-evidence tabs linked to the parent skill scores.
- Renders `MistakesReportSection` after Player Profile and before Opening Repertoire.
- Renders `OpeningRepertoireSection`, which keeps frequency and position-tendency concepts together while separating them visually.
- Links to `/opening-study` with `username` and `cacheHash` from the opening repertoire section.

`OpeningRepertoireSection`:

- Shows the most-played opening chart.
- Separates position tendencies into White, Black, and Overall tabs.
- Groups tendency metrics into position character, king safety, and structure/outcome concepts.
- Does not render opening matches or per-opening top-feature panels.

`MistakesReportSection`:

- Restores or automatically starts the report-scoped mistakes analysis.
- Starts with all exact games used by the report.
- Keeps the profile readable while the separate request runs.
- Provides an independent game editor and engine controls.
- Marks the displayed aggregate stale while draft selection or settings differ.
- Persists drafts by report hash and completed state in the backend sidecar.
- Links to the report-scoped direct detail route.

### Report Config Form

Defined in `frontend/app/components/report/report-config-form.tsx`.

Responsibilities:

- Recursively renders nested hparams.
- Uses number inputs for numeric values.
- Uses checkboxes for booleans.
- Uses text inputs for other primitive values.
- Applies updates immutably with `updateAtPath`.

The form is generic, so backend hparam shape changes usually do not require frontend layout changes unless the UI needs special handling.

### Report Charts

Defined in `frontend/app/components/charts/report-charts.tsx`.

Current chart components:

- `SkillRadarChart`
- `FavouriteOpeningsChart`
- `MetricBarChart`

These components expect normalized `0..1` metric values for percent charts. `MetricBarChart` can disable percent formatting for raw values such as average time by complexity.

### Saved Reports

Defined in `frontend/app/components/saved-reports-list.tsx`.

Responsibilities:

- Loads saved report entries on mount.
- Groups entries by username.
- Opens a saved report by navigating to `/report/:username?restore=<cache_hash>`.
- Rebuilds a saved report by navigating to `/report/:username` with `rebuildParams` in route state.
- Deletes saved report entries with `deleteSavedReport`.

## Change Checklist

Use this checklist when modifying the player report:

1. If request or response shape changes, update:
   - `backend/models.py`
   - `frontend/app/lib/types.ts`
   - `frontend/app/lib/api.ts` if endpoint behavior changes
2. If build orchestration changes, update:
   - `backend/services/statistics_service.py`
   - `backend/services/cache_service.py` if cache identity or persistence changes
3. If game enrichment requirements change, update:
   - `backend/services/enrichment_service.py`
   - `utils/game_enrichment_transformer.py`
   - heuristic fallback in `utils/player_vector_cache.py` if fallback reports still need the field
4. If global score logic changes, update:
   - `utils/global_statistics_transformer.py`
   - `config/global_statistics_hparams.yaml`
   - `config/README.md`
5. If player style/profile logic changes, update:
   - `utils/player_feature_transformer.py`
   - `utils/player_statistics.py` if bundle shape changes
6. If opening repertoire data or report sections change, update:
   - `backend/services/openings_service.py`
   - `frontend/app/components/report/player-report.tsx`
   - `frontend/app/lib/types.ts`
7. If saved report behavior changes, update:
   - `backend/services/saved_reports_service.py`
   - `frontend/app/components/saved-reports-list.tsx`
8. If frontend report presentation changes, update:
   - `frontend/app/routes/report.$username.tsx`
   - `frontend/app/components/report/compare-report-view.tsx`
   - `frontend/app/components/report/player-report.tsx`
   - `frontend/app/components/report/report-config-form.tsx`
   - `frontend/app/components/charts/report-charts.tsx`
9. Update or add tests in:
   - `tests/test_backend_services.py`
   - `test_global_statistics_transformer.py`
   - `test_player_feature_transformer.py`
   - `test_game_enrichment_transformer.py`
   - opening service tests in `tests/test_backend_services.py` or dedicated opening tests
10. Run targeted tests before broader validation.

## Common Pitfalls

- Report caches depend on hparams, filters, max games, engine depth, engine usage, feature model version, and dataset identity. If a new behavior affects report output, it may need to be part of `report_cache_key`.
- `target_color` is not part of the report cache key. The report currently builds all color groups in one response.
- Stockfish is optional for player reports. If a metric assumes engine-backed fields, preserve or update the heuristic fallback path.
- CP values may be White-oriented in enriched moves. Use player-oriented values for player-facing profile and skill calculations.
- The frontend report types are stricter than some backend JSON payload internals. Keep `ReportCharts` and saved report types synchronized manually.
- Saved reports reference cache hashes. Deleting or invalidating cache files can make saved entries impossible to open.
- Increasing `engine_depth` and `max_games` can make `/api/report/build` slow because build work is synchronous from the API route's perspective.
- Hparams are recursively rendered in the frontend. Invalid numeric hparams are rejected by the backend, not constrained by specialized frontend controls.
- Opening study should use a report `cacheHash` when possible so it respects the exact report game filters.

## Useful Commands

Run backend service tests:

```bash
conda run -n chess python -m pytest tests/test_backend_services.py -q
```

Run global statistics tests:

```bash
conda run -n chess python -m pytest test_global_statistics_transformer.py -q
```

Run player feature tests:

```bash
conda run -n chess python -m pytest test_player_feature_transformer.py -q
```

Run game enrichment tests:

```bash
conda run -n chess python -m pytest test_game_enrichment_transformer.py -q
```

Run all tests:

```bash
conda run -n chess python -m pytest -q
```

Run the backend locally:

```bash
conda run -n chess python -m uvicorn backend.main:app --port 8000 --reload
```

Run the frontend locally:

```bash
cd frontend
npm run dev
```
