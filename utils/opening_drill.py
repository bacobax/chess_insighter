"""Opening drill lines: a repertoire line where the opponent varies.

At the opponent's turns the drill branches over the popular replies in the
Lichess popularity snapshot, each weighted by how often it is played. At the player's turns the repertoire move is
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


# Branches the opponent reaches in under 2% of games are left out of the catalog.
MIN_LINE_PROBABILITY = 0.02


def _main_moves(main_line: list[str]) -> list[chess.Move]:
    probe = chess.Board()
    moves = []
    for san in main_line:
        try:
            move = probe.parse_san(san)
        except ValueError as exc:
            raise ValueError(f"Illegal move in the opening line: {san}") from exc
        moves.append(move)
        probe.push(move)
    return moves


def drill_catalog(
    main_line: list[str],
    user_color: str,
    *,
    popularity_path: str | Path,
    openings_path: str | Path,
    min_probability: float = MIN_LINE_PROBABILITY,
) -> list[dict[str, Any]]:
    """Every drill line worth knowing for one repertoire opening.

    The opponent branches over its popular replies; the player always has one
    answer. Each line carries the chance of meeting it (product of the
    opponent's normalised reply shares). The main line comes first, the rest by
    probability.
    """
    snapshot = load_popularity_snapshot(str(popularity_path))
    names = _opening_names(str(openings_path))
    user_turn = chess.WHITE if user_color == "white" else chess.BLACK
    main_moves = _main_moves(main_line)
    target_plies = len(main_moves)
    lines: list[dict[str, Any]] = []

    def leaf(moves: list[str], choices: list[dict[str, Any]], probability: float, deviates_at: int | None, named: tuple[str, str]) -> None:
        lines.append({
            "id": " ".join(moves),
            "moves": list(moves),
            "user_color": user_color,
            "eco": named[0] or None,
            "variation": named[1] or None,
            "probability": probability,
            "main_line": deviates_at is None,
            "deviates_at": deviates_at,
            "opponent_choices": list(choices),
        })

    def walk(board: chess.Board, moves: list[str], choices: list[dict[str, Any]], probability: float,
             on_main: bool, deviates_at: int | None, named: tuple[str, str]) -> None:
        ply = len(moves)
        if ply >= target_plies:
            return leaf(moves, choices, probability, deviates_at, named)
        main_move = main_moves[ply] if on_main else None
        popular = _popular_moves(board, snapshot)

        def play(move: chess.Move, next_probability: float, choice: dict[str, Any] | None) -> None:
            san = board.san(move)
            board.push(move)
            walk(
                board,
                [*moves, san],
                [*choices, choice] if choice else choices,
                next_probability,
                on_main and move == main_move,
                deviates_at if move == main_move or not on_main else ply,
                names.get(position_key(board), named),
            )
            board.pop()

        if board.turn == user_turn:
            if main_move is not None:
                return play(main_move, probability, None)
            answers = [entry for entry in popular if entry[2] >= MIN_ANSWER_GAMES]
            return play(answers[0][0], probability, None) if answers else leaf(moves, choices, probability, deviates_at, named)

        candidates = [entry for entry in popular if entry[1] >= MIN_REPLY_SHARE][:MAX_REPLIES]
        if main_move is not None and all(entry[0] != main_move for entry in candidates):
            candidates.append((main_move, MAIN_LINE_FALLBACK_SHARE, 0))
        if main_move is not None and ply < PINNED_PLIES:
            candidates = [entry for entry in candidates if entry[0] == main_move]
        if not candidates:
            return leaf(moves, choices, probability, deviates_at, named)
        total = sum(max(entry[1], 0.01) for entry in candidates)
        explored = False
        for move, share, _games in candidates:
            weight = max(share, 0.01) / total
            if probability * weight < min_probability and move != main_move:
                continue
            explored = True
            play(move, probability * weight, {
                "ply": ply,
                "san": board.san(move),
                "share": share,
                "main_line": move == main_move,
                "alternatives": [{"san": board.san(other[0]), "share": other[1]} for other in candidates if other[0] != move],
            })
        if not explored:
            leaf(moves, choices, probability, deviates_at, named)

    walk(chess.Board(), [], [], 1.0, True, None, ("", ""))
    total = sum(line["probability"] for line in lines) or 1.0
    for line in lines:
        line["probability"] = round(line["probability"] / total, 4)
    lines.sort(key=lambda line: (not line["main_line"], -line["probability"]))
    return lines


def sample_drill_line(
    main_line: list[str],
    user_color: str,
    *,
    popularity_path: str | Path,
    openings_path: str | Path,
    variations: bool = True,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Pick one catalog line, weighted by how often the opponent plays into it."""
    rng = rng or random.Random()
    catalog = drill_catalog(main_line, user_color, popularity_path=popularity_path, openings_path=openings_path)
    if not variations:
        return catalog[0]
    return rng.choices(catalog, weights=[max(line["probability"], 0.001) for line in catalog])[0]
