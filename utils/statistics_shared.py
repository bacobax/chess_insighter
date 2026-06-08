from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from utils.game_enrichment_transformer import EnrichedGame, EnrichedMove


DEFAULT_GLOBAL_STATISTICS_HPARAMS_PATH = Path("config/global_statistics_hparams.yaml")


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def loss_to_skill_score_base2(
    average_loss: float | None,
    half_life: float,
) -> float | None:
    if average_loss is None:
        return None
    if half_life <= 0:
        raise ValueError("half_life must be positive")
    return clamp01(2 ** (-max(0.0, average_loss) / half_life))


class StatisticsHparams:
    def __init__(self, path: str | Path = DEFAULT_GLOBAL_STATISTICS_HPARAMS_PATH):
        self.path = Path(path)
        self.values = self._load_simple_yaml(self.path)

    def required_float(self, dotted_path: str) -> float:
        value = self.required_value(dotted_path)
        if not isinstance(value, (int, float)):
            raise ValueError(f"Hparam must be numeric: {dotted_path}")
        return float(value)

    def required_int(self, dotted_path: str) -> int:
        value = self.required_value(dotted_path)
        if not isinstance(value, int):
            raise ValueError(f"Hparam must be an integer: {dotted_path}")
        return value

    def required_value(self, dotted_path: str) -> Any:
        current: Any = self.values
        for part in dotted_path.split("."):
            if not isinstance(current, dict) or part not in current:
                raise ValueError(f"Missing required hparam: {dotted_path}")
            current = current[part]
        return current

    @classmethod
    def _load_simple_yaml(cls, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"Global statistics hparams file not found: {path}")

        root: dict[str, Any] = {}
        stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

        for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line_without_comment = raw_line.split("#", 1)[0].rstrip()
            if not line_without_comment.strip():
                continue

            indent = len(line_without_comment) - len(line_without_comment.lstrip(" "))
            if indent % 2 != 0:
                raise ValueError(
                    f"Invalid YAML indentation in {path}:{line_number}. Use 2 spaces."
                )

            stripped = line_without_comment.strip()
            if ":" not in stripped:
                raise ValueError(f"Invalid YAML line in {path}:{line_number}: {raw_line}")

            key, raw_value = stripped.split(":", 1)
            key = key.strip()
            raw_value = raw_value.strip()
            if not key:
                raise ValueError(f"Empty YAML key in {path}:{line_number}")

            while stack and indent <= stack[-1][0]:
                stack.pop()
            if not stack:
                raise ValueError(f"Invalid YAML nesting in {path}:{line_number}")

            parent = stack[-1][1]
            if raw_value == "":
                nested: dict[str, Any] = {}
                parent[key] = nested
                stack.append((indent, nested))
            else:
                parent[key] = cls._parse_yaml_scalar(raw_value, path, line_number)

        return root

    @staticmethod
    def _parse_yaml_scalar(raw_value: str, path: Path, line_number: int) -> Any:
        try:
            if any(character in raw_value for character in [".", "e", "E"]):
                return float(raw_value)
            return int(raw_value)
        except ValueError as exc:
            raise ValueError(
                f"Invalid scalar in {path}:{line_number}. "
                "Only numeric hyperparameter values are supported."
            ) from exc


class PlayerGameSampler:
    def __init__(self, hparams: StatisticsHparams):
        self.result_score_win = hparams.required_float("result_scores.win")
        self.result_score_draw = hparams.required_float("result_scores.draw")
        self.result_score_loss = hparams.required_float("result_scores.loss")

    def target_games(self, games: list[EnrichedGame], username_key: str) -> list[EnrichedGame]:
        return [game for game in games if self.target_color(game, username_key) is not None]

    def target_moves(self, game: EnrichedGame, username_key: str) -> list[EnrichedMove]:
        target_color = self.target_color(game, username_key)
        if target_color is None:
            return []
        return [move for move in game.moves if move.player_color == target_color]

    def target_color(self, game: EnrichedGame, username_key: str) -> Optional[str]:
        if username_key_value(game.white_username) == username_key:
            return "white"
        if username_key_value(game.black_username) == username_key:
            return "black"

        for move in game.moves:
            if username_key_value(move.player_username) == username_key:
                return move.player_color

        return None

    def target_result_score(
        self,
        game: EnrichedGame,
        username_key: str,
    ) -> Optional[float]:
        target_color = self.target_color(game, username_key)
        if target_color is None:
            return None
        return self.result_score_for_color(game, target_color)

    def result_score_for_color(
        self,
        game: EnrichedGame,
        color_name: str,
    ) -> Optional[float]:
        chesscom_result = game.white_result if color_name == "white" else game.black_result
        return self._chesscom_result_score(chesscom_result, game.result, color_name)

    def _chesscom_result_score(
        self,
        chesscom_result: Optional[str],
        pgn_result: Optional[str],
        color: str,
    ) -> Optional[float]:
        if chesscom_result == "win":
            return self.result_score_win
        if chesscom_result in {
            "checkmated",
            "resigned",
            "timeout",
            "abandoned",
            "lose",
        }:
            return self.result_score_loss
        if chesscom_result in {
            "agreed",
            "repetition",
            "stalemate",
            "insufficient",
            "50move",
            "timevsinsufficient",
        }:
            return self.result_score_draw

        if pgn_result == "1/2-1/2":
            return self.result_score_draw
        if pgn_result == "1-0":
            return self.result_score_win if color == "white" else self.result_score_loss
        if pgn_result == "0-1":
            return self.result_score_win if color == "black" else self.result_score_loss

        return None

    @staticmethod
    def game_id(game: EnrichedGame, index: int) -> str:
        return game.uuid or game.url or f"game-{index + 1}"


def username_key_value(username: Optional[str]) -> str:
    return (username or "").strip().lower()
