from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from utils.game_enrichment_transformer import EnrichedGame, EnrichedMove


@dataclass(frozen=True)
class StatisticResult:
    score: Optional[float]
    average_loss: Optional[float]
    sample_count: int
    game_count: int


@dataclass(frozen=True)
class OpeningStatistics:
    score: Optional[float]
    book_accuracy: Optional[float]
    eval_stability_after_opening: Optional[float]
    result_from_opening_positions: Optional[float]
    opening_move_count: int
    post_opening_move_count: int
    game_count: int


@dataclass(frozen=True)
class TimeManagementStatistics:
    score: Optional[float]
    average_time_spent_by_complexity: dict[str, Optional[float]]
    blunder_rate_in_time_pressure: Optional[float]
    time_trouble_frequency: Optional[float]
    critical_position_underthinking_rate: Optional[float]
    overthinking_simple_positions_rate: Optional[float]
    target_move_count: int
    pressure_move_count: int
    clock_sample_count: int


@dataclass(frozen=True)
class GameAnalysisStatistics:
    score: Optional[float]
    mistake_repetition_rate: Optional[float]
    weakness_improvement_rate: Optional[float]
    same_pattern_error_decay: Optional[float]
    post_loss_improvement: Optional[float]
    weakness_opportunity_count: int
    improvement_count: int


@dataclass(frozen=True)
class AdvantageCapitalizationStatistics:
    score: Optional[float]
    conversion_rate_from_plus_2: Optional[float]
    conversion_rate_from_plus_5: Optional[float]
    average_eval_drop_after_getting_advantage: Optional[float]
    number_of_moves_to_convert: Optional[float]
    winning_position_blunder_rate: Optional[float]
    eval_preservation_when_ahead: Optional[float]
    low_blunder_rate_when_ahead: Optional[float]
    winning_game_count: int
    clearly_winning_game_count: int
    winning_move_count: int


@dataclass(frozen=True)
class ResourcefulnessStatistics:
    score: Optional[float]
    save_rate_from_minus_2: Optional[float]
    draw_or_win_rate_from_lost_positions: Optional[float]
    eval_recovery_rate: Optional[float]
    opponent_error_inducement_rate: Optional[float]
    survival_moves_before_collapse: Optional[float]
    low_collapse_rate_when_worse: Optional[float]
    worse_game_count: int
    lost_game_count: int
    worse_move_count: int


@dataclass(frozen=True)
class GlobalStatistics:
    username: str
    games_count: int
    target_games_count: int
    target_moves_count: int
    min_samples: int
    complexity_p50: Optional[float]
    complexity_p85: Optional[float]
    complexity_p90: Optional[float]
    tactics_score: StatisticResult
    calculation_score: StatisticResult
    openings_score: OpeningStatistics
    middlegame_strategy_score: StatisticResult
    endgame_score: StatisticResult
    time_management_score: TimeManagementStatistics
    game_analysis_score: GameAnalysisStatistics
    advantage_capitalization_score: AdvantageCapitalizationStatistics
    resourcefulness_score: ResourcefulnessStatistics


class GlobalStatisticsTransformer:
    """
    Computes player-focused skill statistics from already-enriched games.

    Scores are normalized to 0..1. Missing source data is skipped; a score is
    None when no qualifying samples are available.
    """

    def __init__(self, hparams_path: str | Path):
        self.hparams_path = Path(hparams_path)
        hparams = self._load_simple_yaml(self.hparams_path)

        self.min_samples = self._required_int(hparams, "sampling.min_samples")

        self.complexity_simple_percentile = self._required_float(
            hparams, "complexity.simple_percentile"
        )
        self.complexity_complex_percentile = self._required_float(
            hparams, "complexity.complex_percentile"
        )
        self.complexity_high_percentile = self._required_float(
            hparams, "complexity.high_percentile"
        )

        self.opening_post_opening_move_count = self._required_int(
            hparams, "opening.post_opening_move_count"
        )
        self.opening_weight_book_accuracy = self._required_float(
            hparams, "opening.weights.book_accuracy"
        )
        self.opening_weight_eval_stability_after_opening = self._required_float(
            hparams, "opening.weights.eval_stability_after_opening"
        )
        self.opening_weight_result_from_opening_positions = self._required_float(
            hparams, "opening.weights.result_from_opening_positions"
        )

        self.time_pressure_seconds = self._required_float(
            hparams, "time_management.time_pressure_seconds"
        )
        self.blunder_win_prob_loss = self._required_float(
            hparams, "time_management.blunder_win_prob_loss"
        )
        self.critical_underthinking_seconds = self._required_float(
            hparams, "time_management.critical_underthinking_seconds"
        )
        self.simple_overthinking_seconds = self._required_float(
            hparams, "time_management.simple_overthinking_seconds"
        )
        self.opponent_error_win_prob_loss = self._required_float(
            hparams, "time_management.opponent_error_win_prob_loss"
        )
        self.time_weight_time_trouble = self._required_float(
            hparams, "time_management.weights.time_trouble"
        )
        self.time_weight_blunders_in_time_pressure = self._required_float(
            hparams, "time_management.weights.blunders_in_time_pressure"
        )
        self.time_weight_bad_time_allocation = self._required_float(
            hparams, "time_management.weights.bad_time_allocation"
        )

        self.weakness_loss_threshold = self._required_float(
            hparams, "game_analysis.weakness_loss_threshold"
        )
        self.improvement_delta = self._required_float(
            hparams, "game_analysis.improvement_delta"
        )

        self.winning_eval_cp = self._required_float(
            hparams, "advantage_capitalization.winning_eval_cp"
        )
        self.clearly_winning_eval_cp = self._required_float(
            hparams, "advantage_capitalization.clearly_winning_eval_cp"
        )
        self.advantage_weight_conversion_rate = self._required_float(
            hparams,
            "advantage_capitalization.weights.conversion_rate_from_winning_positions",
        )
        self.advantage_weight_eval_preservation = self._required_float(
            hparams, "advantage_capitalization.weights.eval_preservation_when_ahead"
        )
        self.advantage_weight_low_blunder_rate = self._required_float(
            hparams, "advantage_capitalization.weights.low_blunder_rate_when_ahead"
        )

        self.worse_eval_cp = self._required_float(
            hparams, "resourcefulness.worse_eval_cp"
        )
        self.lost_eval_cp = self._required_float(
            hparams, "resourcefulness.lost_eval_cp"
        )
        self.resourcefulness_weight_save_rate = self._required_float(
            hparams, "resourcefulness.weights.save_rate_from_bad_positions"
        )
        self.resourcefulness_weight_eval_recovery = self._required_float(
            hparams, "resourcefulness.weights.eval_recovery_after_disadvantage"
        )
        self.resourcefulness_weight_low_collapse_rate = self._required_float(
            hparams, "resourcefulness.weights.low_collapse_rate_when_worse"
        )

        self.result_score_win = self._required_float(hparams, "result_scores.win")
        self.result_score_draw = self._required_float(hparams, "result_scores.draw")
        self.result_score_loss = self._required_float(hparams, "result_scores.loss")

    def compute(
        self,
        games: list[EnrichedGame],
        username: str,
    ) -> GlobalStatistics:
        username_key = self._username_key(username)
        target_games = [
            game for game in games if self._target_color(game, username_key) is not None
        ]
        target_moves = [
            move
            for game in target_games
            for move in self._target_moves(game, username_key)
        ]

        complexities = [
            move.complexity
            for game in games
            for move in game.moves
            if move.complexity is not None
        ]
        complexity_p50 = self._percentile(complexities, self.complexity_simple_percentile)
        complexity_p85 = self._percentile(complexities, self.complexity_complex_percentile)
        complexity_p90 = self._percentile(complexities, self.complexity_high_percentile)

        return GlobalStatistics(
            username=username,
            games_count=len(games),
            target_games_count=len(target_games),
            target_moves_count=len(target_moves),
            min_samples=self.min_samples,
            complexity_p50=complexity_p50,
            complexity_p85=complexity_p85,
            complexity_p90=complexity_p90,
            tactics_score=self._loss_score(
                target_games,
                username_key,
                self.min_samples,
                lambda move: "tactical" in move.position_type_tags,
            ),
            calculation_score=self._loss_score(
                target_games,
                username_key,
                self.min_samples,
                lambda move: (
                    complexity_p85 is not None
                    and move.complexity is not None
                    and move.complexity > complexity_p85
                ),
            ),
            openings_score=self._opening_statistics(
                target_games,
                username_key,
                self.min_samples,
            ),
            middlegame_strategy_score=self._loss_score(
                target_games,
                username_key,
                self.min_samples,
                lambda move: move.quiet_middlegame,
            ),
            endgame_score=self._loss_score(
                target_games,
                username_key,
                self.min_samples,
                lambda move: move.phase == "endgame",
            ),
            time_management_score=self._time_management_statistics(
                target_games,
                username_key,
                complexity_p50,
                complexity_p85,
                complexity_p90,
            ),
            game_analysis_score=self._game_analysis_statistics(
                target_games,
                username_key,
                self.min_samples,
                complexity_p85,
            ),
            advantage_capitalization_score=self._advantage_statistics(
                target_games,
                username_key,
                self.min_samples,
            ),
            resourcefulness_score=self._resourcefulness_statistics(
                target_games,
                username_key,
            ),
        )

    def _loss_score(
        self,
        games: list[EnrichedGame],
        username_key: str,
        min_samples: int,
        predicate: Callable[[EnrichedMove], bool],
    ) -> StatisticResult:
        game_losses: list[float] = []
        sample_count = 0

        for game in games:
            losses = [
                loss
                for move in self._target_moves(game, username_key)
                if predicate(move)
                for loss in [self._win_prob_loss(move)]
                if loss is not None
            ]
            if len(losses) >= min_samples:
                game_losses.append(self._mean(losses))
                sample_count += len(losses)

        if not game_losses:
            return StatisticResult(
                score=None,
                average_loss=None,
                sample_count=0,
                game_count=0,
            )

        average_loss = self._mean(game_losses)
        return StatisticResult(
            score=self._clamp01(1.0 - average_loss),
            average_loss=average_loss,
            sample_count=sample_count,
            game_count=len(game_losses),
        )

    def _opening_statistics(
        self,
        games: list[EnrichedGame],
        username_key: str,
        min_samples: int,
    ) -> OpeningStatistics:
        book_accuracies: list[float] = []
        post_opening_losses: list[float] = []
        opening_results: list[float] = []
        opening_move_count = 0
        post_opening_move_count = 0

        for game in games:
            target_moves = self._target_moves(game, username_key)
            opening_moves = [move for move in target_moves if move.phase == "opening"]
            if len(opening_moves) >= min_samples:
                opening_move_count += len(opening_moves)
                book_accuracies.append(
                    self._mean([1.0 if move.in_opening_book else 0.0 for move in opening_moves])
                )

            first_post_opening = next(
                (
                    index
                    for index, move in enumerate(target_moves)
                    if move.phase != "opening"
                ),
                None,
            )
            if first_post_opening is not None:
                post_moves = target_moves[
                    first_post_opening:
                    first_post_opening + self.opening_post_opening_move_count
                ]
                losses = [
                    loss
                    for move in post_moves
                    for loss in [self._win_prob_loss(move)]
                    if loss is not None
                ]
                if len(losses) >= min_samples:
                    post_opening_move_count += len(losses)
                    post_opening_losses.append(self._mean(losses))

            if any(move.in_opening_book for move in target_moves):
                result = self._target_result_score(game, username_key)
                if result is not None:
                    opening_results.append(result)

        book_accuracy = self._safe_mean(book_accuracies)
        eval_stability_after_opening = (
            self._clamp01(1.0 - self._mean(post_opening_losses))
            if post_opening_losses
            else None
        )
        result_from_opening_positions = self._safe_mean(opening_results)

        score = self._weighted_score(
            [
                (book_accuracy, self.opening_weight_book_accuracy),
                (
                    eval_stability_after_opening,
                    self.opening_weight_eval_stability_after_opening,
                ),
                (
                    result_from_opening_positions,
                    self.opening_weight_result_from_opening_positions,
                ),
            ]
        )

        return OpeningStatistics(
            score=score,
            book_accuracy=book_accuracy,
            eval_stability_after_opening=eval_stability_after_opening,
            result_from_opening_positions=result_from_opening_positions,
            opening_move_count=opening_move_count,
            post_opening_move_count=post_opening_move_count,
            game_count=len(opening_results),
        )

    def _time_management_statistics(
        self,
        games: list[EnrichedGame],
        username_key: str,
        complexity_p50: Optional[float],
        complexity_p85: Optional[float],
        complexity_p90: Optional[float],
    ) -> TimeManagementStatistics:
        moves = [
            move
            for game in games
            for move in self._target_moves(game, username_key)
        ]
        clock_before_moves = [move for move in moves if move.clock_before is not None]
        spent_moves = [move for move in moves if move.clock_spent is not None]
        pressure_moves = [
            move
            for move in clock_before_moves
            if move.clock_before is not None
            and move.clock_before < self.time_pressure_seconds
        ]

        time_trouble_frequency = (
            len(pressure_moves) / len(clock_before_moves)
            if clock_before_moves
            else None
        )
        blunder_rate_in_time_pressure = (
            self._rate(pressure_moves, self._is_blunder)
            if pressure_moves
            else (0.0 if clock_before_moves else None)
        )

        critical_moves = [
            move
            for move in spent_moves
            if move.tactical_position
            or (
                complexity_p85 is not None
                and move.complexity is not None
                and move.complexity > complexity_p85
            )
        ]
        simple_moves = [
            move
            for move in spent_moves
            if not move.tactical_position
            and complexity_p50 is not None
            and move.complexity is not None
            and move.complexity < complexity_p50
        ]

        critical_position_underthinking_rate = (
            self._rate(
                critical_moves,
                lambda move: (
                    move.clock_spent is not None
                    and move.clock_spent <= self.critical_underthinking_seconds
                ),
            )
            if critical_moves
            else (0.0 if spent_moves else None)
        )
        overthinking_simple_positions_rate = (
            self._rate(
                simple_moves,
                lambda move: (
                    move.clock_spent is not None
                    and move.clock_spent >= self.simple_overthinking_seconds
                ),
            )
            if simple_moves
            else (0.0 if spent_moves else None)
        )

        score = None
        if any(
            value is not None
            for value in [
                time_trouble_frequency,
                blunder_rate_in_time_pressure,
                critical_position_underthinking_rate,
                overthinking_simple_positions_rate,
            ]
        ):
            bad_time_allocation = self._mean(
                [
                    critical_position_underthinking_rate or 0.0,
                    overthinking_simple_positions_rate or 0.0,
                ]
            )
            score = self._clamp01(
                1.0
                - self.time_weight_time_trouble * (time_trouble_frequency or 0.0)
                - self.time_weight_blunders_in_time_pressure * (
                    blunder_rate_in_time_pressure or 0.0
                )
                - self.time_weight_bad_time_allocation * bad_time_allocation
            )

        return TimeManagementStatistics(
            score=score,
            average_time_spent_by_complexity=self._average_time_spent_by_complexity(
                spent_moves,
                complexity_p50,
                complexity_p85,
                complexity_p90,
            ),
            blunder_rate_in_time_pressure=blunder_rate_in_time_pressure,
            time_trouble_frequency=time_trouble_frequency,
            critical_position_underthinking_rate=critical_position_underthinking_rate,
            overthinking_simple_positions_rate=overthinking_simple_positions_rate,
            target_move_count=len(moves),
            pressure_move_count=len(pressure_moves),
            clock_sample_count=len(clock_before_moves),
        )

    def _game_analysis_statistics(
        self,
        games: list[EnrichedGame],
        username_key: str,
        min_samples: int,
        complexity_p85: Optional[float],
    ) -> GameAnalysisStatistics:
        histories: dict[str, list[float]] = {
            bucket: []
            for bucket in [
                "tactical",
                "calculation",
                "opening",
                "quiet_middlegame",
                "endgame",
                "time_pressure",
                "advantage",
                "worse_position",
            ]
        }
        opportunities = 0
        improvements = 0
        error_decays: list[float] = []

        sorted_games = self._sort_games_by_time(games)
        for game in sorted_games:
            bucket_losses = self._game_bucket_losses(
                game,
                username_key,
                min_samples,
                complexity_p85,
            )
            for bucket, current_loss in bucket_losses.items():
                history = histories[bucket]
                if len(history) >= min_samples:
                    prior_loss = self._mean(history)
                    if prior_loss >= self.weakness_loss_threshold:
                        opportunities += 1
                        decay = prior_loss - current_loss
                        error_decays.append(decay)
                        if decay >= self.improvement_delta:
                            improvements += 1
                history.append(current_loss)

        weakness_improvement_rate = (
            improvements / opportunities
            if opportunities
            else None
        )

        return GameAnalysisStatistics(
            score=weakness_improvement_rate,
            mistake_repetition_rate=(
                1.0 - weakness_improvement_rate
                if weakness_improvement_rate is not None
                else None
            ),
            weakness_improvement_rate=weakness_improvement_rate,
            same_pattern_error_decay=self._safe_mean(error_decays),
            post_loss_improvement=self._post_loss_improvement(
                sorted_games,
                username_key,
                min_samples,
            ),
            weakness_opportunity_count=opportunities,
            improvement_count=improvements,
        )

    def _advantage_statistics(
        self,
        games: list[EnrichedGame],
        username_key: str,
        min_samples: int,
    ) -> AdvantageCapitalizationStatistics:
        plus_2_results: list[float] = []
        plus_5_results: list[float] = []
        winning_game_losses: list[float] = []
        winning_blunders = 0
        eval_drops: list[float] = []
        moves_to_convert: list[float] = []
        winning_move_count = 0

        for game in games:
            target_moves = self._target_moves(game, username_key)
            winning_moves = [
                move for move in target_moves if self._eval_for_player(move) is not None
                and self._eval_for_player(move) >= self.winning_eval_cp
            ]
            clearly_winning_moves = [
                move for move in target_moves if self._eval_for_player(move) is not None
                and self._eval_for_player(move) >= self.clearly_winning_eval_cp
            ]
            result = self._target_result_score(game, username_key)
            if winning_moves and result is not None:
                plus_2_results.append(
                    self.result_score_win
                    if result == self.result_score_win
                    else self.result_score_loss
                )
            if clearly_winning_moves and result is not None:
                plus_5_results.append(
                    self.result_score_win
                    if result == self.result_score_win
                    else self.result_score_loss
                )
            if winning_moves and result == self.result_score_win:
                first_index = target_moves.index(winning_moves[0])
                moves_to_convert.append(float(len(target_moves) - first_index))

            losses = [
                loss
                for move in winning_moves
                for loss in [self._win_prob_loss(move)]
                if loss is not None
            ]
            if len(losses) >= min_samples:
                winning_game_losses.append(self._mean(losses))
            winning_move_count += len(winning_moves)
            winning_blunders += sum(1 for move in winning_moves if self._is_blunder(move))
            eval_drops.extend(
                drop
                for move in winning_moves
                for drop in [self._eval_drop_for_player(move)]
                if drop is not None
            )

        conversion_rate = self._safe_mean(plus_2_results)
        eval_preservation = (
            self._clamp01(1.0 - self._mean(winning_game_losses))
            if winning_game_losses
            else None
        )
        winning_position_blunder_rate = (
            winning_blunders / winning_move_count
            if winning_move_count
            else None
        )
        low_blunder_rate = (
            self._clamp01(1.0 - winning_position_blunder_rate)
            if winning_position_blunder_rate is not None
            else None
        )

        return AdvantageCapitalizationStatistics(
            score=self._weighted_score(
                [
                    (conversion_rate, self.advantage_weight_conversion_rate),
                    (eval_preservation, self.advantage_weight_eval_preservation),
                    (low_blunder_rate, self.advantage_weight_low_blunder_rate),
                ]
            ),
            conversion_rate_from_plus_2=conversion_rate,
            conversion_rate_from_plus_5=self._safe_mean(plus_5_results),
            average_eval_drop_after_getting_advantage=self._safe_mean(eval_drops),
            number_of_moves_to_convert=self._safe_mean(moves_to_convert),
            winning_position_blunder_rate=winning_position_blunder_rate,
            eval_preservation_when_ahead=eval_preservation,
            low_blunder_rate_when_ahead=low_blunder_rate,
            winning_game_count=len(plus_2_results),
            clearly_winning_game_count=len(plus_5_results),
            winning_move_count=winning_move_count,
        )

    def _resourcefulness_statistics(
        self,
        games: list[EnrichedGame],
        username_key: str,
    ) -> ResourcefulnessStatistics:
        worse_results: list[float] = []
        lost_results: list[float] = []
        recoveries: list[float] = []
        opponent_error_count = 0
        opponent_error_samples = 0
        collapse_count = 0
        survival_lengths: list[float] = []
        worse_move_count = 0

        for game in games:
            target_moves = self._target_moves(game, username_key)
            worse_moves = [
                move for move in target_moves if self._eval_for_player(move) is not None
                and self._eval_for_player(move) <= self.worse_eval_cp
            ]
            lost_moves = [
                move for move in target_moves if self._eval_for_player(move) is not None
                and self._eval_for_player(move) <= self.lost_eval_cp
            ]
            result = self._target_result_score(game, username_key)
            if worse_moves and result is not None:
                worse_results.append(
                    self.result_score_win
                    if result >= self.result_score_draw
                    else self.result_score_loss
                )
            if lost_moves and result is not None:
                lost_results.append(
                    self.result_score_win
                    if result >= self.result_score_draw
                    else self.result_score_loss
                )

            worse_move_count += len(worse_moves)
            collapse_count += sum(1 for move in worse_moves if self._is_blunder(move))
            recoveries.extend(
                recovery
                for move in worse_moves
                for recovery in [self._win_prob_recovery(move)]
                if recovery is not None
            )
            survival = self._survival_before_collapse(target_moves, worse_moves)
            if survival is not None:
                survival_lengths.append(survival)

            target_color = self._target_color(game, username_key)
            for index, move in enumerate(game.moves[:-1]):
                if move.player_color != target_color:
                    continue
                if (
                    self._eval_for_player(move) is None
                    or self._eval_for_player(move) > self.worse_eval_cp
                ):
                    continue
                next_move = game.moves[index + 1]
                if next_move.player_color == target_color:
                    continue
                opponent_error_samples += 1
                next_loss = self._win_prob_loss(next_move)
                if next_loss is not None and next_loss >= self.opponent_error_win_prob_loss:
                    opponent_error_count += 1

        save_rate = self._safe_mean(worse_results)
        eval_recovery_rate = self._safe_mean(recoveries)
        low_collapse_rate = (
            self._clamp01(1.0 - collapse_count / worse_move_count)
            if worse_move_count
            else None
        )

        return ResourcefulnessStatistics(
            score=self._weighted_score(
                [
                    (save_rate, self.resourcefulness_weight_save_rate),
                    (eval_recovery_rate, self.resourcefulness_weight_eval_recovery),
                    (
                        low_collapse_rate,
                        self.resourcefulness_weight_low_collapse_rate,
                    ),
                ]
            ),
            save_rate_from_minus_2=save_rate,
            draw_or_win_rate_from_lost_positions=self._safe_mean(lost_results),
            eval_recovery_rate=eval_recovery_rate,
            opponent_error_inducement_rate=(
                opponent_error_count / opponent_error_samples
                if opponent_error_samples
                else None
            ),
            survival_moves_before_collapse=self._safe_mean(survival_lengths),
            low_collapse_rate_when_worse=low_collapse_rate,
            worse_game_count=len(worse_results),
            lost_game_count=len(lost_results),
            worse_move_count=worse_move_count,
        )

    def _game_bucket_losses(
        self,
        game: EnrichedGame,
        username_key: str,
        min_samples: int,
        complexity_p85: Optional[float],
    ) -> dict[str, float]:
        predicates: dict[str, Callable[[EnrichedMove], bool]] = {
            "tactical": lambda move: "tactical" in move.position_type_tags,
            "calculation": lambda move: (
                complexity_p85 is not None
                and move.complexity is not None
                and move.complexity > complexity_p85
            ),
            "opening": lambda move: move.phase == "opening",
            "quiet_middlegame": lambda move: move.quiet_middlegame,
            "endgame": lambda move: move.phase == "endgame",
            "time_pressure": lambda move: (
                move.clock_before is not None
                and move.clock_before < self.time_pressure_seconds
            ),
            "advantage": lambda move: (
                self._eval_for_player(move) is not None
                and self._eval_for_player(move) >= self.winning_eval_cp
            ),
            "worse_position": lambda move: (
                self._eval_for_player(move) is not None
                and self._eval_for_player(move) <= self.worse_eval_cp
            ),
        }
        bucket_losses: dict[str, float] = {}
        target_moves = self._target_moves(game, username_key)
        for bucket, predicate in predicates.items():
            losses = [
                loss
                for move in target_moves
                if predicate(move)
                for loss in [self._win_prob_loss(move)]
                if loss is not None
            ]
            if len(losses) >= min_samples:
                bucket_losses[bucket] = self._mean(losses)

        return bucket_losses

    def _post_loss_improvement(
        self,
        games: list[EnrichedGame],
        username_key: str,
        min_samples: int,
    ) -> Optional[float]:
        opportunities = 0
        improvements = 0
        for previous_game, next_game in zip(games, games[1:]):
            if self._target_result_score(previous_game, username_key) != self.result_score_loss:
                continue
            previous_loss = self._game_average_loss(previous_game, username_key, min_samples)
            next_loss = self._game_average_loss(next_game, username_key, min_samples)
            if previous_loss is None or next_loss is None:
                continue
            opportunities += 1
            if previous_loss - next_loss >= self.improvement_delta:
                improvements += 1

        if not opportunities:
            return None

        return improvements / opportunities

    def _game_average_loss(
        self,
        game: EnrichedGame,
        username_key: str,
        min_samples: int,
    ) -> Optional[float]:
        losses = [
            loss
            for move in self._target_moves(game, username_key)
            for loss in [self._win_prob_loss(move)]
            if loss is not None
        ]
        if len(losses) < min_samples:
            return None

        return self._mean(losses)

    def _average_time_spent_by_complexity(
        self,
        moves: list[EnrichedMove],
        complexity_p50: Optional[float],
        complexity_p85: Optional[float],
        complexity_p90: Optional[float],
    ) -> dict[str, Optional[float]]:
        buckets: dict[str, list[float]] = {
            "simple": [],
            "normal": [],
            "complex": [],
            "high_complexity": [],
        }
        for move in moves:
            if move.clock_spent is None:
                continue
            bucket = self._complexity_bucket(
                move,
                complexity_p50,
                complexity_p85,
                complexity_p90,
            )
            if bucket is not None:
                buckets[bucket].append(move.clock_spent)

        return {bucket: self._safe_mean(values) for bucket, values in buckets.items()}

    @staticmethod
    def _complexity_bucket(
        move: EnrichedMove,
        complexity_p50: Optional[float],
        complexity_p85: Optional[float],
        complexity_p90: Optional[float],
    ) -> Optional[str]:
        if move.complexity is None:
            return None
        if complexity_p50 is None or complexity_p85 is None or complexity_p90 is None:
            return None
        if move.complexity > complexity_p90:
            return "high_complexity"
        if move.complexity > complexity_p85:
            return "complex"
        if move.complexity < complexity_p50:
            return "simple"
        return "normal"

    def _survival_before_collapse(
        self,
        target_moves: list[EnrichedMove],
        worse_moves: list[EnrichedMove],
    ) -> Optional[float]:
        if not worse_moves:
            return None

        start = target_moves.index(worse_moves[0])
        for offset, move in enumerate(target_moves[start:], start=0):
            if self._is_blunder(move):
                return float(offset)

        return float(len(target_moves) - start)

    def _target_moves(self, game: EnrichedGame, username_key: str) -> list[EnrichedMove]:
        target_color = self._target_color(game, username_key)
        if target_color is None:
            return []

        return [move for move in game.moves if move.player_color == target_color]

    def _target_color(self, game: EnrichedGame, username_key: str) -> Optional[str]:
        if self._username_key(game.white_username) == username_key:
            return "white"
        if self._username_key(game.black_username) == username_key:
            return "black"

        for move in game.moves:
            if self._username_key(move.player_username) == username_key:
                return move.player_color

        return None

    def _target_result_score(
        self,
        game: EnrichedGame,
        username_key: str,
    ) -> Optional[float]:
        target_color = self._target_color(game, username_key)
        if target_color == "white":
            return self._chesscom_result_score(game.white_result, game.result, "white")
        if target_color == "black":
            return self._chesscom_result_score(game.black_result, game.result, "black")
        return None

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
    def _username_key(username: Optional[str]) -> str:
        return (username or "").strip().lower()

    @staticmethod
    def _sort_games_by_time(games: list[EnrichedGame]) -> list[EnrichedGame]:
        sorted_items = sorted(
            enumerate(games),
            key=lambda item: (
                item[1].end_time is None,
                item[1].end_time if item[1].end_time is not None else 0,
                item[0],
            ),
        )
        return [game for _, game in sorted_items]

    @staticmethod
    def _win_prob_loss(move: EnrichedMove) -> Optional[float]:
        if move.win_prob_loss is None:
            return None

        return max(0.0, move.win_prob_loss)

    @staticmethod
    def _win_prob_recovery(move: EnrichedMove) -> Optional[float]:
        if move.win_prob_before is None or move.win_prob_after is None:
            return None

        return max(0.0, move.win_prob_after - move.win_prob_before)

    @staticmethod
    def _eval_for_player(move: EnrichedMove) -> Optional[int]:
        if move.eval_before_cp is None:
            return None

        return move.eval_before_cp if move.player_color == "white" else -move.eval_before_cp

    @staticmethod
    def _eval_after_for_player(move: EnrichedMove) -> Optional[int]:
        if move.eval_after_cp is None:
            return None

        return move.eval_after_cp if move.player_color == "white" else -move.eval_after_cp

    def _eval_drop_for_player(self, move: EnrichedMove) -> Optional[float]:
        eval_before = self._eval_for_player(move)
        eval_after = self._eval_after_for_player(move)
        if eval_before is None or eval_after is None:
            return None

        return float(max(0, eval_before - eval_after))

    def _is_blunder(self, move: EnrichedMove) -> bool:
        loss = self._win_prob_loss(move)
        return loss is not None and loss >= self.blunder_win_prob_loss

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

    @staticmethod
    def _required_value(hparams: dict[str, Any], dotted_path: str) -> Any:
        current: Any = hparams
        for part in dotted_path.split("."):
            if not isinstance(current, dict) or part not in current:
                raise ValueError(f"Missing required hparam: {dotted_path}")
            current = current[part]

        return current

    @classmethod
    def _required_float(cls, hparams: dict[str, Any], dotted_path: str) -> float:
        value = cls._required_value(hparams, dotted_path)
        if not isinstance(value, (int, float)):
            raise ValueError(f"Hparam must be numeric: {dotted_path}")

        return float(value)

    @classmethod
    def _required_int(cls, hparams: dict[str, Any], dotted_path: str) -> int:
        value = cls._required_value(hparams, dotted_path)
        if not isinstance(value, int):
            raise ValueError(f"Hparam must be an integer: {dotted_path}")

        return value

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> Optional[float]:
        if not values:
            return None

        sorted_values = sorted(values)
        if len(sorted_values) == 1:
            return float(sorted_values[0])

        rank = (percentile / 100.0) * (len(sorted_values) - 1)
        lower = int(rank)
        upper = min(lower + 1, len(sorted_values) - 1)
        fraction = rank - lower
        return float(
            sorted_values[lower]
            + (sorted_values[upper] - sorted_values[lower]) * fraction
        )

    @staticmethod
    def _mean(values: list[float]) -> float:
        return sum(values) / len(values)

    def _safe_mean(self, values: list[float]) -> Optional[float]:
        if not values:
            return None

        return self._mean(values)

    @staticmethod
    def _rate(values: list[EnrichedMove], predicate: Callable[[EnrichedMove], bool]) -> float:
        if not values:
            return 0.0

        return sum(1 for value in values if predicate(value)) / len(values)

    def _weighted_score(self, components: list[tuple[Optional[float], float]]) -> Optional[float]:
        if any(value is None for value, _ in components):
            return None

        return self._clamp01(
            sum((value or 0.0) * weight for value, weight in components)
        )

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, value))
