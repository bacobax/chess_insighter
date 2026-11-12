"""Lichess opening explorer client shared by the offline build and the API.

One request per call, no retries and no caching: callers decide how to wait
(the build script sleeps and retries, the API backs off and answers "pending").
Every Explorer request is made with the same player cohort so offline snapshot
values and live positions are comparable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

import chess
import requests


EXPLORER_URL = "https://explorer.lichess.org/lichess"
SPEEDS = ("blitz", "rapid")
RATINGS = (1200, 1400, 1600, 1800, 2000)
MAX_MOVES = 50
WINDOW_MONTHS = 24
REQUEST_TIMEOUT_SECONDS = 45.0
# Lichess asks clients to wait a full minute after an unannotated 429.
DEFAULT_RATE_LIMIT_WAIT_SECONDS = 60.0


class ExplorerError(RuntimeError):
    """Base class for Explorer failures."""


class ExplorerRateLimited(ExplorerError):
    def __init__(self, retry_after: float | None) -> None:
        super().__init__("Lichess Explorer rate limit reached")
        self.retry_after = retry_after


class ExplorerTransientError(ExplorerError):
    """Transport failure or 5xx: worth retrying later."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ExplorerAuthRejected(ExplorerError):
    """401/403: the token is missing, wrong or revoked."""


class ExplorerResponseError(ExplorerError):
    """Any other HTTP error or an unexpected body: retrying will not help."""


def _month_index(year: int, month: int) -> int:
    return year * 12 + month - 1


def _month_from_index(value: int) -> str:
    year, zero_month = divmod(value, 12)
    return f"{year:04d}-{zero_month + 1:02d}"


def default_window(now: datetime | None = None) -> tuple[str, str]:
    """The last 24 complete months, as Explorer ``since``/``until`` values."""
    current = now or datetime.now(timezone.utc)
    last_complete = _month_index(current.year, current.month) - 1
    return _month_from_index(last_complete - (WINDOW_MONTHS - 1)), _month_from_index(last_complete)


def cohort_label() -> str:
    """Identifies the player cohort (not the date window) of every request."""
    return f"{'-'.join(SPEEDS)}_{'-'.join(map(str, RATINGS))}_moves{MAX_MOVES}"


def explorer_params(board: chess.Board, *, since: str, until: str) -> dict[str, Any]:
    return {
        "variant": "standard",
        "fen": board.fen(),
        "speeds": ",".join(SPEEDS),
        "ratings": ",".join(str(rating) for rating in RATINGS),
        "since": since,
        "until": until,
        "moves": MAX_MOVES,
        "topGames": 0,
        "recentGames": 0,
    }


def _retry_after(headers: Mapping[str, str] | None) -> float | None:
    value = (headers or {}).get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def request_explorer_position(
    board: chess.Board,
    *,
    session: requests.Session,
    token: str,
    since: str,
    until: str,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Make exactly one Explorer request and return its JSON body.

    Raises a typed ``ExplorerError`` instead of retrying, so the caller can
    choose between sleeping (offline build) and backing off (API).
    """
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        response = session.get(
            EXPLORER_URL,
            params=explorer_params(board, since=since, until=until),
            headers=headers,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise ExplorerTransientError("Lichess Explorer transport failed") from exc

    status = response.status_code
    if status == 200:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ExplorerResponseError("Lichess Explorer returned malformed JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("moves", []), list):
            raise ExplorerResponseError("Lichess Explorer returned an unexpected response shape")
        return payload
    if status in {401, 403}:
        raise ExplorerAuthRejected("Lichess Explorer rejected the OAuth token")
    if status == 429:
        raise ExplorerRateLimited(_retry_after(response.headers))
    if status >= 500:
        raise ExplorerTransientError(f"Lichess Explorer failed with HTTP {status}", _retry_after(response.headers))
    raise ExplorerResponseError(f"Lichess Explorer failed with HTTP {status}")


def move_games(move: Mapping[str, Any]) -> int:
    return int(move.get("white") or 0) + int(move.get("draws") or 0) + int(move.get("black") or 0)


def normalized_moves(payload: Mapping[str, Any]) -> tuple[list[dict[str, Any]], int, int]:
    """``(moves with games + share, total games, games covered by the listed moves)``.

    Shares are over the covered games, so they add up to 1 across the listed moves.
    """
    total_games = move_games(payload)
    raw_moves = [move for move in payload.get("moves", []) if isinstance(move, dict) and move.get("uci")]
    covered_games = sum(move_games(move) for move in raw_moves)
    moves = [
        {
            "uci": str(move["uci"]),
            "games": move_games(move),
            "share": (move_games(move) / covered_games) if covered_games else 0.0,
        }
        for move in raw_moves
    ]
    return moves, total_games, covered_games
