# opening_repository.py

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Iterable
import csv

import chess
import chess.pgn


@dataclass(frozen=True)
class Opening:
    eco: str
    name: str
    pgn: str
    uci: str
    epd: str
    ply: int


class OpeningRepository:
    """
    Loads the Lichess chess-openings dataset and retrieves openings by board position.

    Expected dataset file:
        openings_dataset/all.tsv

    Required columns:
        eco, name, pgn, uci, epd
    """

    def __init__(self, dataset_path: str | Path):
        self.dataset_path = Path(dataset_path)
        self._by_epd: dict[str, Opening] = {}
        self._load()

    @staticmethod
    def _position_key(epd_or_fen: str) -> str:
        """
        Normalize a position string to the four fields used by the openings TSV.

        The dataset stores EPD-style keys:
            board side-to-move castling-rights en-passant-square

        `python-chess` callers may pass either EPD or full six-field FEN. Keeping
        only the first four fields makes both forms comparable.
        """
        fields = epd_or_fen.strip().split()
        if len(fields) < 4:
            return epd_or_fen.strip()

        return " ".join(fields[:4])

    def _load(self) -> None:
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"Opening dataset not found: {self.dataset_path}")

        with self.dataset_path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file, delimiter="\t")

            required_columns = {"eco", "name", "pgn", "uci", "epd"}
            if reader.fieldnames is None or not required_columns.issubset(reader.fieldnames):
                raise ValueError(
                    f"Invalid opening dataset. Required columns: {required_columns}. "
                    f"Found: {reader.fieldnames}"
                )

            for row in reader:
                uci_moves = row["uci"].strip().split()
                ply = len(uci_moves)

                opening = Opening(
                    eco=row["eco"].strip(),
                    name=row["name"].strip(),
                    pgn=row["pgn"].strip(),
                    uci=row["uci"].strip(),
                    epd=self._position_key(row["epd"]),
                    ply=ply,
                )

                # If duplicate positions exist, keep the deepest/more specific one.
                existing = self._by_epd.get(opening.epd)
                if existing is None or opening.ply > existing.ply:
                    self._by_epd[opening.epd] = opening

    def get_by_epd(self, epd: str) -> Optional[Opening]:
        return self._by_epd.get(self._position_key(epd))

    def get_by_fen(self, fen: str) -> Optional[Opening]:
        return self.get_by_epd(fen)

    def get_by_board(self, board: chess.Board) -> Optional[Opening]:
        return self.get_by_epd(board.epd())

    def detect_from_uci_moves(self, uci_moves: Iterable[str]) -> Optional[Opening]:
        """
        Detects the deepest matching opening from a sequence of UCI moves.

        UCI move example:
            e2e4
            g1f3
            e7e8q
        """

        board = chess.Board()
        best_match: Optional[Opening] = self.get_by_board(board)

        for uci in uci_moves:
            move = chess.Move.from_uci(uci)

            if move not in board.legal_moves:
                raise ValueError(f"Illegal move {uci} in position: {board.fen()}")

            board.push(move)

            opening = self.get_by_board(board)
            if opening is not None:
                best_match = opening

        return best_match

    def detect_from_pgn_game(self, game: chess.pgn.Game) -> Optional[Opening]:
        """
        Detects the deepest matching opening from a parsed python-chess PGN game.
        """

        board = game.board()
        best_match: Optional[Opening] = self.get_by_board(board)

        for move in game.mainline_moves():
            board.push(move)

            opening = self.get_by_board(board)
            if opening is not None:
                best_match = opening

        return best_match

    def __len__(self) -> int:
        return len(self._by_epd)
