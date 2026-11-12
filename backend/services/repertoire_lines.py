"""Expand a saved repertoire into the lines you need to know.

From a start position the walk plays your saved move at your turns (choices
are keyed by position, so transpositions reuse them) and branches over every
popular opponent reply. Each line carries its *reach*: the product of the
opponent's reply shares along it, i.e. how often you meet it.

A branch stops when:

- ``complete``     you have played ``max_own_moves`` moves, or the opponent has
                   no reply with at least the minimum share (``endReason``);
- ``out_of_book``  the position has fewer than ``min_position_games`` games;
- ``needs_choice`` it is your turn and you have not chosen a move yet;
- ``pending``      no popularity data is known yet for an opponent position
                   (call again: ``retryAfter`` says when);
- ``no_data``      no data and none can be fetched (Explorer not configured,
                   token rejected, …): final, polling will not help.

The opponent's most common reply is always followed, so main lines go as deep
as your move cap whatever their reach. Other replies are followed only while
the line's reach stays at or above ``min_reach``; replies below the share
floor or that cutoff are reported as ``pruned``. Every extra branch starts at
``min_reach`` or more, which keeps the number of lines manageable, but unlike
a pure cutoff there is no fixed upper bound.

The walk only reads cached data, except for up to ``fetch_budget`` uncached
opponent positions fetched from the live Explorer per call. The rest come back
``pending`` so the client can call again.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Sequence

import chess

from backend.services.explorer_service import ExplorerService, get_explorer_service
from backend.services.repertoire_service import RepertoireConfig, popularity, replay_prefix
from backend.settings import settings
from utils.opening_catalog_index import catalog_index
from utils.opening_popularity import position_key


LeafStatus = Literal["complete", "out_of_book", "needs_choice", "pending", "no_data"]
# Why a ``complete`` line ends.
EndReason = Literal["move_cap", "no_common_reply", "game_over", "depth_limit"]
MAX_NODES = 3000
# Retry hint when the per-call fetch budget ran out (the Explorer's request spacing).
BUDGET_RETRY_SECONDS = 1.0


@dataclass(frozen=True)
class LineSettings:
    min_reach: float = 0.02
    max_own_moves: int = 10


@dataclass
class _Walk:
    color: chess.Color
    choices: Mapping[str, Mapping[str, Any]]
    config: RepertoireConfig
    line_settings: LineSettings
    explorer: ExplorerService
    fetch_budget: int
    leaves: list[dict[str, Any]] = field(default_factory=list)
    pruned: float = 0.0
    nodes: int = 0
    truncated: bool = False
    retry_after: float | None = None
    used_choices: set[str] = field(default_factory=set)


def _popularity_for_walk(walk: _Walk, board: chess.Board):
    data = popularity(board, walk.explorer, live=False)
    if data.status == "pending" and data.source == "none" and walk.fetch_budget > 0 and walk.explorer.configured:
        walk.fetch_budget -= 1
        data = popularity(board, walk.explorer, live=True)
        if data.status == "pending":
            # Rate-limited or busy: stop fetching for the rest of this walk.
            walk.fetch_budget = 0
            if data.retry_after is not None:
                walk.retry_after = max(walk.retry_after or 0.0, data.retry_after)
    return data


def _leaf(
    walk: _Walk,
    board: chess.Board,
    moves: list[str],
    sans: list[str],
    reach: float,
    own_moves: int,
    status: LeafStatus,
    end_reason: EndReason | None = None,
) -> None:
    named = catalog_index(str(settings.openings_path)).deepest_opening(replay_prefix(moves))
    walk.leaves.append({
        "id": " ".join(moves),
        "prefixUci": list(moves),
        "san": list(sans),
        "reach": reach,
        "status": status,
        "endReason": end_reason,
        "ownMoves": own_moves,
        "epd": position_key(board),
        "openingEco": named[0].eco if named else None,
        "openingName": named[0].name if named else None,
    })


def _expand(walk: _Walk, board: chess.Board, moves: list[str], sans: list[str], reach: float, own_moves: int) -> None:
    walk.nodes += 1
    if walk.nodes > MAX_NODES or len(moves) >= 60:
        walk.truncated = True
        return _leaf(walk, board, moves, sans, reach, own_moves, "complete", "depth_limit")
    if board.is_game_over():
        return _leaf(walk, board, moves, sans, reach, own_moves, "complete", "game_over")

    if board.turn == walk.color:
        choice = walk.choices.get(position_key(board))
        if choice is None:
            data = popularity(board, walk.explorer, live=False)
            if data.status == "ready" and data.total_games < walk.config.min_position_games:
                return _leaf(walk, board, moves, sans, reach, own_moves, "out_of_book")
            return _leaf(walk, board, moves, sans, reach, own_moves, "needs_choice")
        move = chess.Move.from_uci(str(choice["uci"]))
        if move not in board.legal_moves:
            # A stale choice (should not happen: positions are keyed exactly).
            return _leaf(walk, board, moves, sans, reach, own_moves, "needs_choice")
        walk.used_choices.add(position_key(board))
        san = board.san(move)
        board.push(move)
        try:
            next_moves, next_sans = [*moves, move.uci()], [*sans, san]
            if own_moves + 1 >= walk.line_settings.max_own_moves:
                return _leaf(walk, board, next_moves, next_sans, reach, own_moves + 1, "complete", "move_cap")
            return _expand(walk, board, next_moves, next_sans, reach, own_moves + 1)
        finally:
            board.pop()

    data = _popularity_for_walk(walk, board)
    if data.status == "unavailable" or (data.status == "pending" and not walk.explorer.configured):
        return _leaf(walk, board, moves, sans, reach, own_moves, "no_data")
    if data.status != "ready":
        return _leaf(walk, board, moves, sans, reach, own_moves, "pending")
    if data.total_games < walk.config.min_position_games:
        return _leaf(walk, board, moves, sans, reach, own_moves, "out_of_book")
    replies = sorted(
        (m for m in data.moves if m["share"] >= walk.config.opponent_min_share),
        key=lambda m: m["share"],
        reverse=True,
    )[: walk.config.opponent_max_replies]
    expanded = 0.0
    for rank, reply in enumerate(replies):
        child_reach = reach * reply["share"]
        # The most common reply is always followed; the others only above the cutoff.
        if rank > 0 and child_reach < walk.line_settings.min_reach:
            continue
        expanded += child_reach
        move = chess.Move.from_uci(reply["uci"])
        board.push(move)
        try:
            _expand(walk, board, [*moves, reply["uci"]], [*sans, reply["san"]], child_reach, own_moves)
        finally:
            board.pop()
    # Rare replies and those under the reach cutoff are not drilled.
    walk.pruned += max(0.0, reach - expanded)
    if not replies:
        # No reply reaches the share floor: nothing common left to prepare for.
        _leaf(walk, board, moves, sans, reach, own_moves, "complete", "no_common_reply")
        walk.pruned -= reach  # counted as a leaf, not as pruned


def repertoire_lines(
    color: Literal["white", "black"],
    choices: Mapping[str, Mapping[str, Any]],
    *,
    start_prefix_uci: Sequence[str] = (),
    config: RepertoireConfig = RepertoireConfig(),
    line_settings: LineSettings = LineSettings(),
    explorer: ExplorerService | None = None,
    fetch_budget: int = 3,
) -> dict[str, Any]:
    boards = replay_prefix(start_prefix_uci)
    board = boards[-1].copy(stack=False)
    start_sans: list[str] = []
    replay = chess.Board()
    for uci in start_prefix_uci:
        move = chess.Move.from_uci(uci)
        start_sans.append(replay.san(move))
        replay.push(move)

    walk = _Walk(
        color=chess.WHITE if color == "white" else chess.BLACK,
        choices=choices,
        config=config,
        line_settings=line_settings,
        explorer=explorer or get_explorer_service(),
        fetch_budget=max(0, fetch_budget),
    )
    _expand(walk, board, list(start_prefix_uci), start_sans, 1.0, 0)

    walk.leaves.sort(key=lambda leaf: -leaf["reach"])
    by_status: dict[str, float] = {"complete": 0.0, "out_of_book": 0.0, "needs_choice": 0.0, "pending": 0.0, "no_data": 0.0}
    for leaf in walk.leaves:
        by_status[leaf["status"]] += leaf["reach"]
    pending = any(leaf["status"] == "pending" for leaf in walk.leaves)
    return {
        "color": color,
        "startPrefixUci": list(start_prefix_uci),
        "lines": [{**leaf, "reach": round(leaf["reach"], 4)} for leaf in walk.leaves],
        "coverage": {
            "complete": round(by_status["complete"], 4),
            "outOfBook": round(by_status["out_of_book"], 4),
            "needsChoice": round(by_status["needs_choice"], 4),
            "pending": round(by_status["pending"], 4),
            "noData": round(by_status["no_data"], 4),
            "pruned": round(max(0.0, walk.pruned), 4),
        },
        "status": "pending" if pending else "ready",
        "retryAfter": (walk.retry_after or BUDGET_RETRY_SECONDS) if pending else None,
        "choicesUsed": len(walk.used_choices),
        "truncated": walk.truncated,
        "settings": {"minReach": line_settings.min_reach, "maxOwnMoves": line_settings.max_own_moves},
    }
