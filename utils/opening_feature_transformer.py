from __future__ import annotations

from dataclasses import dataclass
import csv
import math
import re
import unicodedata
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Optional

import chess
import chess.engine

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - exercised only when tqdm is absent.
    tqdm = None


DEFAULT_STOCKFISH_PATH = "/opt/homebrew/bin/stockfish"

VECTOR_COLUMNS = [
    "tactical_density",
    "quiet_position_density",
    "king_safety_risk",
    "early_castling_tendency",
    "opposite_side_castling_tendency",
    "middlegame_complexity",
    "pawn_structure_sharpness",
    "material_imbalance",
    "endgame_likelihood_proxy",
    "structure_diversity",
]


@dataclass(frozen=True)
class OpeningLine:
    eco: str
    name: str
    pgn: str
    uci: str
    epd: str


@dataclass(frozen=True)
class EngineMoveInfo:
    move_uci: Optional[str]
    eval_cp: Optional[int]
    line_uci: list[str]


@dataclass(frozen=True)
class EnginePositionInfo:
    eval_cp: Optional[int]
    top_moves: list[EngineMoveInfo]
    best_move_cp_gain: float
    eval_volatility: float
    low_gap_between_top_moves: float
    best_move_is_forcing: bool
    forcing_line_depth: int


@dataclass(frozen=True)
class LineFeatureVector:
    opening_name: str
    eco: str
    pgn: str
    uci: str
    tactical_density: float
    quiet_position_density: float
    king_safety_risk: float
    early_castling_tendency: float
    opposite_side_castling_tendency: float
    middlegame_complexity: float
    pawn_structure_sharpness: float
    material_imbalance: float
    endgame_likelihood_proxy: float
    structure_signature: str


@dataclass(frozen=True)
class OpeningGroupFeatureVector:
    opening_name: str
    line_count: int
    eco_values: str
    representative_pgn: str
    representative_uci: str
    tactical_density: float
    quiet_position_density: float
    king_safety_risk: float
    early_castling_tendency: float
    opposite_side_castling_tendency: float
    middlegame_complexity: float
    pawn_structure_sharpness: float
    material_imbalance: float
    endgame_likelihood_proxy: float
    structure_diversity: float

    def vector(self) -> list[float]:
        return [float(getattr(self, column)) for column in VECTOR_COLUMNS]


def load_opening_lines(dataset_path: str | Path) -> list[OpeningLine]:
    path = Path(dataset_path)
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file, delimiter="\t")
        required = {"eco", "name", "pgn", "uci", "epd"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"Dataset must contain columns {sorted(required)}")

        return [
            OpeningLine(
                eco=row["eco"].strip(),
                name=row["name"].strip(),
                pgn=row["pgn"].strip(),
                uci=row["uci"].strip(),
                epd=row["epd"].strip(),
            )
            for row in reader
        ]


def normalize_opening_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", name).strip().lower()
    normalized = normalized.replace("'", "")
    normalized = re.sub(r"[/,:;()\-\u2013\u2014]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def ascii_fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def opening_alias_prefix(name: str) -> str:
    aliases = {
        normalize_opening_name("Ruy Lopez / Spanish Opening"): "ruy lopez",
        normalize_opening_name("Italian Game / Giuoco Piano"): "italian game",
        normalize_opening_name("Grunfeld Defense"): "grunfeld defense",
        normalize_opening_name("Grünfeld Defense"): "grunfeld defense",
    }
    key = normalize_opening_name(ascii_fold(name))
    return aliases.get(key, key)


def opening_family_name(name: str, eco: Optional[str] = None) -> str:
    folded = normalize_opening_name(ascii_fold(name))
    aliases = {
        normalize_opening_name(ascii_fold("Ruy Lopez / Spanish Opening")): "Ruy Lopez",
        normalize_opening_name(ascii_fold("Ruy Lopez")): "Ruy Lopez",
        normalize_opening_name(ascii_fold("Italian Game / Giuoco Piano")): "Italian Game",
        normalize_opening_name(ascii_fold("Italian Game")): "Italian Game",
        normalize_opening_name(ascii_fold("Giuoco Piano")): "Italian Game",
        normalize_opening_name(ascii_fold("Grunfeld Defense")): "Grünfeld Defense",
        normalize_opening_name(ascii_fold("Grünfeld Defense")): "Grünfeld Defense",
    }
    if folded in aliases:
        return aliases[folded]

    base = name.split(":", 1)[0].strip()
    base_folded = normalize_opening_name(ascii_fold(base))
    return aliases.get(base_folded, base)


def replay_boards(uci_moves: str) -> tuple[list[chess.Board], list[chess.Move]]:
    board = chess.Board()
    boards = [board.copy()]
    moves: list[chess.Move] = []

    for move_uci in uci_moves.split():
        move = chess.Move.from_uci(move_uci)
        if move not in board.legal_moves:
            raise ValueError(f"Illegal move {move_uci} in {board.fen()}")
        moves.append(move)
        board.push(move)
        boards.append(board.copy())

    return boards, moves


def legal_captures_count(board: chess.Board) -> int:
    return sum(1 for move in board.legal_moves if board.is_capture(move))


def legal_checks_count(board: chess.Board) -> int:
    return sum(1 for move in board.legal_moves if board.gives_check(move))


def hanging_pieces_count(board: chess.Board) -> int:
    count = 0
    for square, piece in board.piece_map().items():
        attackers = board.attackers(not piece.color, square)
        defenders = board.attackers(piece.color, square)
        if attackers and not defenders and piece.piece_type != chess.KING:
            count += 1
    return count


def attacked_high_value_pieces_count(board: chess.Board) -> int:
    return sum(
        1
        for square, piece in board.piece_map().items()
        if piece.piece_type in {chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT}
        and board.attackers(not piece.color, square)
    )


def is_forcing_move(board: chess.Board, move: chess.Move) -> bool:
    return board.is_capture(move) or board.gives_check(move) or move.promotion is not None


def score_to_white_cp(score: Optional[chess.engine.PovScore], mate_score: int = 100_000) -> Optional[int]:
    if score is None:
        return None
    return score.white().score(mate_score=mate_score)


def analyse_position(
    engine: Any,
    board: chess.Board,
    *,
    limit: chess.engine.Limit,
    multipv: int,
    cache: dict[str, EnginePositionInfo],
) -> EnginePositionInfo:
    fen = board.fen()
    cached = cache.get(fen)
    if cached is not None:
        return cached

    legal_count = board.legal_moves.count()
    if legal_count == 0:
        info = EnginePositionInfo(None, [], 0.0, 0.0, 0.0, False, 0)
        cache[fen] = info
        return info

    raw_info = engine.analyse(board, limit, multipv=min(multipv, max(1, legal_count)))
    raw_infos = [raw_info] if isinstance(raw_info, dict) else list(raw_info)

    top_moves: list[EngineMoveInfo] = []
    for item in raw_infos:
        pv = item.get("pv") or []
        top_moves.append(
            EngineMoveInfo(
                move_uci=pv[0].uci() if pv else None,
                eval_cp=score_to_white_cp(item.get("score")),
                line_uci=[move.uci() for move in pv],
            )
        )
    top_moves = [move for move in top_moves if move.move_uci is not None]

    best_gain = compute_best_move_cp_gain(board, top_moves)
    volatility = compute_eval_volatility(top_moves)
    low_gap = compute_low_gap_between_top_moves(top_moves)
    forcing_depth = compute_forcing_line_depth(board, top_moves[0].line_uci if top_moves else [])
    best_forcing = False
    if top_moves and top_moves[0].move_uci:
        best_move = chess.Move.from_uci(top_moves[0].move_uci)
        best_forcing = best_move in board.legal_moves and is_forcing_move(board, best_move)

    info = EnginePositionInfo(
        eval_cp=top_moves[0].eval_cp if top_moves else None,
        top_moves=top_moves,
        best_move_cp_gain=best_gain,
        eval_volatility=volatility,
        low_gap_between_top_moves=low_gap,
        best_move_is_forcing=best_forcing,
        forcing_line_depth=forcing_depth,
    )
    cache[fen] = info
    return info


def compute_best_move_cp_gain(board: chess.Board, top_moves: list[EngineMoveInfo]) -> float:
    if len(top_moves) < 2:
        return 0.0
    best = top_moves[0].eval_cp
    second = top_moves[1].eval_cp
    if best is None or second is None:
        return 0.0
    return float(max(0, best - second) if board.turn == chess.WHITE else max(0, second - best))


def compute_eval_volatility(top_moves: list[EngineMoveInfo]) -> float:
    values = [move.eval_cp for move in top_moves if move.eval_cp is not None]
    if len(values) < 2:
        return 0.0
    avg = sum(values) / len(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) / len(values))


def compute_low_gap_between_top_moves(top_moves: list[EngineMoveInfo]) -> float:
    if len(top_moves) < 2 or top_moves[0].eval_cp is None or top_moves[1].eval_cp is None:
        return 0.0
    gap = abs(top_moves[0].eval_cp - top_moves[1].eval_cp)
    return 1.0 / (1.0 + gap / 100.0)


def compute_forcing_line_depth(board: chess.Board, line_uci: list[str]) -> int:
    temp = board.copy()
    depth = 0
    for move_uci in line_uci:
        move = chess.Move.from_uci(move_uci)
        if move not in temp.legal_moves or not is_forcing_move(temp, move):
            break
        temp.push(move)
        depth += 1
    return depth


def is_tactical_position(board: chess.Board, engine_info: EnginePositionInfo) -> bool:
    return tactical_position_score(board, engine_info) >= 0.55


def tactical_position_score(board: chess.Board, engine_info: EnginePositionInfo) -> float:
    captures = legal_captures_count(board)
    checks = legal_checks_count(board)
    hanging = hanging_pieces_count(board)
    attacked_high_value = attacked_high_value_pieces_count(board)
    forcing_context = (
        checks > 0
        or hanging > 0
        or attacked_high_value > 0
        or engine_info.best_move_is_forcing
        or engine_info.best_move_cp_gain >= 90
    )

    score = 0.0
    if board.is_check():
        score += 0.25
    score += 0.18 * min(1.0, checks / 2)
    # Raw captures alone are noisy in opening books; require another danger signal
    # before they can materially lift the tactical score.
    if forcing_context:
        score += 0.14 * min(1.0, captures / 6)
    else:
        score += 0.04 * min(1.0, captures / 6)
    score += 0.16 * min(1.0, hanging / 2)
    score += 0.12 * min(1.0, attacked_high_value / 3)
    score += 0.15 if engine_info.best_move_is_forcing else 0.0
    score += 0.12 * min(1.0, engine_info.best_move_cp_gain / 220)
    score += 0.08 * min(1.0, engine_info.forcing_line_depth / 3)
    return clamp01(score)


def is_quiet_position(board: chess.Board, engine_info: EnginePositionInfo) -> bool:
    return quiet_position_score(board, engine_info) >= 0.60


def quiet_position_score(board: chess.Board, engine_info: EnginePositionInfo) -> float:
    tactical_score = tactical_position_score(board, engine_info)
    captures = legal_captures_count(board)
    checks = legal_checks_count(board)
    score = 0.0
    score += 0.35 * (1.0 - tactical_score)
    score += 0.2 * (1.0 - min(1.0, captures / 6))
    score += 0.15 * (1.0 - min(1.0, checks / 2))
    score += 0.15 * (1.0 - min(1.0, engine_info.eval_volatility / 220))
    score += 0.1 * (1.0 - min(1.0, engine_info.best_move_cp_gain / 180))
    score += 0.05 * engine_info.low_gap_between_top_moves
    if board.is_check():
        score *= 0.35
    return clamp01(score)


def isolated_pawns(board: chess.Board, color: chess.Color) -> int:
    pawns = board.pieces(chess.PAWN, color)
    files = {chess.square_file(square) for square in pawns}
    return sum(
        1
        for square in pawns
        if chess.square_file(square) - 1 not in files and chess.square_file(square) + 1 not in files
    )


def doubled_pawns(board: chess.Board, color: chess.Color) -> int:
    counts = [0] * 8
    for square in board.pieces(chess.PAWN, color):
        counts[chess.square_file(square)] += 1
    return sum(max(0, count - 1) for count in counts)


def passed_pawns(board: chess.Board, color: chess.Color) -> int:
    enemy = board.pieces(chess.PAWN, not color)
    total = 0
    for square in board.pieces(chess.PAWN, color):
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        blocked = False
        for enemy_square in enemy:
            enemy_file = chess.square_file(enemy_square)
            enemy_rank = chess.square_rank(enemy_square)
            if abs(enemy_file - file) <= 1:
                if color == chess.WHITE and enemy_rank > rank:
                    blocked = True
                if color == chess.BLACK and enemy_rank < rank:
                    blocked = True
        if not blocked:
            total += 1
    return total


def pawn_islands(board: chess.Board, color: chess.Color) -> int:
    files = sorted({chess.square_file(square) for square in board.pieces(chess.PAWN, color)})
    if not files:
        return 0
    islands = 1
    for previous, current in zip(files, files[1:]):
        if current != previous + 1:
            islands += 1
    return islands


def open_files(board: chess.Board) -> int:
    return sum(
        1
        for file in range(8)
        if not any(chess.square_file(square) == file for square in board.pieces(chess.PAWN, chess.WHITE))
        and not any(chess.square_file(square) == file for square in board.pieces(chess.PAWN, chess.BLACK))
    )


def semi_open_files(board: chess.Board, color: chess.Color) -> int:
    friendly_files = {chess.square_file(square) for square in board.pieces(chess.PAWN, color)}
    enemy_files = {chess.square_file(square) for square in board.pieces(chess.PAWN, not color)}
    return sum(1 for file in range(8) if file not in friendly_files and file in enemy_files)


def center_state_scores(board: chess.Board) -> tuple[float, float]:
    central_files = {3, 4}
    central_pawns = [
        square
        for color in [chess.WHITE, chess.BLACK]
        for square in board.pieces(chess.PAWN, color)
        if chess.square_file(square) in central_files
    ]
    locked = 0
    for square in central_pawns:
        color = board.color_at(square)
        if color is None:
            continue
        direction = 8 if color == chess.WHITE else -8
        front = square + direction
        if 0 <= front < 64 and board.piece_at(front) and board.piece_at(front).piece_type == chess.PAWN:
            locked += 1
    open_center = 1.0 if not central_pawns else max(0.0, 1.0 - len(central_pawns) / 4.0)
    closed_center = min(1.0, locked / 2.0)
    return open_center, closed_center


def pawn_structure_sharpness(board: chess.Board) -> float:
    weak_pawns = (
        isolated_pawns(board, chess.WHITE)
        + isolated_pawns(board, chess.BLACK)
        + doubled_pawns(board, chess.WHITE)
        + doubled_pawns(board, chess.BLACK)
        + passed_pawns(board, chess.WHITE)
        + passed_pawns(board, chess.BLACK)
    )
    open_center_score, closed_center_score = center_state_scores(board)
    files_score = (open_files(board) + semi_open_files(board, chess.WHITE) + semi_open_files(board, chess.BLACK)) / 16
    islands_score = (pawn_islands(board, chess.WHITE) + pawn_islands(board, chess.BLACK)) / 8
    return clamp01(0.35 * min(1.0, weak_pawns / 8) + 0.25 * max(open_center_score, closed_center_score) + 0.2 * files_score + 0.2 * islands_score)


def pawn_structure_signature(board: chess.Board) -> str:
    open_center_score, closed_center_score = center_state_scores(board)
    return "|".join(
        str(value)
        for value in [
            isolated_pawns(board, chess.WHITE),
            isolated_pawns(board, chess.BLACK),
            doubled_pawns(board, chess.WHITE),
            doubled_pawns(board, chess.BLACK),
            passed_pawns(board, chess.WHITE),
            passed_pawns(board, chess.BLACK),
            pawn_islands(board, chess.WHITE),
            pawn_islands(board, chess.BLACK),
            open_files(board),
            semi_open_files(board, chess.WHITE),
            semi_open_files(board, chess.BLACK),
            round(open_center_score),
            round(closed_center_score),
        ]
    )


def material_imbalance_score(
    board: chess.Board,
    engine_info: Optional[EnginePositionInfo] = None,
) -> float:
    return clamp01(
        0.65 * realized_material_imbalance_score(board)
        + 0.35 * material_imbalance_potential(board, engine_info)
    )


def realized_material_imbalance_score(board: chess.Board) -> float:
    values = {
        chess.KNIGHT: 3,
        chess.BISHOP: 3,
        chess.ROOK: 5,
        chess.QUEEN: 9,
    }
    material = {
        color: sum(values[piece] * len(board.pieces(piece, color)) for piece in values)
        for color in [chess.WHITE, chess.BLACK]
    }
    material_diff = abs(material[chess.WHITE] - material[chess.BLACK]) / 10
    bishop_pair = abs(
        int(len(board.pieces(chess.BISHOP, chess.WHITE)) >= 2)
        - int(len(board.pieces(chess.BISHOP, chess.BLACK)) >= 2)
    )
    minor_diff = abs(
        len(board.pieces(chess.KNIGHT, chess.WHITE))
        + len(board.pieces(chess.BISHOP, chess.WHITE))
        - len(board.pieces(chess.KNIGHT, chess.BLACK))
        - len(board.pieces(chess.BISHOP, chess.BLACK))
    ) / 4
    rook_diff = abs(len(board.pieces(chess.ROOK, chess.WHITE)) - len(board.pieces(chess.ROOK, chess.BLACK))) / 2
    queen_trade = 1.0 if len(board.pieces(chess.QUEEN, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.BLACK)) < 2 else 0.0
    return clamp01(0.35 * material_diff + 0.2 * bishop_pair + 0.2 * minor_diff + 0.15 * rook_diff + 0.1 * queen_trade)


def material_imbalance_potential(
    board: chess.Board,
    engine_info: Optional[EnginePositionInfo],
) -> float:
    white_bishops = len(board.pieces(chess.BISHOP, chess.WHITE))
    black_bishops = len(board.pieces(chess.BISHOP, chess.BLACK))
    white_knights = len(board.pieces(chess.KNIGHT, chess.WHITE))
    black_knights = len(board.pieces(chess.KNIGHT, chess.BLACK))
    white_pawns = len(board.pieces(chess.PAWN, chess.WHITE))
    black_pawns = len(board.pieces(chess.PAWN, chess.BLACK))

    bishop_pair_vs_not = abs(int(white_bishops >= 2) - int(black_bishops >= 2))
    minor_mix_asymmetry = min(1.0, abs((white_bishops - white_knights) - (black_bishops - black_knights)) / 4)
    pawn_gambit = min(1.0, abs(white_pawns - black_pawns) / 2)
    exchange_shape = min(
        1.0,
        abs(len(board.pieces(chess.ROOK, chess.WHITE)) - len(board.pieces(chess.ROOK, chess.BLACK)))
        + abs(len(board.pieces(chess.QUEEN, chess.WHITE)) - len(board.pieces(chess.QUEEN, chess.BLACK))),
    )

    pv_exchange_motif = 0.0
    if engine_info is not None and engine_info.top_moves:
        pv_exchange_motif = max(
            pv_material_asymmetry_after_prefix(board, move.line_uci)
            for move in engine_info.top_moves
        )

    return clamp01(
        0.3 * bishop_pair_vs_not
        + 0.25 * minor_mix_asymmetry
        + 0.2 * pawn_gambit
        + 0.1 * exchange_shape
        + 0.15 * pv_exchange_motif
    )


def pv_material_asymmetry_after_prefix(board: chess.Board, line_uci: list[str]) -> float:
    temp = board.copy()
    forcing_moves = 0
    for move_uci in line_uci[:4]:
        move = chess.Move.from_uci(move_uci)
        if move not in temp.legal_moves:
            break
        if not is_forcing_move(temp, move):
            break
        forcing_moves += 1
        temp.push(move)

    if forcing_moves == 0:
        return 0.0

    return max(
        realized_material_imbalance_score(temp),
        min(1.0, abs(len(temp.pieces(chess.PAWN, chess.WHITE)) - len(temp.pieces(chess.PAWN, chess.BLACK))) / 2),
    )


def king_square(board: chess.Board, color: chess.Color) -> Optional[int]:
    return board.king(color)


def castling_side(square: Optional[int]) -> Optional[str]:
    if square is None:
        return None
    file = chess.square_file(square)
    if file <= 2:
        return "queen"
    if file >= 6:
        return "king"
    return None


def castling_path_squares(color: chess.Color, side: str) -> list[int]:
    if color == chess.WHITE and side == "king":
        return [chess.F1, chess.G1]
    if color == chess.WHITE and side == "queen":
        return [chess.D1, chess.C1, chess.B1]
    if color == chess.BLACK and side == "king":
        return [chess.F8, chess.G8]
    return [chess.D8, chess.C8, chess.B8]


def castling_right_for_side(board: chess.Board, color: chess.Color, side: str) -> bool:
    if color == chess.WHITE and side == "king":
        return board.has_kingside_castling_rights(chess.WHITE)
    if color == chess.WHITE and side == "queen":
        return board.has_queenside_castling_rights(chess.WHITE)
    if color == chess.BLACK and side == "king":
        return board.has_kingside_castling_rights(chess.BLACK)
    return board.has_queenside_castling_rights(chess.BLACK)


def pawn_shield_score(board: chess.Board, color: chess.Color, side: str) -> float:
    files = [5, 6, 7] if side == "king" else [0, 1, 2]
    home_ranks = [1, 2] if color == chess.WHITE else [6, 5]
    present = 0
    for file in files:
        for rank in home_ranks:
            piece = board.piece_at(chess.square(file, rank))
            if piece is not None and piece.color == color and piece.piece_type == chess.PAWN:
                present += 1
                break
    return present / len(files)


def flank_pawn_storm_score(board: chess.Board, color: chess.Color, side: str) -> float:
    files = [5, 6, 7] if side == "king" else [0, 1, 2]
    enemy = not color
    advanced = 0
    for square in board.pieces(chess.PAWN, enemy):
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        if file not in files:
            continue
        if enemy == chess.WHITE and rank >= 4:
            advanced += 1
        if enemy == chess.BLACK and rank <= 3:
            advanced += 1
    return min(1.0, advanced / 3)


def castling_side_potential(board: chess.Board, color: chess.Color) -> dict[str, float]:
    king = board.king(color)
    current_side = castling_side(king)
    if current_side is not None:
        return {"king": 1.0 if current_side == "king" else 0.0, "queen": 1.0 if current_side == "queen" else 0.0}

    scores: dict[str, float] = {}
    for side in ["king", "queen"]:
        if not castling_right_for_side(board, color, side):
            scores[side] = 0.0
            continue
        path = castling_path_squares(color, side)
        clear_count = sum(1 for square in path if board.piece_at(square) is None)
        clear_score = clear_count / len(path)
        shield = pawn_shield_score(board, color, side)
        storm_penalty = flank_pawn_storm_score(board, color, side)
        scores[side] = clamp01(0.45 + 0.3 * clear_score + 0.2 * shield - 0.2 * storm_penalty)
    return scores


def castling_opportunity_score(board: chess.Board, color: chess.Color) -> float:
    potentials = castling_side_potential(board, color)
    return max(potentials.values()) if potentials else 0.0


def preferred_castling_side(board: chess.Board, color: chess.Color) -> Optional[str]:
    potentials = castling_side_potential(board, color)
    if not potentials:
        return None
    side, score = max(potentials.items(), key=lambda item: item[1])
    return side if score >= 0.35 else None


def king_safety_risk_for_color(board: chess.Board, color: chess.Color, move_number: int, castled: bool) -> float:
    return king_safety_context_score(
        board=board,
        color=color,
        move_number=move_number,
        castled=castled,
        castle_opportunity=castling_opportunity_score(board, color),
    )


def king_safety_context_score(
    *,
    board: chess.Board,
    color: chess.Color,
    move_number: int,
    castled: bool,
    castle_opportunity: float,
) -> float:
    king = king_square(board, color)
    if king is None:
        return 1.0

    risk = 0.0
    king_file = chess.square_file(king)
    king_rank = chess.square_rank(king)
    home_rank = 0 if color == chess.WHITE else 7

    if not castled and move_number >= 8 and king_file == 4 and king_rank == home_rank:
        risk += 0.18 * (1.0 - castle_opportunity)
    if not castled and move_number >= 10 and king_file == 4 and king_rank == home_rank:
        risk += 0.18
    if not castled and move_number >= 15 and king_file == 4 and king_rank == home_rank:
        risk += 0.22
    if not castled and not board.has_castling_rights(color):
        risk += 0.25

    if not castled and move_number < 8 and castle_opportunity >= 0.55:
        risk -= 0.08

    adjacent_files = [file for file in [king_file - 1, king_file, king_file + 1] if 0 <= file < 8]
    friendly_pawn_files = {chess.square_file(square) for square in board.pieces(chess.PAWN, color)}
    enemy_pawn_files = {chess.square_file(square) for square in board.pieces(chess.PAWN, not color)}
    for file in adjacent_files:
        if file not in friendly_pawn_files:
            risk += 0.06 if file in enemy_pawn_files else 0.10

    attackers = 0
    for delta_file in [-1, 0, 1]:
        for delta_rank in [-1, 0, 1]:
            file = king_file + delta_file
            rank = king_rank + delta_rank
            if 0 <= file < 8 and 0 <= rank < 8:
                attackers += len(board.attackers(not color, chess.square(file, rank)))
    risk += min(0.25, attackers * 0.03)

    king_side = castling_side(king) or preferred_castling_side(board, color) or "king"
    risk += 0.12 * flank_pawn_storm_score(board, color, king_side)
    risk -= 0.08 * pawn_shield_score(board, color, king_side)

    if castled:
        floor = 0.0
    elif move_number < 8:
        floor = 0.015 + 0.04 * (1.0 - castle_opportunity)
    else:
        floor = 0.04 + 0.1 * (1.0 - castle_opportunity)

    return clamp01(max(risk, floor))


def detect_castling_stats(boards: list[chess.Board], moves: list[chess.Move]) -> tuple[float, float, dict[chess.Color, bool], dict[chess.Color, Optional[str]]]:
    castle_move_number: dict[chess.Color, Optional[int]] = {chess.WHITE: None, chess.BLACK: None}
    castle_side: dict[chess.Color, Optional[str]] = {chess.WHITE: None, chess.BLACK: None}

    for board, move in zip(boards, moves):
        color = board.turn
        if board.is_castling(move):
            move_number = board.fullmove_number
            castle_move_number[color] = move_number
            temp = board.copy()
            temp.push(move)
            castle_side[color] = castling_side(temp.king(color))

    final_board = boards[-1] if boards else chess.Board()
    early_values = []
    for color in [chess.WHITE, chess.BLACK]:
        if castle_move_number[color] is not None:
            early_values.append(1.0 if castle_move_number[color] <= 10 else 0.65)
        elif final_board.fullmove_number < 8:
            early_values.append(0.65 * castling_opportunity_score(final_board, color))
        else:
            early_values.append(0.35 * castling_opportunity_score(final_board, color))
    early_castling = mean(early_values)
    both_castled = castle_side[chess.WHITE] is not None and castle_side[chess.BLACK] is not None
    if both_castled:
        opposite = 1.0 if castle_side[chess.WHITE] != castle_side[chess.BLACK] else 0.0
    else:
        white_side = castle_side[chess.WHITE] or preferred_castling_side(final_board, chess.WHITE)
        black_side = castle_side[chess.BLACK] or preferred_castling_side(final_board, chess.BLACK)
        if white_side is None or black_side is None:
            opposite = 0.0
        elif white_side != black_side:
            white_strength = castling_side_potential(final_board, chess.WHITE).get(white_side, 0.0)
            black_strength = castling_side_potential(final_board, chess.BLACK).get(black_side, 0.0)
            opposite = 0.55 * min(white_strength, black_strength)
        else:
            opposite = 0.0
    return early_castling, opposite, {color: castle_move_number[color] is not None for color in [chess.WHITE, chess.BLACK]}, castle_side


def is_endgame(board: chess.Board) -> bool:
    queens = len(board.pieces(chess.QUEEN, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.BLACK))
    non_pawn_material = 0
    values = {chess.KNIGHT: 300, chess.BISHOP: 300, chess.ROOK: 500, chess.QUEEN: 900}
    for piece, value in values.items():
        non_pawn_material += value * (len(board.pieces(piece, chess.WHITE)) + len(board.pieces(piece, chess.BLACK)))
    return non_pawn_material <= 2600 or (queens == 0 and non_pawn_material <= 3600)


def piece_exchange_score(board: chess.Board) -> float:
    starting_non_pawns = 16
    current = sum(
        len(board.pieces(piece, color))
        for piece in [chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]
        for color in [chess.WHITE, chess.BLACK]
    )
    return clamp01((starting_non_pawns - current) / starting_non_pawns)


def symmetry_score(board: chess.Board) -> float:
    white_files = sorted(chess.square_file(square) for square in board.pieces(chess.PAWN, chess.WHITE))
    black_files = sorted(chess.square_file(square) for square in board.pieces(chess.PAWN, chess.BLACK))
    shared = sum(1 for file in range(8) if file in white_files and file in black_files)
    count_diff = abs(len(white_files) - len(black_files))
    return clamp01((shared / 8) * (1 - count_diff / 8))


def endgame_likelihood_proxy(board: chess.Board, tactical_density: float, king_safety_risk: float, eval_volatility: float) -> float:
    queens = len(board.pieces(chess.QUEEN, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.BLACK))
    queen_trade = 1.0 if queens == 0 else 0.0
    low_tactics = 1.0 - tactical_density
    low_king_attack = 1.0 - king_safety_risk
    stable_eval = 1.0 - clamp01(eval_volatility / 300)
    low_pawn_weakness = 1.0 - pawn_structure_sharpness(board)
    return clamp01(
        0.2 * queen_trade
        + 0.2 * piece_exchange_score(board)
        + 0.18 * symmetry_score(board)
        + 0.17 * low_tactics
        + 0.15 * low_king_attack
        + 0.05 * stable_eval
        + 0.05 * low_pawn_weakness
    )


def position_complexity(board: chess.Board, engine_info: EnginePositionInfo) -> float:
    tactical_options = legal_captures_count(board) + legal_checks_count(board)
    king_risk_white = king_safety_risk_for_color(board, chess.WHITE, board.fullmove_number, False)
    king_risk_black = king_safety_risk_for_color(board, chess.BLACK, board.fullmove_number, False)
    return clamp01(
        0.2 * min(1.0, board.legal_moves.count() / 60)
        + 0.18 * min(1.0, engine_info.eval_volatility / 300)
        + 0.18 * min(1.0, tactical_options / 12)
        + 0.16 * material_imbalance_score(board, engine_info)
        + 0.14 * pawn_structure_sharpness(board)
        + 0.08 * abs(king_risk_white - king_risk_black)
        + 0.06 * engine_info.low_gap_between_top_moves
    )


def compute_line_features(
    line: OpeningLine,
    engine: Any,
    *,
    limit: chess.engine.Limit,
    multipv: int = 3,
    cache: Optional[dict[str, EnginePositionInfo]] = None,
) -> LineFeatureVector:
    if cache is None:
        cache = {}
    boards, moves = replay_boards(line.uci)
    position_infos = [
        analyse_position(engine, board, limit=limit, multipv=multipv, cache=cache)
        for board in boards
    ]

    tactical_density = mean(tactical_position_score(board, info) for board, info in zip(boards, position_infos))
    quiet_density = mean(quiet_position_score(board, info) for board, info in zip(boards, position_infos))

    early_castling, opposite_castling, castled, _castle_sides = detect_castling_stats(boards, moves)
    final_board = boards[-1]
    final_move_number = final_board.fullmove_number
    king_risk = mean(
        [
            king_safety_risk_for_color(final_board, chess.WHITE, final_move_number, castled[chess.WHITE]),
            king_safety_risk_for_color(final_board, chess.BLACK, final_move_number, castled[chess.BLACK]),
        ]
    )

    complexity_boards = boards[-4:] if len(boards) >= 4 else boards
    complexity_infos = position_infos[-len(complexity_boards):]
    complexity = mean(position_complexity(board, info) for board, info in zip(complexity_boards, complexity_infos))
    final_eval_volatility = position_infos[-1].eval_volatility if position_infos else 0.0

    return LineFeatureVector(
        opening_name=line.name,
        eco=line.eco,
        pgn=line.pgn,
        uci=line.uci,
        tactical_density=round_float(tactical_density),
        quiet_position_density=round_float(quiet_density),
        king_safety_risk=round_float(king_risk),
        early_castling_tendency=round_float(early_castling),
        opposite_side_castling_tendency=round_float(opposite_castling),
        middlegame_complexity=round_float(complexity),
        pawn_structure_sharpness=round_float(pawn_structure_sharpness(final_board)),
        material_imbalance=round_float(material_imbalance_score(final_board, position_infos[-1] if position_infos else None)),
        endgame_likelihood_proxy=round_float(endgame_likelihood_proxy(final_board, tactical_density, king_risk, final_eval_volatility)),
        structure_signature=pawn_structure_signature(final_board),
    )


def aggregate_line_features(features: Iterable[LineFeatureVector], *, opening_name: Optional[str] = None) -> OpeningGroupFeatureVector:
    items = list(features)
    if not items:
        raise ValueError("Cannot aggregate an empty feature list")
    name = opening_name or items[0].opening_name
    signatures = [item.structure_signature for item in items]
    return OpeningGroupFeatureVector(
        opening_name=name,
        line_count=len(items),
        eco_values=";".join(sorted({item.eco for item in items})),
        representative_pgn=max(items, key=lambda item: len(item.uci.split())).pgn,
        representative_uci=max(items, key=lambda item: len(item.uci.split())).uci,
        tactical_density=avg_attr(items, "tactical_density"),
        quiet_position_density=avg_attr(items, "quiet_position_density"),
        king_safety_risk=avg_attr(items, "king_safety_risk"),
        early_castling_tendency=avg_attr(items, "early_castling_tendency"),
        opposite_side_castling_tendency=avg_attr(items, "opposite_side_castling_tendency"),
        middlegame_complexity=avg_attr(items, "middlegame_complexity"),
        pawn_structure_sharpness=avg_attr(items, "pawn_structure_sharpness"),
        material_imbalance=avg_attr(items, "material_imbalance"),
        endgame_likelihood_proxy=avg_attr(items, "endgame_likelihood_proxy"),
        structure_diversity=round_float(signature_entropy(signatures)),
    )


def aggregate_by_normalized_name(features: Iterable[LineFeatureVector]) -> list[OpeningGroupFeatureVector]:
    groups: dict[str, list[LineFeatureVector]] = {}
    names: dict[str, str] = {}
    for feature in features:
        family = opening_family_name(feature.opening_name, feature.eco)
        key = normalize_opening_name(family)
        groups.setdefault(key, []).append(feature)
        names.setdefault(key, family)
    return [
        aggregate_line_features(groups[key], opening_name=names[key])
        for key in sorted(groups, key=lambda value: names[value])
    ]


def compute_opening_groups(
    lines: list[OpeningLine],
    *,
    stockfish_path: str = DEFAULT_STOCKFISH_PATH,
    engine_depth: int = 10,
    multipv: int = 3,
    max_lines_per_group: Optional[int] = None,
    show_progress: bool = True,
) -> tuple[list[OpeningGroupFeatureVector], list[LineFeatureVector]]:
    selected = cap_lines_per_group(lines, max_lines_per_group)
    cache: dict[str, EnginePositionInfo] = {}
    limit = chess.engine.Limit(depth=engine_depth)
    with chess.engine.SimpleEngine.popen_uci(stockfish_path) as engine:
        line_features = [
            compute_line_features(line, engine, limit=limit, multipv=multipv, cache=cache)
            for line in progress_iter(selected, desc="Analyzing opening lines", enabled=show_progress)
        ]
    return aggregate_by_normalized_name(line_features), line_features


def cap_lines_per_group(lines: list[OpeningLine], max_lines_per_group: Optional[int]) -> list[OpeningLine]:
    if max_lines_per_group is None or max_lines_per_group <= 0:
        return lines
    counts: dict[str, int] = {}
    selected: list[OpeningLine] = []
    for line in lines:
        key = normalize_opening_name(opening_family_name(line.name, line.eco))
        if counts.get(key, 0) >= max_lines_per_group:
            continue
        selected.append(line)
        counts[key] = counts.get(key, 0) + 1
    return selected


def write_group_features(path: str | Path, groups: list[OpeningGroupFeatureVector]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "opening_name",
        "line_count",
        "eco_values",
        "representative_pgn",
        "representative_uci",
        *VECTOR_COLUMNS,
    ]
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for group in groups:
            row = {column: getattr(group, column) for column in columns}
            writer.writerow(row)


def load_gt_rows(testset_path: str | Path) -> list[dict[str, str]]:
    with Path(testset_path).open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def parse_eco_range(value: str) -> set[str]:
    ecos: set[str] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" not in part:
            ecos.add(part)
            continue
        start, end = [chunk.strip() for chunk in part.split("-", 1)]
        if len(start) != 3 or len(end) != 3 or start[0] != end[0]:
            continue
        prefix = start[0]
        for number in range(int(start[1:]), int(end[1:]) + 1):
            ecos.add(f"{prefix}{number:02d}")
    return ecos


def match_lines_for_gt_row(lines: list[OpeningLine], row: dict[str, str]) -> list[OpeningLine]:
    ecos = parse_eco_range(row.get("eco", ""))
    alias_prefix = opening_alias_prefix(row.get("opening_name", ""))
    alias_prefix_ascii = normalize_opening_name(ascii_fold(alias_prefix))

    matches = []
    for line in lines:
        line_name = normalize_opening_name(ascii_fold(line.name))
        eco_match = not ecos or line.eco in ecos
        name_match = line_name == alias_prefix_ascii or line_name.startswith(alias_prefix_ascii + " ")
        if eco_match and name_match:
            matches.append(line)

    if matches:
        return matches

    # Some broad GT rows use family names whose dataset names are best selected by ECO.
    return [line for line in lines if not ecos or line.eco in ecos]


def compute_gt_groups(
    lines: list[OpeningLine],
    gt_rows: list[dict[str, str]],
    *,
    stockfish_path: str = DEFAULT_STOCKFISH_PATH,
    engine_depth: int = 10,
    multipv: int = 3,
    max_lines_per_group: Optional[int] = None,
    show_progress: bool = True,
) -> list[OpeningGroupFeatureVector]:
    cache: dict[str, EnginePositionInfo] = {}
    limit = chess.engine.Limit(depth=engine_depth)
    groups: list[OpeningGroupFeatureVector] = []
    with chess.engine.SimpleEngine.popen_uci(stockfish_path) as engine:
        for row in progress_iter(gt_rows, desc="Validating GT openings", enabled=show_progress):
            matched = match_lines_for_gt_row(lines, row)
            matched = cap_lines_per_gt_row(matched, max_lines_per_group)
            if not matched:
                raise ValueError(f"No opening lines matched GT row {row.get('opening_name')}")
            features = [
                compute_line_features(line, engine, limit=limit, multipv=multipv, cache=cache)
                for line in progress_iter(
                    matched,
                    desc=f"  {row['opening_name']}",
                    leave=False,
                    enabled=show_progress,
                )
            ]
            groups.append(aggregate_line_features(features, opening_name=row["opening_name"]))
    return groups


def cap_lines_per_gt_row(lines: list[OpeningLine], max_lines_per_group: Optional[int]) -> list[OpeningLine]:
    if max_lines_per_group is None or max_lines_per_group <= 0:
        return lines
    return lines[:max_lines_per_group]


def gt_vector(row: dict[str, str]) -> list[float]:
    return [float(row[column]) for column in VECTOR_COLUMNS]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def similarity_matrix(gt_rows: list[dict[str, str]], computed_groups: list[OpeningGroupFeatureVector]) -> list[list[float]]:
    return [
        [round_float(cosine_similarity(gt_vector(row), group.vector())) for group in computed_groups]
        for row in gt_rows
    ]


def write_similarity_matrix(
    path: str | Path,
    gt_rows: list[dict[str, str]],
    computed_groups: list[OpeningGroupFeatureVector],
    matrix: list[list[float]],
) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    columns = ["gt_opening", *[group.opening_name for group in computed_groups]]
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(columns)
        for row, scores in zip(gt_rows, matrix):
            writer.writerow([row["opening_name"], *scores])


def diagonal_report(gt_rows: list[dict[str, str]], matrix: list[list[float]]) -> list[str]:
    report: list[str] = []
    for idx, scores in enumerate(matrix):
        if not scores:
            report.append(f"{gt_rows[idx]['opening_name']}: no similarity scores")
            continue
        best_idx = max(range(len(scores)), key=lambda item: scores[item])
        status = "PASS" if best_idx == idx else "FAIL"
        report.append(
            f"{status}: {gt_rows[idx]['opening_name']} diagonal={scores[idx]:.4f} "
            f"best_col={best_idx} best={scores[best_idx]:.4f}"
        )
    return report


def diagonal_failures(gt_rows: list[dict[str, str]], matrix: list[list[float]]) -> list[str]:
    failures: list[str] = []
    for idx, scores in enumerate(matrix):
        if not scores:
            failures.append(f"{gt_rows[idx]['opening_name']}: no similarity scores")
            continue
        best_idx = max(range(len(scores)), key=lambda item: scores[item])
        if best_idx != idx:
            failures.append(
                f"{gt_rows[idx]['opening_name']}: diagonal={scores[idx]:.4f}, "
                f"best_col={best_idx}, best={scores[best_idx]:.4f}"
            )
    return failures


def mean_bool(values: Iterable[bool]) -> float:
    items = list(values)
    if not items:
        return 0.0
    return sum(1.0 for value in items if value) / len(items)


def progress_iter(
    iterable: Iterable[Any],
    *,
    desc: str,
    leave: bool = True,
    enabled: bool = True,
) -> Iterable[Any]:
    if not enabled or tqdm is None:
        return iterable
    return tqdm(iterable, desc=desc, leave=leave)


def avg_attr(items: list[Any], attr: str) -> float:
    return round_float(sum(float(getattr(item, attr)) for item in items) / len(items))


def signature_entropy(signatures: list[str]) -> float:
    if len(signatures) <= 1:
        return 0.0
    counts: dict[str, int] = {}
    for signature in signatures:
        counts[signature] = counts.get(signature, 0) + 1
    entropy = 0.0
    total = len(signatures)
    for count in counts.values():
        probability = count / total
        entropy -= probability * math.log(probability)
    max_entropy = math.log(total)
    return clamp01(entropy / max_entropy) if max_entropy else 0.0


def round_float(value: float) -> float:
    return round(clamp01(value), 6)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
