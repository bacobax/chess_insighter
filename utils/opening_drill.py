"""Opening drill lines: a repertoire line where the opponent varies.

At the opponent's turns a reply is sampled from the Lichess popularity snapshot,
weighted by how often it is played. At the player's turns the repertoire move is
used while still on the main line; after the opponent deviates, the player's
most popular answer in that position is used instead.
"""

from __future__ import annotations

import csv
import random
from functools import lru_cache
from pathlib import Path
from typing import Any

import chess

from utils.opening_popularity import load_popularity_snapshot, position_key


MIN_REPLY_SHARE = 0.05
MAX_REPLIES = 4
MIN_ANSWER_GAMES = 30
# Weight given to the main-line reply when the snapshot has no data for it.
MAIN_LINE_FALLBACK_SHARE = 0.25
# The first two plies define the repertoire slot (1.e4 e5 for the Italian,
# 1.e4 for the Petrov, 1.d4 for the QGD), so the opponent never varies there.
PINNED_PLIES = 2


@lru_cache(maxsize=2)
def _opening_names(path: str) -> dict[str, tuple[str, str]]:
    names: dict[str, tuple[str, str]] = {}
    with Path(path).open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            epd = (row.get("epd") or "").strip()
            if epd:
                names[epd] = (row.get("eco") or "", row.get("name") or "")
    return names


def parse_line_text(line: str) -> list[str]:
    """"1.e4 e5 2.Nf3 Nc6" (or "1. e4 e5", "1…e5") → ["e4", "e5", "Nf3", "Nc6"]."""
    moves = []
    for token in line.replace("…", " ").split():
        token = token.split(".")[-1]
        if token and not token.isdigit():
            moves.append(token)
    if not moves:
        raise ValueError("The opening line has no moves.")
    return moves


def _popular_moves(board: chess.Board, snapshot: dict[str, Any]) -> list[tuple[chess.Move, float, int]]:
    record = snapshot.get(position_key(board))
    if record is None:
        return []
    moves = []
    for item in record.moves:
        try:
            move = chess.Move.from_uci(str(item.get("uci") or ""))
        except ValueError:
            continue
        if move in board.legal_moves:
            moves.append((move, float(item.get("share") or 0.0), int(item.get("games") or 0)))
    return sorted(moves, key=lambda entry: entry[1], reverse=True)


def sample_drill_line(
    main_line: list[str],
    user_color: str,
    *,
    popularity_path: str | Path,
    openings_path: str | Path,
    variations: bool = True,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Return a drill line as SAN moves plus where and how the opponent varied."""
    rng = rng or random.Random()
    snapshot = load_popularity_snapshot(str(popularity_path))
    names = _opening_names(str(openings_path))
    user_turn = chess.WHITE if user_color == "white" else chess.BLACK

    board = chess.Board()
    main_moves: list[chess.Move] = []
    probe = chess.Board()
    for san in main_line:
        try:
            move = probe.parse_san(san)
        except ValueError as exc:
            raise ValueError(f"Illegal move in the opening line: {san}") from exc
        main_moves.append(move)
        probe.push(move)

    target_plies = len(main_moves)
    moves: list[str] = []
    choices: list[dict[str, Any]] = []
    on_main = True
    deviates_at: int | None = None
    eco, name = "", ""

    while len(moves) < target_plies:
        ply = len(moves)
        main_move = main_moves[ply] if on_main and ply < len(main_moves) else None
        popular = _popular_moves(board, snapshot)

        if board.turn == user_turn:
            if main_move is not None:
                move = main_move
            else:
                answers = [entry for entry in popular if entry[2] >= MIN_ANSWER_GAMES]
                if not answers:
                    break
                move = answers[0][0]
        else:
            candidates = [entry for entry in popular if entry[1] >= MIN_REPLY_SHARE][:MAX_REPLIES]
            if main_move is not None and all(entry[0] != main_move for entry in candidates):
                candidates.append((main_move, MAIN_LINE_FALLBACK_SHARE, 0))
            if main_move is not None and (not variations or ply < PINNED_PLIES):
                move = main_move
            elif candidates:
                move = rng.choices([entry[0] for entry in candidates], weights=[max(entry[1], 0.01) for entry in candidates])[0]
            else:
                break
            share = next((entry[1] for entry in candidates if entry[0] == move), None)
            choices.append({
                "ply": ply,
                "san": board.san(move),
                "share": share,
                "main_line": move == main_move,
                "alternatives": [{"san": board.san(entry[0]), "share": entry[1]} for entry in candidates if entry[0] != move],
            })
            if main_move is not None and move != main_move:
                on_main = False
                deviates_at = ply

        moves.append(board.san(move))
        board.push(move)
        named = names.get(position_key(board))
        if named:
            eco, name = named

    return {
        "moves": moves,
        "user_color": user_color,
        "eco": eco or None,
        "variation": name or None,
        "deviates_at": deviates_at,
        "opponent_choices": choices,
    }
