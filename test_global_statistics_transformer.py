from __future__ import annotations

import math
from pathlib import Path
import tempfile
import unittest

from utils.game_enrichment_transformer import EnrichedGame, EnrichedMove
from utils.global_statistics_transformer import GlobalStatisticsTransformer
from utils.statistics_shared import loss_to_skill_score_base2


HPARAMS_PATH = Path("config/global_statistics_hparams.yaml")


def make_transformer(*, min_samples: int = 3) -> GlobalStatisticsTransformer:
    if min_samples == 3:
        return GlobalStatisticsTransformer(HPARAMS_PATH)

    text = HPARAMS_PATH.read_text(encoding="utf-8")
    text = text.replace("min_samples: 3", f"min_samples: {min_samples}", 1)
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as file:
        file.write(text)
        temp_path = file.name

    return GlobalStatisticsTransformer(temp_path)


def make_move(
    *,
    color: str = "white",
    username: str = "alice",
    ply: int = 1,
    loss: float | None = 0.0,
    complexity: float | None = 10.0,
    phase: str = "middlegame",
    tags: list[str] | None = None,
    quiet_middlegame: bool = False,
    clock_before: float | None = None,
    clock_spent: float | None = None,
    eval_before_cp: int | None = 0,
    eval_after_cp: int | None = 0,
    in_opening_book: bool = False,
) -> EnrichedMove:
    return EnrichedMove(
        game_uuid="game",
        game_url=None,
        ply=ply,
        move_number=(ply + 1) // 2,
        player_color=color,
        player_username=username,
        san="e4",
        uci="e2e4",
        fen_before="before",
        fen_after="after",
        eval_before_cp=eval_before_cp,
        eval_after_cp=eval_after_cp,
        eval_best_move_cp=eval_before_cp,
        eval_played_move_cp=eval_after_cp,
        move_cp_loss=None,
        best_move_uci=None,
        top_engine_moves=[],
        best_move_cp_gain=0,
        win_prob_before=0.5,
        win_prob_after=0.5 - loss if loss is not None else None,
        win_prob_loss=loss,
        clock_before=clock_before,
        clock_after=None,
        clock_spent=clock_spent,
        phase=phase,
        position_type_tags=tags or [],
        tactical_position="tactical" in (tags or []),
        quiet_middlegame=quiet_middlegame,
        complexity=complexity,
        number_of_legal_moves=20,
        eval_volatility_among_top_engine_lines=0.0,
        forcing_line_depth=0,
        low_gap_between_top_moves=0.0,
        engine_top_move_is_forcing=False,
        move_is_threat=False,
        is_capture=False,
        is_check=False,
        is_castling=False,
        is_promotion=False,
        in_opening_book=in_opening_book,
        opening_eco="A00" if in_opening_book else None,
        opening_name="Test Opening" if in_opening_book else None,
    )


def make_game(
    moves: list[EnrichedMove],
    *,
    white: str = "alice",
    black: str = "bob",
    white_result: str = "win",
    black_result: str = "resigned",
    result: str = "1-0",
    end_time: int | None = 1,
) -> EnrichedGame:
    return EnrichedGame(
        uuid="game",
        url=None,
        white_username=white,
        black_username=black,
        white_rating=1500,
        black_rating=1500,
        white_result=white_result,
        black_result=black_result,
        result=result,
        time_class="rapid",
        time_control="600",
        rated=True,
        end_time=end_time,
        chesscom_white_accuracy=None,
        chesscom_black_accuracy=None,
        opening_eco=None,
        opening_name=None,
        moves=moves,
    )


def test_loss_to_skill_score_base2_half_life_calibration():
    assert loss_to_skill_score_base2(0.0, 0.05) == 1.0
    assert math.isclose(loss_to_skill_score_base2(0.05, 0.05), 0.5)
    assert math.isclose(loss_to_skill_score_base2(0.10, 0.05), 0.25)
    assert loss_to_skill_score_base2(None, 0.05) is None

    try:
        loss_to_skill_score_base2(0.05, 0.0)
    except ValueError as exc:
        assert "half_life must be positive" in str(exc)
    else:
        raise AssertionError("Expected invalid half_life to raise")


def test_default_half_life_removes_old_low_loss_saturation():
    score = loss_to_skill_score_base2(0.04, 0.045)

    assert score is not None
    assert score < 0.96


def test_generic_loss_scores_filter_target_player_and_clamp_negative_losses():
    game = make_game(
        [
            make_move(ply=1, loss=0.10, tags=["tactical"]),
            make_move(color="black", username="bob", ply=2, loss=0.90, tags=["tactical"]),
            make_move(ply=3, loss=0.20, tags=["tactical"]),
            make_move(ply=5, loss=-0.10, tags=["tactical"]),
        ]
    )

    stats = make_transformer().compute([game], username="ALICE")

    assert stats.target_games_count == 1
    assert stats.target_moves_count == 3
    assert stats.tactics_score.sample_count == 3
    assert math.isclose(stats.tactics_score.average_loss, 0.10)
    assert math.isclose(stats.tactics_score.score, 2 ** (-0.10 / 0.07))


def test_complexity_percentiles_and_calculation_score_use_p85_threshold():
    moves = [
        make_move(ply=i * 2 + 1, complexity=float(i), loss=0.20 if i >= 9 else 0.0)
        for i in range(1, 11)
    ]
    game = make_game(moves)

    stats = make_transformer(min_samples=2).compute([game], username="alice")

    assert math.isclose(stats.complexity_p50, 5.5)
    assert math.isclose(stats.complexity_p85, 8.65)
    assert math.isclose(stats.complexity_p90, 9.1)
    assert stats.calculation_score.sample_count == 2
    assert math.isclose(stats.calculation_score.average_loss, 0.20)
    assert math.isclose(stats.calculation_score.score, 2 ** (-0.20 / 0.06))


def test_opening_score_uses_exact_book_flag_post_opening_stability_and_result():
    game = make_game(
        [
            make_move(ply=1, phase="opening", in_opening_book=True, loss=0.0),
            make_move(ply=3, phase="opening", in_opening_book=True, loss=0.0),
            make_move(ply=5, phase="opening", in_opening_book=False, loss=0.0),
            make_move(ply=7, phase="middlegame", loss=0.10),
            make_move(ply=9, phase="middlegame", loss=0.20),
            make_move(ply=11, phase="middlegame", loss=0.0),
        ]
    )

    transformer = make_transformer()
    stats = transformer.compute([game], username="alice")

    opening = stats.openings_score
    assert math.isclose(opening.book_accuracy, 2 / 3)
    assert math.isclose(opening.eval_stability_after_opening, 0.90)
    assert opening.result_from_opening_positions == 1.0
    assert math.isclose(
        opening.score,
        transformer.opening_weight_book_accuracy * (2 / 3)
        + transformer.opening_weight_eval_stability_after_opening * 0.90
        + transformer.opening_weight_result_from_opening_positions * 1.0,
    )


def test_time_management_penalties_handle_pressure_blunders_and_allocation():
    game = make_game(
        [
            make_move(
                ply=1,
                loss=0.10,
                complexity=100.0,
                tags=["tactical"],
                clock_before=20.0,
                clock_spent=4.0,
            ),
            make_move(
                ply=3,
                loss=0.0,
                complexity=1.0,
                clock_before=100.0,
                clock_spent=40.0,
            ),
            make_move(
                ply=5,
                loss=0.0,
                complexity=50.0,
                clock_before=80.0,
                clock_spent=10.0,
            ),
        ]
    )

    stats = make_transformer(min_samples=1).compute([game], username="alice")

    time_stats = stats.time_management_score
    assert math.isclose(time_stats.time_trouble_frequency, 1 / 3)
    assert time_stats.blunder_rate_in_time_pressure == 1.0
    assert time_stats.critical_position_underthinking_rate == 1.0
    assert time_stats.overthinking_simple_positions_rate == 1.0
    assert math.isclose(
        time_stats.score,
        1.0 - 0.35 * (1 / 3) - 0.35 * 1.0 - 0.30 * 1.0,
    )


def test_black_orientation_for_advantage_and_resourcefulness():
    black_winning_game = make_game(
        [
            make_move(
                color="black",
                username="alice",
                ply=2,
                eval_before_cp=-300,
                eval_after_cp=-280,
                loss=0.02,
            ),
            make_move(
                color="black",
                username="alice",
                ply=4,
                eval_before_cp=-600,
                eval_after_cp=-610,
                loss=0.0,
            ),
        ],
        white="bob",
        black="alice",
        white_result="resigned",
        black_result="win",
        result="0-1",
    )
    black_worse_game = make_game(
        [
            make_move(
                color="black",
                username="alice",
                ply=2,
                eval_before_cp=300,
                eval_after_cp=250,
                loss=0.0,
            ),
            make_move(
                color="black",
                username="alice",
                ply=4,
                eval_before_cp=600,
                eval_after_cp=500,
                loss=0.0,
            ),
        ],
        white="bob",
        black="alice",
        white_result="agreed",
        black_result="agreed",
        result="1/2-1/2",
        end_time=2,
    )

    stats = make_transformer(min_samples=1).compute(
        [black_winning_game, black_worse_game],
        username="alice",
    )

    assert stats.advantage_capitalization_score.conversion_rate_from_plus_2 == 1.0
    assert stats.advantage_capitalization_score.conversion_rate_from_plus_5 == 1.0
    assert stats.resourcefulness_score.save_rate_from_minus_2 == 1.0
    assert stats.resourcefulness_score.draw_or_win_rate_from_lost_positions == 1.0


def test_game_analysis_detects_chronological_weakness_improvement():
    games = [
        make_game(
            [make_move(ply=i * 2 + 1, loss=0.10, tags=["tactical"]) for i in range(3)],
            end_time=1,
        ),
        make_game(
            [make_move(ply=i * 2 + 1, loss=0.10, tags=["tactical"]) for i in range(3)],
            end_time=2,
        ),
        make_game(
            [make_move(ply=i * 2 + 1, loss=0.10, tags=["tactical"]) for i in range(3)],
            end_time=3,
        ),
        make_game(
            [make_move(ply=i * 2 + 1, loss=0.05, tags=["tactical"]) for i in range(3)],
            end_time=4,
        ),
    ]

    stats = make_transformer().compute(games, username="alice")

    analysis = stats.game_analysis_score
    assert analysis.weakness_opportunity_count == 1
    assert analysis.improvement_count == 1
    assert analysis.score == 1.0


def test_scores_are_none_without_required_samples():
    game = make_game([make_move(loss=None, complexity=None)])

    stats = make_transformer().compute([game], username="alice")

    assert stats.tactics_score.score is None
    assert stats.calculation_score.score is None
    assert stats.middlegame_strategy_score.score is None
    assert stats.endgame_score.score is None


def test_missing_hparam_raises_instead_of_using_default():
    text = HPARAMS_PATH.read_text(encoding="utf-8")
    text = text.replace("    book_accuracy: 0.15\n", "", 1)
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as file:
        file.write(text)
        temp_path = file.name

    try:
        GlobalStatisticsTransformer(temp_path)
    except ValueError as exc:
        assert "opening.weights.book_accuracy" in str(exc)
    else:
        raise AssertionError("Expected missing hparam to raise ValueError")


def test_invalid_half_life_hparam_raises_config_error():
    text = HPARAMS_PATH.read_text(encoding="utf-8")
    text = text.replace("  tactics_wp_loss_half_life: 0.07\n", "  tactics_wp_loss_half_life: 0\n", 1)
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as file:
        file.write(text)
        temp_path = file.name

    try:
        GlobalStatisticsTransformer(temp_path)
    except ValueError as exc:
        assert "skill_score_calibration.tactics_wp_loss_half_life must be positive" in str(exc)
    else:
        raise AssertionError("Expected invalid half-life hparam to raise ValueError")


class GlobalStatisticsTransformerTests(unittest.TestCase):
    def test_loss_to_skill_score_base2_half_life_calibration(self):
        test_loss_to_skill_score_base2_half_life_calibration()

    def test_default_half_life_removes_old_low_loss_saturation(self):
        test_default_half_life_removes_old_low_loss_saturation()

    def test_generic_loss_scores_filter_target_player_and_clamp_negative_losses(self):
        test_generic_loss_scores_filter_target_player_and_clamp_negative_losses()

    def test_complexity_percentiles_and_calculation_score_use_p85_threshold(self):
        test_complexity_percentiles_and_calculation_score_use_p85_threshold()

    def test_opening_score_uses_exact_book_flag_post_opening_stability_and_result(self):
        test_opening_score_uses_exact_book_flag_post_opening_stability_and_result()

    def test_time_management_penalties_handle_pressure_blunders_and_allocation(self):
        test_time_management_penalties_handle_pressure_blunders_and_allocation()

    def test_black_orientation_for_advantage_and_resourcefulness(self):
        test_black_orientation_for_advantage_and_resourcefulness()

    def test_game_analysis_detects_chronological_weakness_improvement(self):
        test_game_analysis_detects_chronological_weakness_improvement()

    def test_scores_are_none_without_required_samples(self):
        test_scores_are_none_without_required_samples()

    def test_missing_hparam_raises_instead_of_using_default(self):
        test_missing_hparam_raises_instead_of_using_default()

    def test_invalid_half_life_hparam_raises_config_error(self):
        test_invalid_half_life_hparam_raises_config_error()
