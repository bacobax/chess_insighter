"""One repertoire position: your playable moves, or the opponent's popular replies.

Move popularity comes from the offline Lichess snapshot where the position is
catalogued, and from the live Explorer past the named lines (same player
cohort). On your turn every candidate (popular moves plus the engine's top
moves) is evaluated at depth 18 and marked ``playable`` when it is within
``cp_tolerance`` of the best move *and* leaves you at least ``min_eval_cp``.
The second rule keeps small per-move losses from adding up over a line.

Opponent turns need no engine: only how often each reply is played. Stopping
a line (reach probability, games, move cap) is the caller's job; this module
reports ``outOfBook`` when the position has too few games.

Lab scores are not computed here. ``labPrefixUci`` is the catalogued move order
reaching this position (possibly a transposition), which the client passes to
``/api/opening-study-tree/children`` to get study scores and explanations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Sequence

import chess

from backend.services.engine_eval_service import (
    DEFAULT_DEPTH,
    DEFAULT_MULTIPV,
    EngineBusy,
    EngineUnavailable,
    PositionEvaluation,
    evaluate_position,
)
from backend.services.explorer_service import ExplorerService, get_explorer_service
from backend.settings import settings
from utils.lichess_explorer import standard_uci
from utils.opening_catalog_index import CatalogIndex, catalog_index
from utils.opening_popularity import MIN_POPULARITY_GAMES, companion_path_for, load_popularity_snapshot, position_key


Color = Literal["white", "black"]
MAX_PLIES = 60
ENGINE_BUSY_RETRY_SECONDS = 3.0


@dataclass(frozen=True)
class RepertoireConfig:
    # A playable move of yours: at most this far behind the engine's best move…
    cp_tolerance: int = 50
    # …and the position after it at least this good for you (centipawns, your view).
    min_eval_cp: int = -100
    # Your popular candidates: at least this share of games, at most this many.
    own_min_share: float = 0.02
    own_max_popular: int = 8
    # Opponent replies listed: at least this share of games, at most this many.
    opponent_min_share: float = 0.02
    opponent_max_replies: int = 8
    # Fewer games than this in the position means it is out of book.
    min_position_games: int = MIN_POPULARITY_GAMES
    engine_depth: int = DEFAULT_DEPTH
    engine_multipv: int = DEFAULT_MULTIPV
    # How long a request waits for another engine search before answering "pending".
    engine_wait_seconds: float = 10.0


DEFAULT_CONFIG = RepertoireConfig()


@dataclass(frozen=True)
class _Popularity:
    source: Literal["snapshot", "live", "none"]
    status: Literal["ready", "pending", "unavailable"]
    total_games: int
    moves: list[dict[str, Any]]  # uci, san, games, share
    fetched_at: str | None = None
    retry_after: float | None = None
    message: str | None = None
    explorer_opening: tuple[str | None, str | None] | None = None


def replay_prefix(prefix_uci: Sequence[str]) -> list[chess.Board]:
    """Every position from the start to the end of ``prefix_uci``."""
    if len(prefix_uci) > MAX_PLIES:
        raise ValueError(f"A repertoire line can have at most {MAX_PLIES} plies.")
    board = chess.Board()
    boards = [board.copy(stack=False)]
    for index, token in enumerate(prefix_uci):
        try:
            move = chess.Move.from_uci(token)
        except ValueError as exc:
            raise ValueError(f"Move {index + 1} ({token!r}) is not a UCI move.") from exc
        if move not in board.legal_moves:
            raise ValueError(f"Move {index + 1} ({token}) is illegal in this position.")
        board.push(move)
        boards.append(board.copy(stack=False))
    return boards


def _san(board: chess.Board, uci: str) -> str | None:
    standard = standard_uci(board, uci)
    return board.san(chess.Move.from_uci(standard)) if standard else None


def is_playable(cp: int | None, cp_loss: int | None, config: RepertoireConfig) -> bool | None:
    """Within ``cp_tolerance`` of the best move and at least ``min_eval_cp`` for you."""
    if cp is None or cp_loss is None:
        return None
    return cp_loss <= config.cp_tolerance and cp >= config.min_eval_cp


def popularity(board: chess.Board, explorer: ExplorerService, *, live: bool = True) -> _Popularity:
    """Snapshot first (catalogued positions, no request spent), live Explorer otherwise.

    With ``live=False`` only cached Explorer data is used; a position never
    fetched comes back as ``source="none", status="pending"``.
    """
    record = load_popularity_snapshot(str(companion_path_for(settings.opening_vectors_path))).get(position_key(board))
    if record is not None:
        moves = []
        for item in record.moves:
            # The snapshot keeps Lichess's castling form (e1h1); match the engine's.
            uci = standard_uci(board, str(item.get("uci") or ""))
            if uci is None:
                continue
            san = _san(board, uci)
            moves.append({"uci": uci, "san": san, "games": int(item.get("games") or 0), "share": float(item.get("share") or 0.0)})
        return _Popularity("snapshot", "ready", record.total_games, moves)

    if not live:
        cached = explorer.cached(board)
        if cached is None:
            return _Popularity("none", "pending", 0, [])
    live = explorer.position(board) if live else cached
    if live.status != "ready":
        return _Popularity("none", live.status, 0, [], retry_after=live.retry_after, message=live.message)
    return _Popularity(
        "live",
        "ready",
        live.total_games,
        [{"uci": m.uci, "san": m.san, "games": m.games, "share": m.share} for m in live.moves],
        fetched_at=live.fetched_at,
        explorer_opening=(live.opening_eco, live.opening_name),
    )


def _child_catalog(index: CatalogIndex, board: chess.Board, uci: str) -> dict[str, Any]:
    child = board.copy(stack=False)
    child.push(chess.Move.from_uci(uci))
    named = index.opening_at(child)
    return {
        "openingEco": named.eco if named else None,
        "openingName": named.name if named else None,
        "inCatalog": index.lab_prefix_for(child) is not None or named is not None,
    }


def repertoire_position(
    color: Color,
    prefix_uci: Sequence[str],
    *,
    config: RepertoireConfig = DEFAULT_CONFIG,
    explorer: ExplorerService | None = None,
    engine=None,
) -> dict[str, Any]:
    boards = replay_prefix(prefix_uci)
    board = boards[-1]
    index = catalog_index(str(settings.openings_path))
    explorer = explorer or get_explorer_service()
    own_turn = (board.turn == chess.WHITE) == (color == "white")
    messages: list[str] = []
    retry_after: list[float] = []

    popularity_data = popularity(board, explorer)
    if popularity_data.status == "pending" and popularity_data.retry_after is not None:
        retry_after.append(popularity_data.retry_after)
    if popularity_data.message:
        messages.append(popularity_data.message)
    out_of_book = popularity_data.status == "ready" and popularity_data.total_games < config.min_position_games

    engine_block: dict[str, Any] = {"status": "skipped", "depth": config.engine_depth, "bestMove": None, "evalCp": None}
    moves: list[dict[str, Any]] = []
    if own_turn:
        popular = [
            m for m in popularity_data.moves
            if m["share"] >= config.own_min_share and m["games"] >= config.min_position_games
        ][: config.own_max_popular]
        evaluation: PositionEvaluation | None = None
        try:
            evaluation = evaluate_position(
                board,
                moves=[m["uci"] for m in popular],
                depth=config.engine_depth,
                multipv=config.engine_multipv,
                engine=engine,
                wait=config.engine_wait_seconds,
            )
            best = evaluation.moves.get(evaluation.best_move or "")
            engine_block.update(status="ready", bestMove=evaluation.best_move, evalCp=best.cp if best else None)
        except EngineBusy:
            engine_block["status"] = "pending"
            retry_after.append(ENGINE_BUSY_RETRY_SECONDS)
        except EngineUnavailable as exc:
            engine_block["status"] = "unavailable"
            messages.append(str(exc))

        by_uci: dict[str, dict[str, Any]] = {}
        for item in popularity_data.moves:
            by_uci[item["uci"]] = {"uci": item["uci"], "san": item["san"], "games": item["games"], "share": item["share"]}
        candidates = [m["uci"] for m in popular]
        if evaluation is not None:
            candidates += [m.uci for m in evaluation.ranked() if m.rank is not None]
        for uci in dict.fromkeys(candidates):
            entry = by_uci.get(uci) or {"uci": uci, "san": _san(board, uci) or uci, "games": 0, "share": 0.0}
            move_eval = evaluation.moves.get(uci) if evaluation else None
            cp_loss = evaluation.cp_loss(uci) if evaluation else None
            playable = is_playable(move_eval.cp if move_eval else None, cp_loss, config)
            moves.append({
                **entry,
                "cp": move_eval.cp if move_eval else None,
                "mate": move_eval.mate if move_eval else None,
                "cpLoss": cp_loss,
                "engineRank": move_eval.rank if move_eval else None,
                "playable": playable,
                **_child_catalog(index, board, uci),
            })
        # Playable first, then the moves people actually play, then the engine's order.
        moves.sort(key=lambda m: (m["playable"] is not True, -m["share"], m["cpLoss"] if m["cpLoss"] is not None else 10**6))
    else:
        replies = [m for m in popularity_data.moves if m["share"] >= config.opponent_min_share]
        replies.sort(key=lambda m: m["share"], reverse=True)
        for item in replies[: config.opponent_max_replies]:
            moves.append({
                **item,
                "cp": None,
                "mate": None,
                "cpLoss": None,
                "engineRank": None,
                "playable": None,
                **_child_catalog(index, board, item["uci"]),
            })

    deepest = index.deepest_opening(boards)
    opening = None
    if deepest is not None:
        named, ply = deepest
        opening = {"eco": named.eco, "name": named.name, "ply": ply, "exact": ply == len(boards) - 1}
    elif popularity_data.explorer_opening and popularity_data.explorer_opening[1]:
        eco, name = popularity_data.explorer_opening
        opening = {"eco": eco, "name": name, "ply": len(boards) - 1, "exact": True}

    # Partial answers (engine moves without shares, say) still carry what is known.
    pending = popularity_data.status == "pending" or engine_block["status"] == "pending"
    lab_prefix = index.lab_prefix_for(board)
    return {
        "status": "pending" if pending else "ready",
        "retryAfter": max(retry_after) if pending and retry_after else None,
        "messages": messages,
        "color": color,
        "prefixUci": list(prefix_uci),
        "fen": board.fen(),
        "epd": position_key(board),
        "ply": len(prefix_uci),
        "sideToMove": "white" if board.turn == chess.WHITE else "black",
        "ownTurn": own_turn,
        "opening": opening,
        "inCatalog": lab_prefix is not None or index.opening_at(board) is not None,
        "labPrefixUci": list(lab_prefix) if lab_prefix is not None else None,
        "popularity": {
            "source": popularity_data.source,
            "status": popularity_data.status,
            "totalGames": popularity_data.total_games,
            "fetchedAt": popularity_data.fetched_at,
            "outOfBook": out_of_book,
        },
        "engine": engine_block,
        "moves": moves,
        "settings": {"cpTolerance": config.cp_tolerance, "minEvalCp": config.min_eval_cp},
    }

