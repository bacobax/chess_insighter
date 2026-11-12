"""Position-keyed index of the named opening lines in ``all.tsv``.

The Opening Lab tree follows exact move sequences, so a transposed move order
falls off it even when the position is catalogued. This index maps every
position on a catalogued line (by EPD) to:

- its name, when a named line ends there;
- the move sequence the Lab should expand from to see its continuations: the
  one most catalogued lines pass through, shortest first on ties.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Sequence

import chess

from utils.opening_popularity import position_key


@dataclass(frozen=True)
class NamedOpening:
    eco: str
    name: str


@dataclass(frozen=True)
class CatalogIndex:
    named: dict[str, NamedOpening]
    lab_prefix: dict[str, tuple[str, ...]]

    def opening_at(self, board: chess.Board) -> NamedOpening | None:
        return self.named.get(position_key(board))

    def lab_prefix_for(self, board: chess.Board) -> tuple[str, ...] | None:
        return self.lab_prefix.get(position_key(board))

    def deepest_opening(self, boards: Iterable[chess.Board]) -> tuple[NamedOpening, int] | None:
        """The last named position along a path, with its index in ``boards``."""
        found = None
        for index, board in enumerate(boards):
            named = self.opening_at(board)
            if named is not None:
                found = (named, index)
        return found


def _build(rows: Sequence[dict[str, str]]) -> CatalogIndex:
    named: dict[str, NamedOpening] = {}
    prefixes: dict[str, Counter[tuple[str, ...]]] = defaultdict(Counter)
    for row in rows:
        board = chess.Board()
        moves: list[str] = []
        valid = True
        # Every position on the line, start position included, that the line continues from.
        for token in str(row.get("uci") or "").split():
            prefixes[position_key(board)][tuple(moves)] += 1
            try:
                move = chess.Move.from_uci(token)
            except ValueError:
                valid = False
                break
            if move not in board.legal_moves:
                valid = False
                break
            board.push(move)
            moves.append(token)
        if not valid or not moves:
            continue
        name = str(row.get("name") or "").strip()
        if name:
            # Lines are sorted by ECO; the first name for a position wins.
            named.setdefault(position_key(board), NamedOpening(str(row.get("eco") or "").strip(), name))
    lab_prefix = {
        epd: min(counter.items(), key=lambda item: (-item[1], len(item[0]), item[0]))[0]
        for epd, counter in prefixes.items()
    }
    return CatalogIndex(named=named, lab_prefix=lab_prefix)


@lru_cache(maxsize=2)
def catalog_index(openings_path: str) -> CatalogIndex:
    with Path(openings_path).open(encoding="utf-8", newline="") as handle:
        return _build(list(csv.DictReader(handle, delimiter="\t")))
