# Report Mistakes Analysis Implementation Guide

This document describes the mistakes analysis embedded in Player Report. There is no standalone batch analyzer page or batch endpoint.

## User Flow

1. The user builds or restores a player report.
2. The report profile renders immediately.
3. The frontend requests the active mistakes result for that report hash.
4. If no active result exists, it automatically analyzes every engine-enriched report game with the report depth and eight punishment plies.
5. The user can add or remove games, change engine settings, and rerun only the mistakes chapter.
6. A mistake detail URL loads its row directly from the report analysis cache.

Extra games affect only mistakes analysis. They never alter profile scores, opening frequencies, or any other report statistics.

## Backend APIs

Routes are defined in `backend/main.py`.

- `POST /api/report/{cache_hash}/mistakes`
  - Request: `ReportMistakesSelectionRequest`
  - Response: `ReportMistakesResponse`
  - Builds or restores an immutable aggregate for the selected games and settings.
- `GET /api/report/{cache_hash}/mistakes`
  - Restores the latest active selection and aggregate.
- `POST /api/report/{cache_hash}/mistakes/games/query`
  - Request: `ReportGamesCatalogRequest`
  - Response: `ReportGamesCatalogResponse`
  - Searches up to 500 games with independent time, rated, result, and date filters.
- `GET /api/report/{cache_hash}/mistakes/{analysis_hash}/{mistake_id}`
  - Response: `ReportMistakeDetailResponse`
  - Loads one stable mistake row without browser storage.
- `POST /api/mistakes/position`
  - Keeps lazy Stockfish exploration for a FEN on the detail page.

`POST /api/mistakes/analyze` was removed. Batch game retrieval and enrichment must not be reintroduced outside the report-scoped service.

## Report Analysis Sidecar

Implemented in `backend/services/report_analysis_service.py` and stored at:

```text
.cache/report_analysis/<report_hash>/
```

The sidecar contains:

```text
manifest.json
active.json
raw/<game-key>.json
enriched/depth-<depth>/<game-key>.json
per_game/<analyzer-version>/depth-<depth>-plies-<plies>/<game-key>.json
catalogs/<filter-hash>.json
analyses/<analysis-hash>.json
```

All JSON writes use temporary files followed by atomic replacement. Operations are protected by a process-local reentrant lock per report hash.

`manifest.json` records the username, report filters, report engine depth, whether Stockfish enrichment succeeded, default report game IDs, aliases, and game summaries. Raw and enriched payloads are stored individually so additions and depth changes can do incremental work.

`active.json` points to the last completed aggregate and stores the selection, settings, and picker filters. Aggregate files are immutable and addressed by a hash of:

- analyzer version
- sorted selected game IDs
- engine depth
- maximum punishment plies

## Report Build Integration

`backend.services.statistics_service.build_report` fetches and enriches games once. After profile statistics are built, it calls `initialize_report_analysis` with the exact raw and enriched games used by that report.

`ReportPayload.analysis_context` contains:

- report game summaries
- default game IDs
- report engine depth
- `engine_enriched`
- sidecar generation ID used to invalidate frontend drafts after refresh

The initial mistakes request reads those depth-specific enrichment artifacts. It does not call Chess.com and does not run `GameEnrichmentTransformer` again. Stockfish is opened only for punishment-line analysis.

A refresh (`refresh_cache=true`) replaces the report sidecar after the new report build succeeds. Reports created before sidecars existed, and reports whose Stockfish enrichment failed, remain readable but require a rebuild with `use_engine=true` and `refresh_cache=true` before mistakes analysis can run.

## Incremental Rules

- Same selection and settings: return the immutable aggregate cache hit.
- Remove games: combine cached per-game results into a new aggregate; do not open Stockfish.
- Add catalog games: enrich and analyze only additions without cached artifacts.
- Change punishment plies: reuse enrichment and rerun per-game punishment analysis.
- Change engine depth: enrich selected games at the new depth, then analyze them.
- Reopen a report: restore `active.json` and its aggregate.

The report catalog caches raw query results by retrieval filters. Result filtering is applied to cached summaries, and matching raw games are registered in the manifest for later selection.

## Stable Mistake IDs

Each response row has `mistake_id`, derived from game identity, ply, and played move. It is stable across aggregate order and supports direct detail lookup. Do not derive detail identity from the row index.

## Core Analyzer

`utils/mistakes_analyzer.py` remains responsible for chess analysis:

- candidate detection from CP and win-probability loss
- inaccuracy, mistake, and blunder severity
- theoretical punishment continuation
- actual punishment comparison
- stability detection
- tactic tagging
- summary counts

`analyze_mistakes` can analyze one enriched game at a time. The report service uses that property for per-game caching, then aggregates summaries and sorts all rows by win-probability loss and CP loss.

## Frontend

The integrated UI is `frontend/app/components/report/mistakes-report-section.tsx`. It appears after Player Profile and before Opening Repertoire.

It provides:

- automatic active-result restore and first analysis
- summary and tactic-theme chart
- simple and advanced row modes
- sorting, grouping, and theme filtering
- engine depth and punishment controls
- expandable game editor with selected count
- independent time, rated, result, and date filters
- pagination capped at 500 games
- explicit rerun and stale-result state

Completed results and active settings are restored from the backend. Uncommitted picker and settings edits are stored in `localStorage` under the report hash so stale edits survive reopening.

Comparison mode enables automatic mistakes analysis only for the primary report. `CompareReportView` passes `enableMistakes={false}` to the secondary report.

## Detail Route

The detail route is:

```text
/report/:username/mistake/:mistakeId?cacheHash=...&analysisHash=...
```

Implemented in `frontend/app/routes/report.$username.mistake.$mistakeId.tsx`, it:

- fetches the mistake from the report-scoped backend endpoint
- renders engine and actual punishment tracks
- lazily calls `/api/mistakes/position` for branch exploration
- returns to `/report/:username?restore=<cache_hash>#mistakes`

It does not use `sessionStorage`.

## Tests And Commands

Backend service tests cover shared initial artifacts, removal without engine work, incremental additions, depth and punishment invalidation, active restore, catalog filtering, invalid IDs, and fallback reports.

```bash
conda run -n chess env PYTHONPATH=. pytest -q tests/test_backend_services.py test_mistakes_analyzer.py
cd frontend && npm run typecheck
cd frontend && npm run build
```

When changing this flow, keep `backend/models.py`, `frontend/app/lib/types.ts`, and `frontend/app/lib/api.ts` synchronized. Never make the integrated chapter retrieve report games through `/api/games/query`.
