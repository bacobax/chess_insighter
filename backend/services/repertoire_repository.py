"""Saved repertoires: one document per account and colour in ``repertoires``.

Choices are keyed by position (EPD), not by move order, so a move chosen once
also applies when the same position is reached by a transposition. A new
choice must be *playable* under the account's settings (see
``repertoire_service.is_playable``); seeded defaults skip that check.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Literal, Sequence

import chess

from backend.services import mongo_service
from backend.services.engine_eval_service import evaluate_position
from backend.services.repertoire_lines import LineSettings
from backend.services.repertoire_service import DEFAULT_CONFIG, RepertoireConfig, is_playable, replay_prefix
from utils.opening_popularity import position_key
from utils.training_plan import SIMPLE_REPERTOIRE, parse_line_text


Color = Literal["white", "black"]
COLLECTION = "repertoires"

DEFAULT_SETTINGS: dict[str, Any] = {
    "cpTolerance": DEFAULT_CONFIG.cp_tolerance,
    "minEvalCp": DEFAULT_CONFIG.min_eval_cp,
    "minReach": LineSettings().min_reach,
    "maxOwnMoves": LineSettings().max_own_moves,
}

# Default lines per colour: the training plan's short, low-theory repertoire.
DEFAULT_SEED_SLOTS: dict[str, tuple[str, ...]] = {
    "white": ("white",),
    "black": ("black_vs_e4", "black_vs_d4"),
}


class ChoiceNotPlayable(ValueError):
    """The move loses too much against the engine's best move, or leaves you too far behind."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _doc_id(owner_id: str, color: Color) -> str:
    return f"{owner_id}:{color}"


def config_for(settings_doc: dict[str, Any]) -> RepertoireConfig:
    return replace(DEFAULT_CONFIG, cp_tolerance=int(settings_doc["cpTolerance"]), min_eval_cp=int(settings_doc["minEvalCp"]))


def line_settings_for(settings_doc: dict[str, Any]) -> LineSettings:
    return LineSettings(min_reach=float(settings_doc["minReach"]), max_own_moves=int(settings_doc["maxOwnMoves"]))


def _own_turn_board(color: Color, prefix_uci: Sequence[str]) -> chess.Board:
    board = replay_prefix(prefix_uci)[-1]
    if (board.turn == chess.WHITE) != (color == "white"):
        raise ValueError("It is the opponent's move in this position; choices are only saved for your own moves.")
    return board


class RepertoireStore:
    def _collection(self):
        return mongo_service.collection(COLLECTION)

    def get(self, owner_id: str, color: Color) -> dict[str, Any]:
        doc = self._collection().find_one({"_id": _doc_id(owner_id, color)}, {"_id": 0})
        if doc is None:
            return {"color": color, "choices": {}, "settings": dict(DEFAULT_SETTINGS), "updatedAt": None}
        return {
            "color": color,
            "choices": doc.get("choices") or {},
            "settings": {**DEFAULT_SETTINGS, **(doc.get("settings") or {})},
            "updatedAt": doc.get("updated_at"),
        }

    def _upsert(self, owner_id: str, color: Color, update: dict[str, Any]) -> None:
        self._collection().update_one(
            {"_id": _doc_id(owner_id, color)},
            {
                **update,
                "$set": {**update.get("$set", {}), "updated_at": _now()},
                "$setOnInsert": {"owner_id": owner_id, "color": color},
            },
            upsert=True,
        )

    def set_choice(
        self,
        owner_id: str,
        color: Color,
        prefix_uci: Sequence[str],
        move_uci: str,
        *,
        engine=None,
    ) -> dict[str, Any]:
        """Save your move in this position after checking it against the engine.

        Raises ``ChoiceNotPlayable`` (400), or ``EngineBusy`` / ``EngineUnavailable``
        when the move cannot be checked right now.
        """
        board = _own_turn_board(color, prefix_uci)
        try:
            move = board.parse_uci(move_uci)
        except ValueError as exc:
            raise ValueError(f"{move_uci} is not a legal move in this position.") from exc
        config = config_for(self.get(owner_id, color)["settings"])
        evaluation = evaluate_position(
            board,
            moves=[move.uci()],
            depth=config.engine_depth,
            multipv=config.engine_multipv,
            engine=engine,
            wait=config.engine_wait_seconds,
        )
        move_eval = evaluation.moves.get(move.uci())
        cp_loss = evaluation.cp_loss(move.uci())
        if not is_playable(move_eval.cp if move_eval else None, cp_loss, config):
            raise ChoiceNotPlayable(
                f"{board.san(move)} is {cp_loss} cp behind the engine's best move"
                f" and leaves you at {move_eval.cp if move_eval else '?'} cp"
                f" (limits: {config.cp_tolerance} cp behind, at least {config.min_eval_cp} cp)."
            )
        choice = {
            "uci": move.uci(),
            "san": board.san(move),
            "prefixUci": list(prefix_uci),
            "cp": move_eval.cp,
            "cpLoss": cp_loss,
            "depth": evaluation.depth,
            "source": "user",
            "chosenAt": _now(),
        }
        self._upsert(owner_id, color, {"$set": {f"choices.{position_key(board)}": choice}})
        return self.get(owner_id, color)

    def remove_choice(self, owner_id: str, color: Color, prefix_uci: Sequence[str]) -> dict[str, Any]:
        board = _own_turn_board(color, prefix_uci)
        self._upsert(owner_id, color, {"$unset": {f"choices.{position_key(board)}": ""}})
        return self.get(owner_id, color)

    def update_settings(self, owner_id: str, color: Color, patch: dict[str, Any]) -> dict[str, Any]:
        unknown = set(patch) - set(DEFAULT_SETTINGS)
        if unknown:
            raise ValueError(f"Unknown repertoire settings: {', '.join(sorted(unknown))}")
        if patch:
            self._upsert(owner_id, color, {"$set": {f"settings.{key}": value for key, value in patch.items()}})
        return self.get(owner_id, color)

    def seed(self, owner_id: str, color: Color, lines: Sequence[str] | None = None) -> dict[str, Any]:
        """Add your moves along ``lines`` (SAN text) wherever no choice exists yet.

        Without ``lines`` the training plan's simple repertoire is used. Seeds are
        trusted defaults and skip the engine check; existing choices are kept.
        """
        sans_lines = [parse_line_text(text) for text in lines] if lines else [
            list(SIMPLE_REPERTOIRE[slot]["line"]) for slot in DEFAULT_SEED_SLOTS[color]
        ]
        existing = self.get(owner_id, color)["choices"]
        new: dict[str, Any] = {}
        for sans in sans_lines:
            board = chess.Board()
            prefix: list[str] = []
            for san in sans:
                try:
                    move = board.parse_san(san)
                except ValueError as exc:
                    raise ValueError(f"Illegal move in the seed line: {san}") from exc
                if (board.turn == chess.WHITE) == (color == "white"):
                    key = position_key(board)
                    if key not in existing and key not in new:
                        new[key] = {
                            "uci": move.uci(),
                            "san": board.san(move),
                            "prefixUci": list(prefix),
                            "cp": None,
                            "cpLoss": None,
                            "depth": None,
                            "source": "seed",
                            "chosenAt": _now(),
                        }
                board.push(move)
                prefix.append(move.uci())
        if new:
            self._upsert(owner_id, color, {"$set": {f"choices.{key}": value for key, value in new.items()}})
        return self.get(owner_id, color)
