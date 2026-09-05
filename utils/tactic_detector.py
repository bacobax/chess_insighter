from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import chess


PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 10_000,
}

ORTHOGONAL_DIRECTIONS = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIAGONAL_DIRECTIONS = ((1, 1), (1, -1), (-1, 1), (-1, -1))


@dataclass(frozen=True)
class TacticTag:
    theme: str
    move_uci: str
    ply_offset: int
    confidence: float
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TacticDetectorConfig:
    min_engine_gain_cp: int = 80


def detect_tactics(
    board: chess.Board,
    move: chess.Move,
    *,
    ply_offset: int = 0,
    engine_gain_cp: int | None = None,
    mate_in: int | None = None,
    is_pv_move: bool = False,
    config: TacticDetectorConfig | None = None,
) -> list[TacticTag]:
    """Detect tactical motifs created by a move.

    Plain checks are intentionally not motifs. Richer checking patterns and
    material motifs are emitted when the move belongs to an engine line or has
    enough engine value.
    """

    config = config or TacticDetectorConfig()
    if move not in board.legal_moves:
        return []

    tags: list[TacticTag] = []
    attacker = board.turn
    defender = not attacker
    move_uci = move.uci()
    gives_check = board.gives_check(move)

    after = board.copy(stack=False)
    after.push(move)

    checking_attackers = _checking_attackers(after, attacker, defender)
    if len(checking_attackers) >= 2:
        tags.append(
            TacticTag(
                theme="double_check",
                move_uci=move_uci,
                ply_offset=ply_offset,
                confidence=0.95,
                evidence={
                    "attackers": [_square_name(square) for square in checking_attackers],
                    "king_square": _square_name(after.king(defender)),
                },
            )
        )

    if gives_check and any(square != move.to_square for square in checking_attackers):
        tags.append(
            TacticTag(
                theme="discovered_check",
                move_uci=move_uci,
                ply_offset=ply_offset,
                confidence=0.9,
                evidence={
                    "checking_attackers": [
                        _square_name(square) for square in checking_attackers
                    ],
                    "moved_piece_square": chess.square_name(move.to_square),
                    "king_square": _square_name(after.king(defender)),
                },
            )
        )

    if mate_in is not None:
        tags.append(
            TacticTag(
                theme="checkmate_in_k",
                move_uci=move_uci,
                ply_offset=ply_offset,
                confidence=1.0,
                evidence={"k": int(abs(mate_in)), "king_square": _square_name(after.king(defender))},
            )
        )
    elif after.is_checkmate():
        tags.append(
            TacticTag(
                theme="checkmate_in_k",
                move_uci=move_uci,
                ply_offset=ply_offset,
                confidence=1.0,
                evidence={"k": 1, "king_square": _square_name(after.king(defender))},
            )
        )

    if after.is_checkmate():
        return _dedupe_tags(tags)

    if not _allow_nontrivial(engine_gain_cp, is_pv_move, config):
        return tags

    fork_targets = _fork_targets(after, move.to_square, attacker, defender)
    if len(fork_targets) >= 2:
        tags.append(
            TacticTag(
                theme="fork",
                move_uci=move_uci,
                ply_offset=ply_offset,
                confidence=0.85,
                evidence={"targets": fork_targets},
            )
        )

    pins = _absolute_pins_created_by_moved_piece(after, move.to_square, attacker, defender)
    for pin in pins:
        tags.append(
            TacticTag(
                theme="absolute_pin",
                move_uci=move_uci,
                ply_offset=ply_offset,
                confidence=0.9,
                evidence=pin,
            )
        )

    skewer = _skewer_created_by_moved_piece(after, move.to_square, attacker, defender)
    if skewer is not None:
        tags.append(
            TacticTag(
                theme="skewer",
                move_uci=move_uci,
                ply_offset=ply_offset,
                confidence=0.85,
                evidence=skewer,
            )
        )

    if _is_king_attraction(after, move, attacker, defender, engine_gain_cp, mate_in):
        tags.append(
            TacticTag(
                theme="king_attraction",
                move_uci=move_uci,
                ply_offset=ply_offset,
                confidence=0.75,
                evidence={
                    "king_square": _square_name(after.king(defender)),
                    "attraction_square": chess.square_name(move.to_square),
                    "engine_gain_cp": engine_gain_cp,
                    "mate_in": mate_in,
                },
            )
        )

    return _dedupe_tags(tags)


def _allow_nontrivial(
    engine_gain_cp: int | None,
    is_pv_move: bool,
    config: TacticDetectorConfig,
) -> bool:
    return is_pv_move or (
        engine_gain_cp is not None and abs(engine_gain_cp) >= config.min_engine_gain_cp
    )


def _checking_attackers(
    board: chess.Board,
    attacker: chess.Color,
    defender: chess.Color,
) -> list[chess.Square]:
    king = board.king(defender)
    if king is None:
        return []
    return list(board.attackers(attacker, king))


def _fork_targets(
    board: chess.Board,
    moved_square: chess.Square,
    attacker: chess.Color,
    defender: chess.Color,
) -> list[dict[str, Any]]:
    moved_piece = board.piece_at(moved_square)
    if moved_piece is None or moved_piece.color != attacker:
        return []

    targets: list[dict[str, Any]] = []
    for target_square in board.attacks(moved_square):
        piece = board.piece_at(target_square)
        if piece is None or piece.color != defender:
            continue
        if piece.piece_type not in {chess.KING, chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT}:
            continue
        targets.append(
            {
                "square": chess.square_name(target_square),
                "piece": chess.piece_name(piece.piece_type),
                "value": PIECE_VALUES[piece.piece_type],
            }
        )

    valuable = [target for target in targets if target["value"] >= PIECE_VALUES[chess.KNIGHT]]
    has_major_target = any(target["piece"] in {"king", "queen", "rook"} for target in targets)
    if len(valuable) >= 2 and has_major_target:
        return targets
    return []


def _absolute_pins_created_by_moved_piece(
    board: chess.Board,
    pinner_square: chess.Square,
    attacker: chess.Color,
    defender: chess.Color,
) -> list[dict[str, Any]]:
    pinner = board.piece_at(pinner_square)
    if pinner is None or pinner.color != attacker:
        return []
    if pinner.piece_type not in {chess.BISHOP, chess.ROOK, chess.QUEEN}:
        return []

    king = board.king(defender)
    if king is None:
        return []

    pins: list[dict[str, Any]] = []
    for direction in _directions_for_slider(pinner.piece_type):
        ray = _ray_from(king, direction)
        first_piece_square: chess.Square | None = None
        for square in ray:
            piece = board.piece_at(square)
            if piece is None:
                continue
            if first_piece_square is None:
                if piece.color == defender and square != king:
                    first_piece_square = square
                    continue
                break
            if square == pinner_square:
                pinned = board.piece_at(first_piece_square)
                if pinned is not None and board.is_pinned(defender, first_piece_square):
                    pins.append(
                        {
                            "pinned_square": chess.square_name(first_piece_square),
                            "pinned_piece": chess.piece_name(pinned.piece_type),
                            "king_square": chess.square_name(king),
                            "pinner_square": chess.square_name(pinner_square),
                        }
                    )
                break
            if piece is not None:
                break
    return pins


def _skewer_created_by_moved_piece(
    board: chess.Board,
    moved_square: chess.Square,
    attacker: chess.Color,
    defender: chess.Color,
) -> dict[str, Any] | None:
    moved_piece = board.piece_at(moved_square)
    if moved_piece is None or moved_piece.color != attacker:
        return None
    if moved_piece.piece_type not in {chess.BISHOP, chess.ROOK, chess.QUEEN}:
        return None

    for direction in _directions_for_slider(moved_piece.piece_type):
        occupied: list[chess.Square] = []
        for square in _ray_from(moved_square, direction):
            if board.piece_at(square) is not None:
                occupied.append(square)
                if len(occupied) == 2:
                    break
        if len(occupied) < 2:
            continue

        first = board.piece_at(occupied[0])
        second = board.piece_at(occupied[1])
        if first is None or second is None:
            continue
        if first.color != defender or second.color != defender:
            continue

        first_value = PIECE_VALUES[first.piece_type]
        second_value = PIECE_VALUES[second.piece_type]
        if first_value > second_value and first_value >= PIECE_VALUES[chess.ROOK]:
            return {
                "front_square": chess.square_name(occupied[0]),
                "front_piece": chess.piece_name(first.piece_type),
                "rear_square": chess.square_name(occupied[1]),
                "rear_piece": chess.piece_name(second.piece_type),
            }
    return None


def _is_king_attraction(
    board_after: chess.Board,
    move: chess.Move,
    attacker: chess.Color,
    defender: chess.Color,
    engine_gain_cp: int | None,
    mate_in: int | None,
) -> bool:
    if mate_in is None and (engine_gain_cp is None or abs(engine_gain_cp) < 80):
        return False

    king = board_after.king(defender)
    moved_piece = board_after.piece_at(move.to_square)
    if king is None or moved_piece is None or moved_piece.color != attacker:
        return False

    if chess.square_distance(king, move.to_square) > 1:
        return False

    return board_after.is_attacked_by(defender, move.to_square) or board_after.is_check()


def _directions_for_slider(piece_type: chess.PieceType) -> tuple[tuple[int, int], ...]:
    if piece_type == chess.BISHOP:
        return DIAGONAL_DIRECTIONS
    if piece_type == chess.ROOK:
        return ORTHOGONAL_DIRECTIONS
    if piece_type == chess.QUEEN:
        return ORTHOGONAL_DIRECTIONS + DIAGONAL_DIRECTIONS
    return ()


def _ray_from(square: chess.Square, direction: tuple[int, int]) -> list[chess.Square]:
    file_index = chess.square_file(square) + direction[0]
    rank_index = chess.square_rank(square) + direction[1]
    ray: list[chess.Square] = []
    while 0 <= file_index <= 7 and 0 <= rank_index <= 7:
        ray.append(chess.square(file_index, rank_index))
        file_index += direction[0]
        rank_index += direction[1]
    return ray


def _square_name(square: chess.Square | None) -> str | None:
    return None if square is None else chess.square_name(square)


def _dedupe_tags(tags: list[TacticTag]) -> list[TacticTag]:
    seen: set[tuple[str, str, int]] = set()
    deduped: list[TacticTag] = []
    for tag in tags:
        key = (tag.theme, tag.move_uci, tag.ply_offset)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(tag)
    return deduped
