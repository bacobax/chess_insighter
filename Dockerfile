# syntax=docker/dockerfile:1
#
# Backend image: FastAPI + Stockfish (compiled from source for the target CPU).
# Build:  docker compose build api
# The frontend is built and served by the `web` (Caddy) image, see frontend/Dockerfile.

ARG PYTHON_VERSION=3.12

# ---------------------------------------------------------------------------
# Stage 1: compile Stockfish. Pinned tag; the NNUE net is downloaded by `make`.
# ---------------------------------------------------------------------------
FROM debian:bookworm-slim AS stockfish
ARG STOCKFISH_TAG=sf_18
# Empty = pick automatically from the target platform (see below).
ARG STOCKFISH_ARCH=
ARG TARGETARCH
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch "${STOCKFISH_TAG}" https://github.com/official-stockfish/Stockfish.git /stockfish
WORKDIR /stockfish/src
# arm64 -> armv8-dotprod (Ampere Altra / Neoverse N1 and Apple Silicon both support dotprod)
# amd64 -> x86-64-avx2 (any x86 server from the last ~10 years)
RUN ARCH="${STOCKFISH_ARCH}"; \
    if [ -z "$ARCH" ]; then \
      case "${TARGETARCH}" in \
        arm64) ARCH=armv8-dotprod ;; \
        amd64) ARCH=x86-64-avx2 ;; \
        *) echo "Unsupported TARGETARCH=${TARGETARCH}; pass --build-arg STOCKFISH_ARCH=..." >&2; exit 1 ;; \
      esac; \
    fi; \
    make -j"$(nproc)" build ARCH="$ARCH" \
    && strip stockfish \
    && ./stockfish bench 2>&1 | tail -n 3

# ---------------------------------------------------------------------------
# Stage 2: Python runtime.
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:${PATH}" \
    STOCKFISH_PATH=/usr/local/bin/stockfish \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

# Dependencies first (cached unless pyproject/uv.lock change). App deps only: no dev/ml/notebooks.
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY --from=stockfish /stockfish/src/stockfish /usr/local/bin/stockfish

# Application code and the data it reads at runtime (paths are relative to /app).
COPY backend ./backend
COPY utils ./utils
COPY config ./config
COPY openings_dataset ./openings_dataset

RUN useradd --system --uid 10001 --no-create-home app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

# Exactly one worker: build jobs and their WebSocket status streams live in process memory.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
