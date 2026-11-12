"""Live Lichess Explorer positions, cached in MongoDB for every user.

Used past the catalogued opening lines, where the offline popularity snapshot
has no data. Requests are serialized with a minimum gap between them; a 429
blocks new requests for the time Lichess asks (a minute by default). While
blocked, a position that was never fetched answers ``pending`` instead of
holding the single API worker, and a cached but stale position is served as is.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import logging
import threading
import time
from typing import Any, Callable, Literal

import chess
import requests

from backend.services import mongo_service
from backend.settings import settings
from utils.lichess_explorer import (
    DEFAULT_RATE_LIMIT_WAIT_SECONDS,
    ExplorerAuthRejected,
    ExplorerRateLimited,
    ExplorerResponseError,
    ExplorerTransientError,
    cohort_label,
    default_window,
    move_games,
    request_explorer_position,
    standard_uci,
)
from utils.opening_popularity import position_key


logger = logging.getLogger(__name__)

NAMESPACE = "explorer_positions"
REFRESH_AFTER = timedelta(days=90)
MIN_REQUEST_INTERVAL_SECONDS = 1.0
# How long a request waits for another one in flight before answering "pending".
LOCK_WAIT_SECONDS = 15.0
TRANSIENT_WAIT_SECONDS = 5.0
BUSY_RETRY_SECONDS = 2.0

Status = Literal["ready", "pending", "unavailable"]


@dataclass(frozen=True)
class ExplorerMove:
    uci: str
    san: str
    games: int
    share: float
    white: int
    draws: int
    black: int
    average_rating: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "uci": self.uci,
            "san": self.san,
            "games": self.games,
            "share": self.share,
            "white": self.white,
            "draws": self.draws,
            "black": self.black,
            "averageRating": self.average_rating,
        }


@dataclass(frozen=True)
class ExplorerPosition:
    status: Status
    epd: str
    total_games: int = 0
    moves: tuple[ExplorerMove, ...] = field(default_factory=tuple)
    opening_eco: str | None = None
    opening_name: str | None = None
    fetched_at: str | None = None
    stale: bool = False
    retry_after: float | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "epd": self.epd,
            "totalGames": self.total_games,
            "moves": [move.to_dict() for move in self.moves],
            "openingEco": self.opening_eco,
            "openingName": self.opening_name,
            "fetchedAt": self.fetched_at,
            "stale": self.stale,
            "retryAfter": self.retry_after,
            "message": self.message,
        }


def cache_key(board: chess.Board) -> str:
    return f"{cohort_label()}:{position_key(board)}"


def _trim_payload(board: chess.Board, payload: dict[str, Any], *, since: str, until: str, fetched_at: str) -> dict[str, Any]:
    """Keep only what positions need; Explorer bodies also carry games and metadata."""
    opening = payload.get("opening") if isinstance(payload.get("opening"), dict) else None
    moves = []
    for move in payload.get("moves", []):
        if not isinstance(move, dict) or not move.get("uci"):
            continue
        rating = move.get("averageRating")
        moves.append({
            "uci": str(move["uci"]),
            "san": str(move.get("san") or ""),
            "white": int(move.get("white") or 0),
            "draws": int(move.get("draws") or 0),
            "black": int(move.get("black") or 0),
            "averageRating": int(rating) if isinstance(rating, (int, float)) else None,
        })
    return {
        "epd": position_key(board),
        "fen": board.fen(),
        "window": [since, until],
        "fetched_at": fetched_at,
        "white": int(payload.get("white") or 0),
        "draws": int(payload.get("draws") or 0),
        "black": int(payload.get("black") or 0),
        "moves": moves,
        "opening": {"eco": opening.get("eco"), "name": opening.get("name")} if opening else None,
    }


def _position_from_record(board: chess.Board, record: dict[str, Any], *, stale: bool) -> ExplorerPosition:
    raw_moves = [move for move in record.get("moves", []) if isinstance(move, dict) and move.get("uci")]
    covered = sum(move_games(move) for move in raw_moves)
    moves = []
    for move in raw_moves:
        uci = standard_uci(board, str(move["uci"]))
        if uci is None:
            continue
        san = str(move.get("san") or "") or board.san(chess.Move.from_uci(uci))
        games = move_games(move)
        moves.append(ExplorerMove(
            uci=uci,
            san=san,
            games=games,
            share=games / covered if covered else 0.0,
            white=int(move.get("white") or 0),
            draws=int(move.get("draws") or 0),
            black=int(move.get("black") or 0),
            average_rating=move.get("averageRating"),
        ))
    moves.sort(key=lambda move: move.games, reverse=True)
    opening = record.get("opening") or {}
    return ExplorerPosition(
        status="ready",
        epd=position_key(board),
        total_games=move_games(record),
        moves=tuple(moves),
        opening_eco=opening.get("eco") or None,
        opening_name=opening.get("name") or None,
        fetched_at=record.get("fetched_at"),
        stale=stale,
    )


class ExplorerService:
    def __init__(
        self,
        *,
        token: str | None,
        session: requests.Session | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleep: Callable[[float], None] = time.sleep,
        min_interval: float = MIN_REQUEST_INTERVAL_SECONDS,
        lock_wait: float = LOCK_WAIT_SECONDS,
    ) -> None:
        self._token = (token or "").strip() or None
        self._session = session or requests.Session()
        self._monotonic = monotonic
        self._now = now
        self._sleep = sleep
        self._min_interval = min_interval
        self._lock_wait = lock_wait
        self._lock = threading.Lock()
        self._last_request: float | None = None
        self._blocked_until = 0.0

    @property
    def configured(self) -> bool:
        return self._token is not None

    def cached(self, board: chess.Board) -> ExplorerPosition | None:
        """The cached position (fresh or stale), never touching the network."""
        record = mongo_service.blob_get(NAMESPACE, cache_key(board))
        if not isinstance(record, dict):
            return None
        return _position_from_record(board, record, stale=self._is_stale(record))

    def position(self, board: chess.Board) -> ExplorerPosition:
        cached = self.cached(board)
        if cached is not None and not cached.stale:
            return cached
        if not self.configured:
            return cached or self._unavailable(board, "The Lichess explorer is not configured (LICHESS_API_TOKEN).")
        remaining = self._blocked_until - self._monotonic()
        if remaining > 0:
            return cached or self._pending(board, remaining)

        if not self._lock.acquire(timeout=self._lock_wait):
            return cached or self._pending(board, BUSY_RETRY_SECONDS)
        try:
            # Another request may have fetched it, or hit the rate limit, while we waited.
            again = self.cached(board)
            if again is not None and not again.stale:
                return again
            remaining = self._blocked_until - self._monotonic()
            if remaining > 0:
                return cached or self._pending(board, remaining)
            return self._fetch(board, cached)
        finally:
            self._lock.release()

    def _fetch(self, board: chess.Board, cached: ExplorerPosition | None) -> ExplorerPosition:
        if self._last_request is not None:
            gap = self._last_request + self._min_interval - self._monotonic()
            if gap > 0:
                self._sleep(gap)
        since, until = default_window(self._now())
        try:
            payload = request_explorer_position(board, session=self._session, token=self._token or "", since=since, until=until)
        except ExplorerRateLimited as exc:
            wait = exc.retry_after if exc.retry_after is not None else DEFAULT_RATE_LIMIT_WAIT_SECONDS
            self._block(wait)
            logger.warning("Lichess Explorer rate limit; pausing requests for %.0f s", wait)
            return cached or self._pending(board, wait)
        except ExplorerTransientError as exc:
            wait = exc.retry_after if exc.retry_after is not None else TRANSIENT_WAIT_SECONDS
            self._block(wait)
            logger.warning("Lichess Explorer unavailable (%s); retrying in %.0f s", exc, wait)
            return cached or self._pending(board, wait)
        except ExplorerAuthRejected:
            self._last_request = self._monotonic()
            logger.error("Lichess Explorer rejected LICHESS_API_TOKEN")
            return cached or self._unavailable(board, "The Lichess explorer rejected the configured token.")
        except ExplorerResponseError as exc:
            self._last_request = self._monotonic()
            logger.warning("Lichess Explorer error for %s: %s", position_key(board), exc)
            return cached or self._unavailable(board, str(exc))
        self._last_request = self._monotonic()

        record = _trim_payload(board, payload, since=since, until=until, fetched_at=self._now().isoformat())
        mongo_service.blob_put(NAMESPACE, cache_key(board), record, epd=record["epd"])
        return _position_from_record(board, record, stale=False)

    def _block(self, seconds: float) -> None:
        self._last_request = self._monotonic()
        self._blocked_until = max(self._blocked_until, self._last_request + max(0.0, seconds))

    def _is_stale(self, record: dict[str, Any]) -> bool:
        try:
            fetched = datetime.fromisoformat(str(record.get("fetched_at")))
        except ValueError:
            return True
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        return self._now() - fetched > REFRESH_AFTER

    @staticmethod
    def _pending(board: chess.Board, retry_after: float) -> ExplorerPosition:
        return ExplorerPosition(
            status="pending",
            epd=position_key(board),
            retry_after=round(max(retry_after, 0.0), 1),
            message="Waiting for the Lichess explorer; try again shortly.",
        )

    @staticmethod
    def _unavailable(board: chess.Board, message: str) -> ExplorerPosition:
        return ExplorerPosition(status="unavailable", epd=position_key(board), message=message)


@lru_cache(maxsize=1)
def get_explorer_service() -> ExplorerService:
    """The process-wide client, so the rate limit is shared by every request."""
    return ExplorerService(token=settings.lichess_api_token)
