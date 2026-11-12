"""Deeper Stockfish evaluations for repertoire choices, cached in MongoDB.

The Opening Lab tree uses depth 8, which is too noisy for a move someone saves
into a repertoire. Here a position is searched once at ``DEFAULT_DEPTH`` with
the top ``DEFAULT_MULTIPV`` moves; moves outside that set (popular Explorer
moves, say) get one more search restricted to them, at the same depth, merged
into the same record. Every user shares the cache, so each position costs one search.

Scores are from the side to move's point of view. ``cp_loss`` is the
centipawn gap to the best move, never negative.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import threading
from typing import Any, Iterable, Iterator

import chess
import chess.engine

from backend.services import mongo_service
from backend.settings import settings
from utils.opening_popularity import position_key


NAMESPACE = "engine_evals"
DEFAULT_DEPTH = 18
DEFAULT_MULTIPV = 5
MATE_SCORE = 100_000
PV_PLIES = 6

# One search at a time: the API runs in a single process and Stockfish is CPU bound.
_engine_lock = threading.Lock()


class EngineUnavailable(RuntimeError):
    """No Stockfish binary is configured or found."""


class EngineBusy(RuntimeError):
    """Another search held the engine longer than the caller was willing to wait."""


@dataclass(frozen=True)
class MoveEvaluation:
    uci: str
    san: str
    cp: int
    mate: int | None
    rank: int | None
    pv: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"uci": self.uci, "san": self.san, "cp": self.cp, "mate": self.mate, "rank": self.rank, "pv": list(self.pv)}


@dataclass(frozen=True)
class PositionEvaluation:
    epd: str
    depth: int
    engine: str | None
    best_move: str | None
    moves: dict[str, MoveEvaluation]

    @property
    def best_cp(self) -> int | None:
        best = self.moves.get(self.best_move or "")
        return best.cp if best else None

    def cp_loss(self, uci: str) -> int | None:
        move = self.moves.get(uci)
        if move is None or self.best_cp is None:
            return None
        # A move searched on its own can come out slightly above the multipv best.
        return max(0, self.best_cp - move.cp)

    def ranked(self) -> list[MoveEvaluation]:
        return sorted(self.moves.values(), key=lambda move: move.cp, reverse=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "epd": self.epd,
            "depth": self.depth,
            "engine": self.engine,
            "bestMove": self.best_move,
            "moves": [{**move.to_dict(), "cpLoss": self.cp_loss(move.uci)} for move in self.ranked()],
        }


def cache_key(board: chess.Board, depth: int) -> str:
    return f"d{depth}:{position_key(board)}"


def _move_entry(board: chess.Board, info: dict[str, Any], rank: int | None) -> tuple[str, dict[str, Any]] | None:
    pv = info.get("pv") or []
    score = info.get("score")
    if not pv or score is None:
        return None
    pov = score.pov(board.turn)
    cp = pov.score(mate_score=MATE_SCORE)
    if cp is None:
        return None
    first = pv[0]
    line = []
    replay = board.copy(stack=False)
    for move in pv[:PV_PLIES]:
        if move not in replay.legal_moves:
            break
        line.append(move.uci())
        replay.push(move)
    return first.uci(), {"san": board.san(first), "cp": int(cp), "mate": pov.mate(), "rank": rank, "pv": line}


def _record_to_evaluation(board: chess.Board, record: dict[str, Any]) -> PositionEvaluation:
    moves = {
        uci: MoveEvaluation(
            uci=uci,
            san=str(entry.get("san") or ""),
            cp=int(entry["cp"]),
            mate=entry.get("mate"),
            rank=entry.get("rank"),
            pv=tuple(entry.get("pv") or ()),
        )
        for uci, entry in (record.get("moves") or {}).items()
    }
    return PositionEvaluation(
        epd=position_key(board),
        depth=int(record["depth"]),
        engine=record.get("engine"),
        best_move=record.get("best_move"),
        moves=moves,
    )


@contextmanager
def _open_engine(engine: chess.engine.SimpleEngine | None) -> Iterator[chess.engine.SimpleEngine]:
    if engine is not None:
        yield engine
        return
    path = settings.stockfish_path
    if not path:
        raise EngineUnavailable("Stockfish is not available (set STOCKFISH_PATH).")
    with chess.engine.SimpleEngine.popen_uci(path) as opened:
        yield opened


def cached_evaluation(board: chess.Board, *, depth: int = DEFAULT_DEPTH) -> PositionEvaluation | None:
    record = mongo_service.blob_get(NAMESPACE, cache_key(board, depth))
    return _record_to_evaluation(board, record) if isinstance(record, dict) else None


def evaluate_position(
    board: chess.Board,
    *,
    moves: Iterable[str] = (),
    depth: int = DEFAULT_DEPTH,
    multipv: int = DEFAULT_MULTIPV,
    engine: chess.engine.SimpleEngine | None = None,
    wait: float | None = None,
) -> PositionEvaluation:
    """Top ``multipv`` moves plus every legal move in ``moves``, at ``depth``.

    Only what the cache is missing is searched. Raises ``EngineUnavailable``
    when a search is needed and no Stockfish is configured, and ``EngineBusy``
    when another search keeps the engine for more than ``wait`` seconds
    (``None`` waits as long as it takes).
    """
    key = cache_key(board, depth)
    legal = {move.uci(): move for move in board.legal_moves}
    wanted = [uci for uci in dict.fromkeys(moves) if uci in legal]

    def missing(record: dict[str, Any] | None) -> tuple[bool, list[str]]:
        if record is None:
            return bool(legal), wanted
        need_multipv = int(record.get("multipv") or 0) < min(multipv, len(legal))
        known = record.get("moves") or {}
        return need_multipv, [uci for uci in wanted if uci not in known]

    record = mongo_service.blob_get(NAMESPACE, key)
    record = record if isinstance(record, dict) else None
    need_multipv, extra = missing(record)
    if record is not None and not need_multipv and not extra:
        return _record_to_evaluation(board, record)

    if not _engine_lock.acquire(timeout=-1 if wait is None else max(0.0, wait)):
        raise EngineBusy("The engine is busy with another position.")
    try:
        # Another request may have filled the cache while this one waited.
        record = mongo_service.blob_get(NAMESPACE, key)
        record = record if isinstance(record, dict) else None
        need_multipv, extra = missing(record)
        if record is None:
            record = {"depth": depth, "multipv": 0, "engine": None, "best_move": None, "moves": {}}
        if need_multipv or extra:
            limit = chess.engine.Limit(depth=max(1, int(depth)))
            with _open_engine(engine) as active:
                record["engine"] = active.id.get("name") if hasattr(active, "id") else None
                entries: dict[str, dict[str, Any]] = dict(record.get("moves") or {})
                if need_multipv:
                    count = min(multipv, len(legal))
                    analysed = active.analyse(board, limit, multipv=count)
                    infos = analysed if isinstance(analysed, list) else [analysed]
                    for rank, info in enumerate(infos, 1):
                        entry = _move_entry(board, info, rank)
                        if entry is not None:
                            entries[entry[0]] = entry[1]
                            if rank == 1:
                                record["best_move"] = entry[0]
                    record["multipv"] = count
                    extra = [uci for uci in wanted if uci not in entries]
                if extra:
                    # One search restricted to the extra moves, one line each.
                    analysed = active.analyse(board, limit, multipv=len(extra), root_moves=[legal[uci] for uci in extra])
                    for info in analysed if isinstance(analysed, list) else [analysed]:
                        entry = _move_entry(board, info, None)
                        if entry is not None and entry[0] in extra:
                            entries[entry[0]] = entry[1]
                record["moves"] = entries
            mongo_service.blob_put(NAMESPACE, key, record, epd=position_key(board), depth=depth)
    finally:
        _engine_lock.release()
    return _record_to_evaluation(board, record)
