# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Python Environment

All Python work runs under the `chess` conda environment — it is the only environment that has `python-chess`, `fastapi`, `uvicorn`, and the other dependencies:

```bash
conda activate chess
# or use the full path:
/Users/francescobassignana/miniforge3/envs/chess/bin/python
```

## Common Commands

### Backend

```bash
# Run dev server (reload on change)
conda run -n chess python -m uvicorn backend.main:app --port 8000 --reload

# Run all tests
conda run -n chess python -m pytest -q

# Run a single test file
conda run -n chess python -m pytest test_opening_study_tree.py -q

# Rebuild opening feature vectors (requires Stockfish; regenerates openings_dataset/opening_feature_vectors.csv)
conda run -n chess python build_opening_feature_vectors.py
```

### Frontend (inside `chess_insighter/`)

```bash
cd chess_insighter
npm run dev        # dev server on :5173
npm run build      # production build
npm run typecheck  # react-router typegen + tsc
```

## Architecture

The repo is split into a Python backend and a React frontend; they communicate over a local HTTP API. A separate ML training pipeline (`train_encoder.py`, `run_sweep.py`, `utils/position_style_encoder.py`) operates independently of both.

### Backend (`backend/`)

FastAPI app serving endpoints under `/api/`. The request/response surface is fully defined in Pydantic models (`backend/models.py`). Services live in `backend/services/` and are called from route handlers in `backend/main.py` via `run_in_threadpool` (all computation is CPU-bound and synchronous).

Key conventions:
- Settings (paths, CORS regex, Stockfish path) are in `backend/settings.py` as a frozen `Settings` dataclass, importable everywhere as `settings`.
- Report data is cached to `.cache/reports/<hash>.json`; the hash is a deterministic digest of request parameters.
- Opening feature rows are loaded once and cached in memory with `@lru_cache(maxsize=1)` in `backend/services/openings_service.py`.

#### API endpoints (`backend/main.py`)

| Endpoint | Method | Handler / Service |
|---|---|---|
| `/api/health` | GET | inline |
| `/api/config/default-hparams` | GET | `hparams_service` |
| `/api/games/query` | POST | `chesscom_service.query_games` |
| `/api/report/build` | POST | `statistics_service.build_report` |
| `/api/report/cache/{hash}` | GET | `cache_service.ReportCache` |
| `/api/mistakes/analyze` | POST | `mistakes_service.build_mistakes_analysis` |
| `/api/mistakes/position` | POST | `mistakes_service.analyse_position` |
| `/api/openings/matches` | POST | `openings_service.top_opening_matches` |
| `/api/opening-study-tree/children` | POST | `opening_study_service.opening_study_tree_children` |
| `/api/reports/saved` | GET/POST | `saved_reports_service` |
| `/api/reports/saved/{hash}` | DELETE | `saved_reports_service` |

#### Backend services (`backend/services/`)

**`cache_service.py`** — deterministic caching
- Keywords: `stable_hash`, `report_cache_key`, `ReportCache`, `update_player_vector_cache`, `dataset_identity`
- Caches reports to `.cache/reports/<hash>.json`; player vectors to `.cache/player_vectors.json`

**`chesscom_service.py`** — Chess.com API client
- Keywords: `query_games`, `fetch_latest_games_for_report`, `summarize_game`, `validate_username`, `UnknownChessComUser`, `ChessComServiceError`, `normalize_result`, `pgn_opening`
- Paginates Chess.com monthly archives; raises typed exceptions caught by `main.py` handlers

**`enrichment_service.py`** — per-move Stockfish enrichment
- Keywords: `enrich_games`
- Calls `utils/game_enrichment_transformer.py`; attaches engine eval, phase, castling flags to every move

**`hparams_service.py`** — config loading / validation
- Keywords: `load_hparams`, `validate_numeric_hparams`, `dump_simple_yaml`
- Reads `config/global_statistics_hparams.yaml`; all thresholds and weights live there

**`mistakes_service.py`** — blunder detection pipeline
- Keywords: `build_mistakes_analysis`, `analyse_position`, `_raw_games_for_request`, `_game_identifier`
- Wraps `utils/mistakes_analyzer.py`; handles game fetching, caching, and the per-position deep-dive endpoint

**`opening_study_service.py`** — opening study tree orchestration
- Keywords: `opening_study_tree_children`, `_resolve_player_vector`, `_resolve_opening_vectors_path`
- Resolves the player vector (from cache or request body) then calls `utils/opening_study_tree.get_opening_study_tree_children`

**`openings_service.py`** — opening feature loading + player↔opening matching
- Keywords: `opening_feature_rows`, `top_opening_matches`, `weighted_cosine_similarity`, `unweighted_cosine_similarity`, `weighted_dot_product_similarity`, `structure_distribution_similarity`, `build_opening_charts`, `top_opening_features`, `favourite_openings`, `find_opening_family_row`, `uci_to_fen`
- Loads `openings_dataset/opening_feature_vectors.csv` once via `@lru_cache(maxsize=1)`

**`saved_reports_service.py`** — saved report persistence
- Keywords: `SavedReportsIndex`, `save_report_entry`, `_now_iso`
- Stores a JSON index in `.cache/saved_reports.json`

**`statistics_service.py`** — full report assembly
- Keywords: `build_report`, `skill_profile`, `opening_components`, `time_management_indicators`, `advantage_components`, `resourcefulness_components`, `game_analysis_components`, `average_time_by_complexity`, `deep_merge`
- Orchestrates `enrichment_service` → `global_statistics_transformer` → formats into `ReportBuildResponse`

### Analysis Layer (`utils/`)

All heavy computation lives here, independent of FastAPI.

#### Mistakes / tactic detection

**`mistakes_analyzer.py`** — blunder detection + punishment-line analysis
- Keywords: `analyze_mistakes`, `classify_mistake_severity`, `MistakeAnalysisItem`, `MistakesAnalysis`, `MistakeAnalyzerConfig`, `EngineRootAnalysis`, `ActualPunishment`, `PunishmentLineMove`, `_build_best_line`, `_evaluate_actual_punishment`, `analyse_position_lines`, `_is_candidate_mistake`, `_decision_difficulty`
- Main entry: `analyze_mistakes(games, config, engine)` → `MistakesAnalysis`

**`tactic_detector.py`** — move-level tactic tagging
- Keywords: `detect_tactics`, `TacticTag`, `TacticDetectorConfig`, `_fork_targets`, `_absolute_pins_created_by_moved_piece`, `_skewer_created_by_moved_piece`, `_is_king_attraction`
- Tags: `check`, `double_check`, `discovered_check`, `checkmate_in_k`, `fork`, `absolute_pin`, `skewer`, `king_attraction`

#### Opening analysis

**`opening_feature_transformer.py`** — calibrated opening feature extraction
- Keywords: `MATCHER_COLUMNS_V2`, `opening_vector_for_color`, `extract_opening_features`
- Defines the 9-feature vocabulary shared by player vectors and opening rows

**`opening_study_tree.py`** — Opening Study Tree engine
- Keywords: `get_opening_study_tree_children`, `compute_node_metrics`, `load_player_vector_from_cache`, `OpeningStudyTreeNode`, `OpeningStudyTreeRequest`, `compute_similarity`, `weighted_cosine`, `evaluate_engine_soundness`, `_root_children_for_black`, `_make_node`, `_load_opening_rows`, `_load_all_lines`, `_compute_global_priors`
- Lazy single-level expansion; style scores: aggressiveness, gambleness, systemness, memory complexity

**`custom_opening_explorer.py`** — alternative opening lookup (separate from study tree)

**`opening_repository.py`** — TSV/CSV opening data loading layer

**`opening_feature_distribution_tools.py`** — feature calibration utilities
- Keywords: `rank_calibrate_opening_group_features`, `empirical_cdf_values`, `write_group_features_with_raw`, `distribution_stats`

#### Player profile

**`player_feature_transformer.py`** — aggregates enriched games into a player vector
- Keywords: `PlayerProfile`, player vector aggregation

**`player_vector_cache.py`** — `.cache/player_vectors.json` load/store keyed by content hash

**`player_statistics.py`** — statistics bundle types
- Keywords: `PlayerStatisticsBundle`, `PlayerStatisticsBuilder`

**`statistics_shared.py`** — shared scoring utilities
- Keywords: `StatisticsHparams`, `PlayerGameSampler`, `loss_to_skill_score_base2`, `clamp01`, `username_key_value`

#### Position analysis

**`game_enrichment_transformer.py`** — per-move engine enrichment
- Keywords: `_classify_phase`, `_is_tactical_position`, `_is_quiet_middlegame`, `_classify_position_tags`, `EnrichedGame`, `EnrichedMove`

**`position_feature_extractor.py`** — structural board features
- Keywords: `extract_position_features`, `extract_position_vector`, `heuristic_engine_info`
- Extracts: pawn islands, passed pawns, open files, king safety, etc. into the 9-feature MATCHER vocabulary

**`global_statistics_transformer.py`** — aggregates enriched games into the full statistics bundle

**`chesscom_repository.py`** — low-level Chess.com HTTP fetching

### Opening Data (`openings_dataset/`)

- `all.tsv` — merged TSV from the `chess-openings` submodule; each row is one named opening line.
- `opening_feature_vectors.csv` — **primary dataset**: 148 rows, one per opening family, with calibrated `white_*`/`black_*`/generalized features, `line_count`, `final_structure_entropy`, `structure_diversity`, `representative_uci`, `representative_pgn`. Regenerated by `build_opening_feature_vectors.py`.
- The player vector stores only the 9 generalized features from `MATCHER_COLUMNS_V2` plus `structure_diversity`. `opening_vector_for_color(row, target_color)` maps the CSV's color-prefixed columns onto those same generalized keys for comparison.

### Neural Network — Position Style Encoder

Board position → 128-d L2-normalized embedding `z`, trained with multitask distillation heads.

#### Files

**`utils/position_style_encoder.py`** — model definition + training/inference utilities
- Keywords: `PositionStyleEncoder`, `BoardEncoder`, `ResidualBlock`, `PositionStyleDataset`, `embed_positions`, `train_one_epoch`, `evaluate`, `save_checkpoint`, `load_checkpoint`, `_get_device`
- Architecture: 18×8×8 AlphaZero input → stem conv → N residual blocks → global avg pool → Linear → L2-normalize → `z`
- 4 heads off `z`: `style` (MSE, 9 features), `phase` (3-way CE), `tactic` (multi-label BCE), `eval` (3-way CE, Stockfish mode only)
- Kendall learnable log-variance uncertainty weighting auto-balances head losses

**`utils/position_label_builder.py`** — label generation for training
- Keywords: `build_labels`, `LABEL_MODE`, `_lightweight_labels_for_position`, `_stockfish_labels_for_position`, `STYLE_COLS`, `PHASE_CLASSES`, `TACTIC_COLS_LIGHTWEIGHT`
- Two modes: `lightweight` (engine-free, ~560 pos/s, eval head masked) and `stockfish` (full pipeline, all 4 heads active)
- Caches to `.parquet` (or `.csv` fallback); reloads from cache automatically

**`train_encoder.py`** — training CLI and reusable API
- Keywords: `load_training_data`, `run_training`, `board_to_tensor`, `stream_pgn_games`, `build_positions`
- `load_training_data(cfg)` — streams PGN, builds labels (cached), builds tensors (cached `.npy`)
- `run_training(cfg, tensors, labels)` — writes `data/runs/<name>/losses.csv`, `summary.json`, `checkpoint.pt`
- Warmup scheduler: set `scheduler.warmup_epochs > 0` for `LinearLR` → `CosineAnnealingLR` via `SequentialLR`

**`run_sweep.py`** — multi-config hyperparameter sweep
- Keywords: `SWEEP_CONFIGS`, `deep_merge`, `cooldown`, `plot_loss_curves`, `plot_val_total_comparison`, `plot_final_metrics`
- Outputs: `data/sweep/{loss_curves,val_total_comparison,final_metrics}.png` + `summary.csv`

#### Config files

- `config/position_encoder_train.yaml` — base run: 8 blocks, width=128, lr=3e-4, 30 epochs
- `config/position_encoder_followup.yaml` — follow-up: 4 blocks, width=64, lr=1e-3, 5-epoch warmup, 60 epochs

#### Run a training

```bash
# base config
/Users/francescobassignana/miniforge3/envs/chess/bin/python train_encoder.py --config config/position_encoder_train.yaml

# follow-up experiment
/Users/francescobassignana/miniforge3/envs/chess/bin/python train_encoder.py --config config/position_encoder_followup.yaml

# full sweep (4 configs + plots)
/Users/francescobassignana/miniforge3/envs/chess/bin/python -u run_sweep.py
```

### Frontend (`frontend/`)

React Router 7 SPA (`ssr: false`), Tailwind CSS 4, Radix UI primitives. API base URL defaults to `http://localhost:8000` and is overridden via `VITE_API_BASE_URL`.

#### Routes (`frontend/app/routes/`)

| File | URL | Feature |
|---|---|---|
| `home.tsx` | `/` | Username entry form |
| `games.$username.tsx` | `/games/:username` | Paginated game list |
| `report.$username.tsx` | `/report/:username` | Full player report (stats + opening matches) |
| `opening-study.tsx` | `/opening-study?username=&color=` | Interactive Opening Study Tree whiteboard |
| `mistakes.$username.tsx` | `/mistakes/:username` | Mistakes analysis — blunder list |
| `mistakes.$username.blunder.$blunderKey.tsx` | `/mistakes/:username/blunder/:blunderKey` | Individual blunder deep-dive + punishment line |

Route declarations live in `frontend/app/routes.ts`.

#### API layer (`frontend/app/lib/`)

**`api.ts`** — all backend calls; keywords: `apiFetch`, `queryGames`, `buildReport`, `analyzeMistakes`, `analyzePosition`, `rematchOpenings`, `fetchOpeningStudyChildren`, `getReportByHash`, `getSavedReports`, `saveReport`, `deleteSavedReport`, `getDefaultHparams`

**`types.ts`** — TypeScript mirror of backend Pydantic models; keywords: `GameSummary`, `ReportBuildRequest`, `ReportBuildResponse`, `MistakesAnalysisRequest`, `MistakesAnalysisResponse`, `MistakeAnalysisItem`, `TacticTag`, `PunishmentLineMove`, `OpeningStudyTreeNode`, `OpeningStudyTreeChildrenRequest`, `OpeningStudyWeights`, `MetricPoint`, `OpeningMatch`, `MatcherFeatureKey`

**`utils.ts`** — shared formatting helpers

#### Components (`frontend/app/components/`)

**Opening Study** (`opening-study/`):
- `OpeningStudyWhiteboard.tsx` — main canvas: node layout, drag, zoom, expansion
- `OpeningStudyControls.tsx` — sidebar controls: color, weights, match mode, player
- `OpeningStudyNode.tsx` — individual node card with hover expansion
- `NodeInspectorPanel.tsx` — full node detail panel (metrics, lines, board)
- `NodeRadarChart.tsx` — radar chart of node style scores
- `StatBarChart.tsx` — bar chart for individual score components
- `MiniChessBoard.tsx` — lightweight CSS/Unicode board (avoids mounting heavy widgets)

**Report** (`report/`):
- `player-report.tsx` — full report layout and tabs
- `compare-report-view.tsx` — side-by-side comparison
- `report-config-form.tsx` — analysis parameters form
- `opening-board-preview.tsx` — FEN preview for opening matches

**Games** (`games/`):
- `game-card.tsx` — single game summary row
- `infinite-games-scroller.tsx` — paginated infinite scroll
- `player-stats-panel.tsx` — quick stats above game list

**Other**:
- `board/BoardZoomModal.tsx` — zoomable board overlay
- `charts/report-charts.tsx` — recharts wrappers for report sections
- `saved-reports-list.tsx` — saved report entries management
- `username-form.tsx` — home page username input
- `ui/` — hand-rolled primitives: `button`, `card`, `input`, `progress`, `tabs`

### Config (`config/`)

| File | Purpose |
|---|---|
| `global_statistics_hparams.yaml` | All analysis thresholds and weights (centipawn cutoffs, complexity percentiles, result scores, etc.) — loaded once by `backend/services/hparams_service.py`. Documented in `config/README.md`. |
| `position_encoder_train.yaml` | Base NN training config (8 blocks, width=128, lr=3e-4, 30 epochs) |
| `position_encoder_followup.yaml` | Follow-up NN experiment (4 blocks, width=64, lr=1e-3, warmup, 60 epochs) |

## After Every Change

After completing any code change, always ask the user which of these three actions to take:

1. **Commit** — draft a commit message and ask the user to confirm it before running `git commit`.
2. **Branch + Commit** — ask the user which branch to base off of, suggest a new branch name, draft a commit message, and ask the user to confirm before creating the branch and committing.
3. **Do nothing** — leave the working tree as-is.

Never commit or create branches without explicit user approval.

## Feature Flags / Important Invariants

- `opening_study_tree.py` is **additive**: it must not affect the existing opening explorer or report pipeline.
- Player vectors in the cache use **generalized** (non-color-prefixed) feature names. Color-specific comparison is done by reading `white_*`/`black_*` columns from the opening CSV, not by storing separate player vectors per color.
- The study-score formula weights are normalized by their sum inside `compute_node_metrics`, so unnormalized weights in API requests still produce valid `[0, 1]` scores.
- `_load_opening_rows` in the study tree is `@lru_cache(maxsize=8)` keyed by file path string — safe for the lifetime of the process but will not see CSV changes without a restart.
