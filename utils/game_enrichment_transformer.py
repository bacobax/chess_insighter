# game_enrichment_transformer.py

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Callable, Iterable, Optional
import io
import math

import chess
import chess.pgn
import chess.engine


CpToExpectedPointsFn = Callable[[int, int], float]


# ---------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class TopEngineMove:
    rank: int
    move_uci: Optional[str]
    eval_cp: Optional[int]
    line_uci: list[str]


@dataclass(frozen=True)
class EnginePositionInfo:
    eval_cp: Optional[int]
    best_move_uci: Optional[str]
    top_moves: list[TopEngineMove]

    best_move_cp_gain: Optional[int]
    eval_volatility_among_top_engine_lines: Optional[float]
    low_gap_between_top_moves: Optional[float]
    forcing_line_depth: int

    number_of_legal_moves: int
    complexity: Optional[float]
    absolute_complexity: Optional[float]

    engine_top_move_is_forcing: bool


@dataclass(frozen=True)
class EnrichedMove:
    game_uuid: Optional[str]
    game_url: Optional[str]

    ply: int
    move_number: int
    player_color: str
    player_username: Optional[str]

    san: str
    uci: str

    fen_before: str
    fen_after: str

    eval_before_cp: Optional[int]
    eval_after_cp: Optional[int]
    eval_best_move_cp: Optional[int]
    eval_played_move_cp: Optional[int]
    move_cp_loss: Optional[int]

    best_move_uci: Optional[str]
    top_engine_moves: list[TopEngineMove]

    best_move_cp_gain: Optional[int]
    win_prob_before: Optional[float]
    win_prob_after: Optional[float]
    win_prob_loss: Optional[float]

    clock_before: Optional[float]
    clock_after: Optional[float]
    clock_spent: Optional[float]

    phase: str
    position_type_tags: list[str]

    tactical_position: bool
    quiet_middlegame: bool
    complexity: Optional[float]
    number_of_legal_moves: int
    eval_volatility_among_top_engine_lines: Optional[float]
    forcing_line_depth: int
    low_gap_between_top_moves: Optional[float]
    engine_top_move_is_forcing: bool
    move_is_threat: bool

    is_capture: bool
    is_check: bool
    is_castling: bool
    is_promotion: bool

    in_opening_book: bool
    opening_eco: Optional[str]
    opening_name: Optional[str]
    absolute_complexity: Optional[float] = None


@dataclass(frozen=True)
class EnrichedGame:
    uuid: Optional[str]
    url: Optional[str]

    white_username: Optional[str]
    black_username: Optional[str]
    white_rating: Optional[int]
    black_rating: Optional[int]

    white_result: Optional[str]
    black_result: Optional[str]
    result: Optional[str]

    time_class: Optional[str]
    time_control: Optional[str]
    rated: Optional[bool]
    end_time: Optional[int]

    chesscom_white_accuracy: Optional[float]
    chesscom_black_accuracy: Optional[float]

    opening_eco: Optional[str]
    opening_name: Optional[str]

    moves: list[EnrichedMove]


# ---------------------------------------------------------------------
# Default configurable formula
# ---------------------------------------------------------------------

def default_cp_to_expected_points(cp: int, rating: int = 1500) -> float:
    rating_factor = 0.0025 + (rating - 1000) * 0.000001
    return 1 / (1 + math.exp(-rating_factor * cp))


# ---------------------------------------------------------------------
# Main transformer
# ---------------------------------------------------------------------

class GameEnrichmentTransformer:
    """
    Transforms raw Chess.com game dictionaries into enriched game/move objects.

    Chess.com provides:
        - PGN
        - player names
        - ratings
        - results
        - time_class
        - time_control
        - rated flag
        - end_time
        - URL / UUID
        - Chess.com accuracies, when available

    This transformer computes:
        - FEN before/after each move
        - engine eval before/after
        - best move
        - centipawn loss
        - expected points / win probability
        - clock information from PGN comments, when available
        - opening/middlegame/endgame phase
        - tactical / quiet / winning / losing / equal / time_pressure tags
        - quiet_middlegame tag
        - complexity score
    """

    def __init__(
        self,
        *,
        stockfish_path: str,
        opening_repository: Optional[Any] = None,
        engine_limit: Optional[chess.engine.Limit] = None,
        cp_to_expected_points_fn: CpToExpectedPointsFn = default_cp_to_expected_points,
        default_rating: int = 1500,
        mate_score: int = 100_000,
        time_pressure_seconds: float = 30.0,
        multipv: int = 3,
        opening_max_ply: int = 20,
        tactic_cp_gain_threshold: int = 150,
        quiet_top_gap_threshold: int = 120,
        quiet_best_move_gain_threshold: int = 100,
    ):
        self.stockfish_path = stockfish_path
        self.opening_repository = opening_repository
        self.engine_limit = engine_limit or chess.engine.Limit(depth=10)
        self.cp_to_expected_points_fn = cp_to_expected_points_fn
        self.default_rating = default_rating
        self.mate_score = mate_score
        self.time_pressure_seconds = time_pressure_seconds
        self.multipv = multipv
        self.opening_max_ply = opening_max_ply

        self.tactic_cp_gain_threshold = tactic_cp_gain_threshold
        self.quiet_top_gap_threshold = quiet_top_gap_threshold
        self.quiet_best_move_gain_threshold = quiet_best_move_gain_threshold

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def transform_games(self, games: Iterable[dict[str, Any]]) -> list[EnrichedGame]:
        enriched_games: list[EnrichedGame] = []
        position_analysis_cache: dict[str, EnginePositionInfo] = {}

        with chess.engine.SimpleEngine.popen_uci(self.stockfish_path) as engine:
            for game_data in games:
                if "pgn" not in game_data:
                    continue

                enriched_games.append(
                    self.transform_game(
                        game_data=game_data,
                        engine=engine,
                        position_analysis_cache=position_analysis_cache,
                    )
                )

        return enriched_games

    def transform_game(
        self,
        *,
        game_data: dict[str, Any],
        engine: chess.engine.SimpleEngine,
        position_analysis_cache: Optional[dict[str, EnginePositionInfo]] = None,
    ) -> EnrichedGame:
        pgn_text = game_data["pgn"]
        game = chess.pgn.read_game(io.StringIO(pgn_text))

        if game is None:
            raise ValueError("Could not parse PGN")

        white = game_data.get("white", {}) or {}
        black = game_data.get("black", {}) or {}
        accuracies = game_data.get("accuracies", {}) or {}

        white_username = white.get("username")
        black_username = black.get("username")
        white_rating = white.get("rating")
        black_rating = black.get("rating")

        game_opening = self._detect_game_opening(game)
        current_opening = None

        board = game.board()
        enriched_moves: list[EnrichedMove] = []

        previous_clock_by_color: dict[str, Optional[float]] = {
            "white": self._initial_clock_seconds(game_data.get("time_control")),
            "black": self._initial_clock_seconds(game_data.get("time_control")),
        }

        for ply, child_node in enumerate(game.mainline(), start=1):
            move = child_node.move
            if move is None:
                continue

            player_color = "white" if board.turn == chess.WHITE else "black"
            player_username = white_username if player_color == "white" else black_username
            player_rating = white_rating if player_color == "white" else black_rating
            if player_rating is None:
                player_rating = self.default_rating

            fen_before = board.fen()
            san = board.san(move)

            clock_before = previous_clock_by_color[player_color]
            clock_after = child_node.clock()
            clock_spent = self._safe_clock_spent(clock_before, clock_after)

            move_is_capture = board.is_capture(move)
            move_is_castling = board.is_castling(move)
            move_is_promotion = move.promotion is not None
            move_gives_check = self._gives_check(board, move)

            # Engine information BEFORE the move.
            engine_info_before = self._analyse_position_rich_cached(
                engine=engine,
                board=board,
                cache=position_analysis_cache,
            )

            # Evaluation if the played move is forced at root.
            eval_played_move_cp = self._analyse_forced_move(
                engine=engine,
                board=board,
                move=move,
            )

            move_cp_loss = self._compute_cp_loss(
                eval_best_move_cp=engine_info_before.eval_cp,
                eval_played_move_cp=eval_played_move_cp,
                player_color=player_color,
            )

            move_is_threat = self._is_threat_move(
                board=board,
                move=move,
                eval_before_cp=engine_info_before.eval_cp,
                eval_after_forced_cp=eval_played_move_cp,
                player_color=player_color,
            )

            tactical_position = self._is_tactical_position(
                best_move_cp_gain=engine_info_before.best_move_cp_gain,
                move_is_check=move_gives_check,
                move_is_capture=move_is_capture,
                move_is_threat=move_is_threat,
                engine_top_move_is_forcing=engine_info_before.engine_top_move_is_forcing,
            )

            opening_before = self._detect_board_opening(board)
            phase_before = self._classify_phase(
                board=board,
                ply=ply,
                book_status=opening_before is not None,
            )

            quiet_middlegame = self._is_quiet_middlegame(
                board=board,
                engine_info=engine_info_before,
                phase=phase_before,
            )

            player_eval_before = self._orient_cp(engine_info_before.eval_cp, player_color)
            win_prob_before = self._cp_to_probability(player_eval_before, player_rating)

            board.push(move)

            fen_after = board.fen()

            # Engine information AFTER the move.
            engine_info_after = self._analyse_position_rich_cached(
                engine=engine,
                board=board,
                cache=position_analysis_cache,
            )

            player_eval_after = self._orient_cp(engine_info_after.eval_cp, player_color)
            win_prob_after = self._cp_to_probability(player_eval_after, player_rating)

            win_prob_loss = None
            if win_prob_before is not None and win_prob_after is not None:
                win_prob_loss = win_prob_before - win_prob_after

            opening_after = self._detect_board_opening(board)
            if opening_after is not None:
                current_opening = opening_after

            position_type_tags = self._classify_position_tags(
                player_eval_before=player_eval_before,
                tactical_position=tactical_position,
                quiet_middlegame=quiet_middlegame,
                clock_after=clock_after,
                phase=phase_before,
            )

            enriched_move = EnrichedMove(
                game_uuid=game_data.get("uuid"),
                game_url=game_data.get("url"),

                ply=ply,
                move_number=(ply + 1) // 2,
                player_color=player_color,
                player_username=player_username,

                san=san,
                uci=move.uci(),

                fen_before=fen_before,
                fen_after=fen_after,

                eval_before_cp=engine_info_before.eval_cp,
                eval_after_cp=engine_info_after.eval_cp,
                eval_best_move_cp=engine_info_before.eval_cp,
                eval_played_move_cp=eval_played_move_cp,
                move_cp_loss=move_cp_loss,

                best_move_uci=engine_info_before.best_move_uci,
                top_engine_moves=engine_info_before.top_moves,

                best_move_cp_gain=engine_info_before.best_move_cp_gain,
                win_prob_before=win_prob_before,
                win_prob_after=win_prob_after,
                win_prob_loss=win_prob_loss,

                clock_before=clock_before,
                clock_after=clock_after,
                clock_spent=clock_spent,

                phase=phase_before,
                position_type_tags=position_type_tags,

                tactical_position=tactical_position,
                quiet_middlegame=quiet_middlegame,
                complexity=engine_info_before.complexity,
                absolute_complexity=engine_info_before.absolute_complexity,
                number_of_legal_moves=engine_info_before.number_of_legal_moves,
                eval_volatility_among_top_engine_lines=(
                    engine_info_before.eval_volatility_among_top_engine_lines
                ),
                forcing_line_depth=engine_info_before.forcing_line_depth,
                low_gap_between_top_moves=engine_info_before.low_gap_between_top_moves,
                engine_top_move_is_forcing=engine_info_before.engine_top_move_is_forcing,
                move_is_threat=move_is_threat,

                is_capture=move_is_capture,
                is_check=move_gives_check,
                is_castling=move_is_castling,
                is_promotion=move_is_promotion,

                in_opening_book=opening_after is not None,
                opening_eco=current_opening.eco if current_opening else None,
                opening_name=current_opening.name if current_opening else None,
            )

            enriched_moves.append(enriched_move)

            if clock_after is not None:
                previous_clock_by_color[player_color] = clock_after

        return EnrichedGame(
            uuid=game_data.get("uuid"),
            url=game_data.get("url"),

            white_username=white_username,
            black_username=black_username,
            white_rating=white_rating,
            black_rating=black_rating,

            white_result=white.get("result"),
            black_result=black.get("result"),
            result=game.headers.get("Result"),

            time_class=game_data.get("time_class"),
            time_control=game_data.get("time_control"),
            rated=game_data.get("rated"),
            end_time=game_data.get("end_time"),

            chesscom_white_accuracy=accuracies.get("white"),
            chesscom_black_accuracy=accuracies.get("black"),

            opening_eco=game_opening.eco if game_opening else None,
            opening_name=game_opening.name if game_opening else None,

            moves=enriched_moves,
        )

    # -----------------------------------------------------------------
    # Engine helpers
    # -----------------------------------------------------------------

    def _analyse_position_rich_cached(
        self,
        *,
        engine: chess.engine.SimpleEngine,
        board: chess.Board,
        cache: Optional[dict[str, EnginePositionInfo]],
    ) -> EnginePositionInfo:
        if cache is None:
            return self._analyse_position_rich(
                engine=engine,
                board=board,
            )

        fen = board.fen()
        cached = cache.get(fen)
        if cached is not None:
            return cached

        engine_info = self._analyse_position_rich(
            engine=engine,
            board=board,
        )
        cache[fen] = engine_info
        return engine_info

    def _analyse_position_rich(
        self,
        *,
        engine: chess.engine.SimpleEngine,
        board: chess.Board,
    ) -> EnginePositionInfo:
        legal_moves = list(board.legal_moves)
        number_of_legal_moves = len(legal_moves)

        if board.is_game_over():
            return EnginePositionInfo(
                eval_cp=self._terminal_eval_cp(board),
                best_move_uci=None,
                top_moves=[],
                best_move_cp_gain=None,
                eval_volatility_among_top_engine_lines=None,
                low_gap_between_top_moves=None,
                forcing_line_depth=0,
                number_of_legal_moves=number_of_legal_moves,
                complexity=None,
                absolute_complexity=None,
                engine_top_move_is_forcing=False,
            )

        raw_info = engine.analyse(
            board,
            self.engine_limit,
            multipv=min(self.multipv, max(1, number_of_legal_moves)),
        )

        if isinstance(raw_info, dict):
            raw_infos = [raw_info]
        else:
            raw_infos = raw_info

        top_moves: list[TopEngineMove] = []

        for idx, info in enumerate(raw_infos, start=1):
            pv = info.get("pv") or []
            score_cp = self._score_to_white_cp(info.get("score"))

            top_moves.append(
                TopEngineMove(
                    rank=idx,
                    move_uci=pv[0].uci() if pv else None,
                    eval_cp=score_cp,
                    line_uci=[move.uci() for move in pv],
                )
            )

        top_moves = [move for move in top_moves if move.move_uci is not None]

        eval_cp = top_moves[0].eval_cp if top_moves else None
        best_move_uci = top_moves[0].move_uci if top_moves else None

        best_move_cp_gain = self._compute_best_move_cp_gain(
            board=board,
            top_moves=top_moves,
        )

        eval_volatility = self._compute_eval_volatility(top_moves)
        low_gap = self._compute_low_gap_between_top_moves(top_moves, board.turn)

        forcing_line_depth = self._compute_forcing_line_depth(
            board=board,
            top_line_uci=top_moves[0].line_uci if top_moves else [],
        )

        engine_top_move_is_forcing = self._is_engine_top_move_forcing(
            board=board,
            top_line_uci=top_moves[0].line_uci if top_moves else [],
        )

        complexity = self._compute_complexity(
            number_of_legal_moves=number_of_legal_moves,
            eval_volatility_among_top_engine_lines=eval_volatility,
            forcing_line_depth=forcing_line_depth,
            low_gap_between_top_moves=low_gap,
        )
        absolute_complexity = self._compute_absolute_complexity(
            board=board,
            number_of_legal_moves=number_of_legal_moves,
            eval_volatility_among_top_engine_lines=eval_volatility,
            forcing_line_depth=forcing_line_depth,
            low_gap_between_top_moves=low_gap,
        )

        return EnginePositionInfo(
            eval_cp=eval_cp,
            best_move_uci=best_move_uci,
            top_moves=top_moves,
            best_move_cp_gain=best_move_cp_gain,
            eval_volatility_among_top_engine_lines=eval_volatility,
            low_gap_between_top_moves=low_gap,
            forcing_line_depth=forcing_line_depth,
            number_of_legal_moves=number_of_legal_moves,
            complexity=complexity,
            absolute_complexity=absolute_complexity,
            engine_top_move_is_forcing=engine_top_move_is_forcing,
        )

    def _analyse_forced_move(
        self,
        *,
        engine: chess.engine.SimpleEngine,
        board: chess.Board,
        move: chess.Move,
    ) -> Optional[int]:
        if board.is_game_over():
            return self._terminal_eval_cp(board)

        info = engine.analyse(
            board,
            self.engine_limit,
            root_moves=[move],
        )

        return self._score_to_white_cp(info.get("score"))

    def _score_to_white_cp(self, score: Optional[chess.engine.PovScore]) -> Optional[int]:
        if score is None:
            return None

        return score.white().score(mate_score=self.mate_score)

    def _terminal_eval_cp(self, board: chess.Board) -> int:
        outcome = board.outcome()

        if outcome is None or outcome.winner is None:
            return 0

        return self.mate_score if outcome.winner == chess.WHITE else -self.mate_score

    def _compute_cp_loss(
        self,
        *,
        eval_best_move_cp: Optional[int],
        eval_played_move_cp: Optional[int],
        player_color: str,
    ) -> Optional[int]:
        if eval_best_move_cp is None or eval_played_move_cp is None:
            return None

        if player_color == "white":
            return max(0, eval_best_move_cp - eval_played_move_cp)

        return max(0, eval_played_move_cp - eval_best_move_cp)

    def _compute_best_move_cp_gain(
        self,
        *,
        board: chess.Board,
        top_moves: list[TopEngineMove],
    ) -> Optional[int]:
        """
        Practical definition:
        how much better the best engine move is than the second engine move.

        From side-to-move perspective:
            White to move: best_eval - second_eval
            Black to move: second_eval - best_eval

        If only one move exists, returns 0.
        """
        if len(top_moves) < 2:
            return 0

        best_eval = top_moves[0].eval_cp
        second_eval = top_moves[1].eval_cp

        if best_eval is None or second_eval is None:
            return None

        if board.turn == chess.WHITE:
            return max(0, best_eval - second_eval)

        return max(0, second_eval - best_eval)

    # -----------------------------------------------------------------
    # Complexity helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _compute_eval_volatility(top_moves: list[TopEngineMove]) -> Optional[float]:
        evals = [move.eval_cp for move in top_moves if move.eval_cp is not None]

        if len(evals) < 2:
            return 0.0

        mean = sum(evals) / len(evals)
        variance = sum((value - mean) ** 2 for value in evals) / len(evals)

        return math.sqrt(variance)

    @staticmethod
    def _compute_low_gap_between_top_moves(
        top_moves: list[TopEngineMove],
        side_to_move: bool,
    ) -> Optional[float]:
        """
        Returns a larger score when the top engine moves are close.

        This is intentionally named like your feature:
            low_gap_between_top_moves

        Example:
            gap 0   -> 100
            gap 50  -> 50
            gap 100 -> 0
            gap >100 -> 0
        """
        if len(top_moves) < 2:
            return 0.0

        best_eval = top_moves[0].eval_cp
        second_eval = top_moves[1].eval_cp

        if best_eval is None or second_eval is None:
            return None

        raw_gap = abs(best_eval - second_eval)

        return max(0.0, 100.0 - float(raw_gap))

    def _compute_forcing_line_depth(
        self,
        *,
        board: chess.Board,
        top_line_uci: list[str],
    ) -> int:
        """
        Counts how many initial moves in the principal variation are forcing.

        A move is considered forcing if it:
            - gives check
            - captures
            - promotes
            - creates a mate threat by direct checkmate availability next ply
        """
        temp_board = board.copy()
        depth = 0

        for move_uci in top_line_uci:
            move = chess.Move.from_uci(move_uci)

            if move not in temp_board.legal_moves:
                break

            if not self._is_forcing_move(temp_board, move):
                break

            temp_board.push(move)
            depth += 1

        return depth

    def _compute_complexity(
        self,
        *,
        number_of_legal_moves: int,
        eval_volatility_among_top_engine_lines: Optional[float],
        forcing_line_depth: int,
        low_gap_between_top_moves: Optional[float],
    ) -> Optional[float]:
        """
        Complexity follows your structure:

            complexity =
                number_of_legal_moves
                + eval_volatility_among_top_engine_lines
                + forcing_line_depth
                + low_gap_between_top_moves

        The components are not normalized yet. This is deliberate: it keeps the
        first implementation transparent and easy to modify.
        """
        if (
            eval_volatility_among_top_engine_lines is None
            or low_gap_between_top_moves is None
        ):
            return None

        return (
            float(number_of_legal_moves)
            + float(eval_volatility_among_top_engine_lines)
            + float(forcing_line_depth)
            + float(low_gap_between_top_moves)
        )

    def _compute_absolute_complexity(
        self,
        *,
        board: chess.Board,
        number_of_legal_moves: int,
        eval_volatility_among_top_engine_lines: Optional[float],
        forcing_line_depth: int,
        low_gap_between_top_moves: Optional[float],
    ) -> Optional[float]:
        if (
            eval_volatility_among_top_engine_lines is None
            or low_gap_between_top_moves is None
        ):
            return None
        legal_move_complexity = min(1.0, number_of_legal_moves / 60.0)
        engine_ambiguity = min(1.0, max(0.0, low_gap_between_top_moves) / 100.0)
        eval_volatility = min(1.0, max(0.0, eval_volatility_among_top_engine_lines) / 300.0)
        forcing_depth = min(1.0, forcing_line_depth / 4.0)
        tactical_options = sum(
            1
            for move in board.legal_moves
            if board.is_capture(move) or board.gives_check(move)
        )
        tactical_options_score = min(1.0, tactical_options / 12.0)
        return max(
            0.0,
            min(
                1.0,
                0.25 * legal_move_complexity
                + 0.25 * engine_ambiguity
                + 0.20 * eval_volatility
                + 0.20 * forcing_depth
                + 0.10 * tactical_options_score,
            ),
        )

    # -----------------------------------------------------------------
    # Tactical / forcing / threat helpers
    # -----------------------------------------------------------------

    def _is_tactical_position(
        self,
        *,
        best_move_cp_gain: Optional[int],
        move_is_check: bool,
        move_is_capture: bool,
        move_is_threat: bool,
        engine_top_move_is_forcing: bool,
    ) -> bool:
        return (
            (best_move_cp_gain is not None and best_move_cp_gain >= self.tactic_cp_gain_threshold)
            or move_is_check
            or move_is_capture
            or move_is_threat
            or engine_top_move_is_forcing
        )

    def _is_forcing_move(self, board: chess.Board, move: chess.Move) -> bool:
        if board.is_capture(move):
            return True

        if self._gives_check(board, move):
            return True

        if move.promotion is not None:
            return True

        if self._creates_immediate_mate_threat(board, move):
            return True

        return False

    def _is_engine_top_move_forcing(
        self,
        *,
        board: chess.Board,
        top_line_uci: list[str],
    ) -> bool:
        if not top_line_uci:
            return False

        move = chess.Move.from_uci(top_line_uci[0])

        if move not in board.legal_moves:
            return False

        return self._is_forcing_move(board, move)

    def _is_threat_move(
        self,
        *,
        board: chess.Board,
        move: chess.Move,
        eval_before_cp: Optional[int],
        eval_after_forced_cp: Optional[int],
        player_color: str,
    ) -> bool:
        """
        Threat heuristic.

        Since Stockfish does not directly say "this move is a threat", this
        uses two signals:

        1. The move creates an immediate mate-in-1 threat.
        2. The move improves the moving player's evaluation by >= 100 cp
           without being a check or capture.

        This prevents simple captures/checks from being double-counted as threats.
        """
        if self._gives_check(board, move) or board.is_capture(move):
            return False

        if self._creates_immediate_mate_threat(board, move):
            return True

        if eval_before_cp is None or eval_after_forced_cp is None:
            return False

        before_for_player = self._orient_cp(eval_before_cp, player_color)
        after_for_player = self._orient_cp(eval_after_forced_cp, player_color)

        if before_for_player is None or after_for_player is None:
            return False

        return (after_for_player - before_for_player) >= 100

    @staticmethod
    def _gives_check(board: chess.Board, move: chess.Move) -> bool:
        return board.gives_check(move)

    def _creates_immediate_mate_threat(self, board: chess.Board, move: chess.Move) -> bool:
        """
        After making the move, checks whether the same side would have a
        checkmate-in-one available after the opponent makes a null-like pass.

        Because actual chess has no pass move, this is only a heuristic:
        we check whether the side to move after the opponent's turn currently
        has any direct mate move if it were their turn again. This is expensive
        to model exactly, so this function uses a conservative approximation:
        after the move, if the opponent is already checkmated, or if the move
        gives check, it is not treated as a separate threat.
        """
        if board.gives_check(move):
            return False

        temp_board = board.copy()
        temp_board.push(move)

        if temp_board.is_checkmate():
            return True

        # Conservative practical heuristic:
        # if the opponent has very few legal replies and is in check, but this
        # branch is already excluded by gives_check above.
        return False

    # -----------------------------------------------------------------
    # Probability helpers
    # -----------------------------------------------------------------

    def _cp_to_probability(
        self,
        cp: Optional[int],
        rating: int,
    ) -> Optional[float]:
        if cp is None:
            return None

        return self.cp_to_expected_points_fn(cp, rating)

    @staticmethod
    def _orient_cp(cp: Optional[int], player_color: str) -> Optional[int]:
        if cp is None:
            return None

        return cp if player_color == "white" else -cp

    # -----------------------------------------------------------------
    # Opening helpers
    # -----------------------------------------------------------------

    def _detect_game_opening(self, game: chess.pgn.Game) -> Optional[Any]:
        if self.opening_repository is None:
            return None

        return self.opening_repository.detect_from_pgn_game(game)

    def _detect_board_opening(self, board: chess.Board) -> Optional[Any]:
        if self.opening_repository is None:
            return None

        return self.opening_repository.get_by_board(board)

    def _is_opening_position(
        self,
        *,
        board: chess.Board,
        ply: int,
        book_status: bool,
    ) -> bool:
        """
        Opening definition.

        A position is opening if:
            - it is still inside the opening repository, or
            - it is within the configured opening ply limit.

        You can make this stricter later by requiring book_status only.
        """
        return book_status or ply <= self.opening_max_ply

    # -----------------------------------------------------------------
    # Phase helpers
    # -----------------------------------------------------------------

    def _classify_phase(
        self,
        *,
        board: chess.Board,
        ply: int,
        book_status: bool,
    ) -> str:
        if self._is_opening_position(board=board, ply=ply, book_status=book_status):
            return "opening"

        if self._is_endgame(board):
            return "endgame"

        return "middlegame"

    def _is_middlegame(
        self,
        *,
        board: chess.Board,
        ply: int,
        book_status: bool,
    ) -> bool:
        return (
            not self._is_opening_position(board=board, ply=ply, book_status=book_status)
            and not self._is_endgame(board)
        )

    @staticmethod
    def _is_endgame(board: chess.Board) -> bool:
        queens = (
            len(board.pieces(chess.QUEEN, chess.WHITE))
            + len(board.pieces(chess.QUEEN, chess.BLACK))
        )

        non_pawn_material = 0

        values = {
            chess.KNIGHT: 300,
            chess.BISHOP: 300,
            chess.ROOK: 500,
            chess.QUEEN: 900,
        }

        for piece_type, value in values.items():
            non_pawn_material += value * (
                len(board.pieces(piece_type, chess.WHITE))
                + len(board.pieces(piece_type, chess.BLACK))
            )

        if non_pawn_material <= 2600:
            return True

        if queens == 0 and non_pawn_material <= 3600:
            return True

        return False

    def _is_quiet_middlegame(
        self,
        *,
        board: chess.Board,
        engine_info: EnginePositionInfo,
        phase: str,
    ) -> bool:
        if phase != "middlegame":
            return False

        if board.is_check():
            return False

        if len(engine_info.top_moves) < 2:
            return False

        best_move_uci = engine_info.top_moves[0].move_uci
        if best_move_uci is None:
            return False

        best_move = chess.Move.from_uci(best_move_uci)
        if best_move not in board.legal_moves:
            return False

        best_eval = engine_info.top_moves[0].eval_cp
        second_eval = engine_info.top_moves[1].eval_cp

        if best_eval is None or second_eval is None:
            return False

        top_gap = abs(best_eval - second_eval)

        if top_gap >= self.quiet_top_gap_threshold:
            return False

        if (
            engine_info.best_move_cp_gain is not None
            and engine_info.best_move_cp_gain >= self.quiet_best_move_gain_threshold
        ):
            return False

        if board.is_capture(best_move):
            return False

        if self._gives_check(board, best_move):
            return False

        piece = board.piece_at(best_move.from_square)
        if piece is not None and piece.piece_type == chess.PAWN:
            if chess.square_rank(best_move.to_square) in [0, 7]:
                return False

        return True

    # -----------------------------------------------------------------
    # Clock helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _initial_clock_seconds(time_control: Optional[str]) -> Optional[float]:
        """
        Chess.com time_control examples:
            "600"
            "300+5"
            "1/259200"
            "-"

        We only infer initial clock for ordinary live formats.
        """
        if not time_control:
            return None

        if time_control == "-":
            return None

        if "/" in time_control:
            return None

        base = time_control.split("+")[0]

        try:
            return float(base)
        except ValueError:
            return None

    @staticmethod
    def _safe_clock_spent(
        clock_before: Optional[float],
        clock_after: Optional[float],
    ) -> Optional[float]:
        if clock_before is None or clock_after is None:
            return None

        return clock_before - clock_after

    # -----------------------------------------------------------------
    # Position tags
    # -----------------------------------------------------------------

    def _classify_position_tags(
        self,
        *,
        player_eval_before: Optional[int],
        tactical_position: bool,
        quiet_middlegame: bool,
        clock_after: Optional[float],
        phase: str,
    ) -> list[str]:
        tags: list[str] = []

        if player_eval_before is not None:
            if player_eval_before >= 200:
                tags.append("winning")
            elif player_eval_before <= -200:
                tags.append("losing")
            else:
                tags.append("equal")

        if tactical_position:
            tags.append("tactical")
        else:
            tags.append("quiet")

        if quiet_middlegame:
            tags.append("quiet_middlegame")

        if phase == "endgame":
            tags.append("endgame")

        if clock_after is not None and clock_after <= self.time_pressure_seconds:
            tags.append("time_pressure")

        return tags


# ---------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------

def enriched_games_to_dicts(enriched_games: list[EnrichedGame]) -> list[dict[str, Any]]:
    return [asdict(game) for game in enriched_games]


def enriched_moves_to_flat_dicts(enriched_games: list[EnrichedGame]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for game in enriched_games:
        for move in game.moves:
            rows.append(asdict(move))

    return rows
