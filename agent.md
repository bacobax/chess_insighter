# Chess Insighter Agent Guide

## Project overview

Chess Insighter is a local full-stack chess analysis application. It fetches Chess.com games, enriches positions with Stockfish, builds player reports, analyzes mistakes, recommends openings, and exposes an interactive opening-study tree.

The repository has three main areas:

- `backend/`: FastAPI routes, Pydantic API models, application settings, caching, and orchestration services.
- `utils/`: chess analysis, feature extraction, statistics, opening matching, and ML training utilities. Keep this layer independent of FastAPI where practical.
- `frontend/`: React 19 and React Router 7 single-page application, styled with Tailwind CSS 4 and Radix primitives.

The position-style encoder (`train_encoder.py`, `run_sweep.py`, and `utils/position_style_encoder.py`) is an independent training pipeline. Opening source data lives in `chess-openings/`; application-ready datasets live in `openings_dataset/`.

## Environment

Run Python commands in the `chess` conda environment. It contains `python-chess`, FastAPI, Stockfish integrations, and the other required packages.

```bash
conda run -n chess python --version
conda run -n chess python -m pip install -r requirements.txt
```

The frontend uses npm and must be run from `frontend/`.

```bash
cd frontend
npm install
```

Stockfish is discovered in this order:

1. `STOCKFISH_PATH`
2. `stockfish` on `PATH`
3. `/opt/homebrew/bin/stockfish`

Most unit tests use fake engines, but mistake analysis and some data-generation workflows require a real Stockfish binary.

## Common commands

From the repository root:

```bash
# Backend development server: http://localhost:8000
conda run -n chess python -m uvicorn backend.main:app --port 8000 --reload

# Full Python test suite
conda run -n chess python -m pytest -q

# Focused Python test
conda run -n chess python -m pytest test_opening_study_tree.py -q

# Rebuild opening vectors (expensive; requires Stockfish)
conda run -n chess python build_opening_feature_vectors.py
```

From `frontend/`:

```bash
# Frontend development server: http://localhost:5173
npm run dev

# Generate React Router types and run TypeScript checks
npm run typecheck

# Production build
npm run build
```

The frontend uses `http://localhost:8000` by default. Override it with `VITE_API_BASE_URL` when needed.

## Architecture and conventions

### Backend

- Define the HTTP contract in `backend/models.py` and routes in `backend/main.py`.
- Put orchestration and persistence in `backend/services/`; keep analysis algorithms in `utils/`.
- CPU-bound synchronous work called by async routes must run through `run_in_threadpool`.
- Use the frozen `settings` object from `backend/settings.py` for paths, CORS, and Stockfish discovery. Do not duplicate repository-relative paths.
- Preserve typed service errors and translate them to HTTP responses at the route boundary.
- Cache keys must be deterministic and include every input that changes the result. Reuse `stable_hash` and related helpers from `backend/services/cache_service.py`.
- Cache writes belong under `.cache/`. Do not commit runtime reports, player vectors, or report-analysis artifacts.

### Frontend

- Route declarations live in `frontend/app/routes.ts`; route modules live in `frontend/app/routes/`.
- Keep all HTTP calls in `frontend/app/lib/api.ts`.
- Keep TypeScript API types in `frontend/app/lib/types.ts` synchronized with the Pydantic models in `backend/models.py`.
- Reuse components in `frontend/app/components/ui/` and the shared helpers in `frontend/app/lib/utils.ts` before adding duplicates.
- Follow the existing design language in `frontend/app/app.css` and nearby components. Preserve responsive behavior and keyboard accessibility.
- React Router is configured as an SPA (`ssr: false`). Do not assume server-side loaders or actions are available.

### Analysis and data

- The nine matcher features defined by `MATCHER_COLUMNS_V2` are a shared vocabulary across player profiles, position features, and opening vectors. A feature change must be propagated across producers, consumers, CSV generation, API types, and tests.
- Chess color and evaluation orientation are easy sources of regressions. Explicitly test behavior for both White and Black whenever changing scores, losses, moves, or opening matches.
- Opening feature vectors in `openings_dataset/opening_feature_vectors.csv` are generated data. Change the generator first, then regenerate the dataset intentionally.
- Treat `openings_dataset/all.tsv` and the `chess-openings/` corpus as source data. Avoid broad formatting or line-ending rewrites.
- ML artifacts under `data/`, diagnostic plots, caches, notebooks, and large generated datasets should not be modified unless the task explicitly requires them.

## Testing expectations

- Add or update focused tests with behavioral changes. Tests exist both as root-level `test_*.py` files and under `tests/`.
- Prefer deterministic fixtures and fake/scripted chess engines for unit tests.
- Run the narrowest relevant test while iterating, then run the full Python suite before handing off backend or analysis changes.
- For frontend changes, run `npm run typecheck`; also run `npm run build` for routing, bundling, or dependency changes.
- When an API shape changes, verify the backend model, service response, frontend type, API client, and consuming component together.

## Working rules

- Preserve unrelated changes in the working tree. Do not reset, reformat, or overwrite files outside the requested scope.
- Prefer small, typed changes that follow the existing module boundaries.
- Do not silently replace calibrated formulas, thresholds, or weights. These are domain behavior; update configuration and tests deliberately.
- Avoid committing secrets, local absolute paths, downloaded game data, caches, model checkpoints, or generated build output.
- Document any command that regenerates tracked datasets and call out when results depend on the installed Stockfish version.
