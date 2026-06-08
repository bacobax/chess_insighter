from __future__ import annotations

import math
from types import SimpleNamespace
import unittest

import chess

from utils.game_enrichment_transformer import EnrichedGame, EnrichedMove
from utils.player_feature_transformer import (
    GameCastlingSummary,
    PlayerFeatureAggregator,
    PlayerMoveSample,
    PlayerSampleBuilder,
    player_opening_vector,
    sample_confidence,
)


START_FEN = chess.Board().fen()
PAWN_FEN = "8/8/8/2p5/2P1P3/2P5/8/4K2k w - - 0 1"
MATERIAL_FEN = "4k3/8/8/8/8/8/8/2BBK1nn w - - 0 1"
QUEENLESS_FEN = "4k3/8/8/8/8/8/8/4K3 w - - 0 1"


def desc(
    *,
    phase: str = "middlegame",
    tactical: bool = False,
    quiet: bool = False,
    complexity: float | None = 50.0,
    fen: str = START_FEN,
    structure_label: str | None = None,
    is_capture: bool = False,
    is_check: bool = False,
    is_promotion: bool = False,
    move_is_threat: bool = False,
):
    return SimpleNamespace(
        phase=phase,
        tactical_position=tactical,
        quiet_middlegame=quiet,
        complexity=complexity,
        fen_before=fen,
        structure_label=structure_label,
        is_capture=is_capture,
        is_check=is_check,
        is_promotion=is_promotion,
        move_is_threat=move_is_threat,
        move_number=12,
    )


def sample(
    game_id: str,
    before,
    after=None,
    *,
    color=chess.WHITE,
    san: str | None = "e4",
    opening="Opening A",
    eco="A00",
    wp_loss: float | None = 0.0,
    cp_loss: float | None = None,
    wp_before: float | None = 0.5,
    wp_after: float | None = 0.5,
    score: float | None = 0.5,
):
    return PlayerMoveSample(
        game_id=game_id,
        player_name="alice",
        player_color=color,
        ply=1,
        move_number=1,
        move_uci="e2e4",
        san=san,
        opening_name=opening,
        eco=eco,
        descriptor_before=before,
        descriptor_after=after,
        result="1/2-1/2",
        player_score=score,
        cp_loss=cp_loss,
        wp_loss=wp_loss,
        player_wp_before=wp_before,
        player_wp_after=wp_after,
    )


def aggregate(samples, summaries=None):
    return PlayerFeatureAggregator().aggregate(samples, summaries or [], "alice")


def test_tactical_exposure_position_choice_and_move_choice_are_distinct():
    samples = [
        sample("g1", desc(tactical=False), desc(tactical=True), wp_loss=0.05),
        sample(
            "g1",
            desc(tactical=True, is_capture=True),
            desc(tactical=False),
            wp_loss=0.10,
        ),
        sample("g1", desc(tactical=False), desc(tactical=False), san="Qh5+", wp_loss=0.00),
    ]

    profile = aggregate(samples)
    style = profile.style_vector

    assert math.isclose(style["tactical_exposure"], 1 / 3)
    assert math.isclose(style["tactical_position_choice"], 1 / 3)
    assert math.isclose(style["tactical_move_choice"], 2 / 3)
    assert math.isclose(style["tactical_creation_rate"], 1 / 2)
    assert math.isclose(style["tactical_defusal_rate"], 1.0)


def test_quiet_exposure_choice_and_creation():
    samples = [
        sample("g1", desc(quiet=False), desc(quiet=True)),
        sample("g1", desc(quiet=True), desc(quiet=True)),
        sample("g1", desc(quiet=False), desc(quiet=False)),
    ]

    style = aggregate(samples).style_vector

    assert math.isclose(style["quiet_exposure"], 1 / 3)
    assert math.isclose(style["quiet_choice"], 2 / 3)
    assert math.isclose(style["quiet_creation_rate"], 1 / 2)


def test_complexity_normalization_choice_and_delta():
    samples = [
        sample("g1", desc(complexity=50), desc(complexity=80)),
        sample("g1", desc(complexity=100), desc(complexity=120)),
        sample("g1", desc(complexity=150), desc(complexity=200)),
    ]

    profile = aggregate(samples)
    style = profile.style_vector
    p95 = 187.5

    assert math.isclose(profile.subfeatures["complexity_scale_p95"], p95)
    assert math.isclose(style["complexity_exposure"], (50 / p95 + 100 / p95 + 150 / p95) / 3)
    assert math.isclose(style["complexity_choice"], (80 / p95 + 120 / p95 + 1.0) / 3)
    assert math.isclose(style["complexity_delta"], ((80 - 50) / p95 + (120 - 100) / p95 + (1.0 - 150 / p95)) / 3)
    assert math.isclose(style["high_complexity_choice_rate"], 1 / 3)


def test_castling_summaries_drive_castling_tendencies():
    samples = [
        sample("g1", desc(), desc()),
        sample("g2", desc(), desc()),
        sample("g3", desc(), desc()),
    ]
    summaries = [
        GameCastlingSummary("g1", chess.WHITE, True, "kingside", 8, True, "kingside", 9),
        GameCastlingSummary("g2", chess.WHITE, True, "queenside", 12, True, "kingside", 10),
        GameCastlingSummary("g3", chess.WHITE, False, None, None, False, None, None),
    ]

    style = aggregate(samples, summaries).style_vector

    assert math.isclose(style["early_castling_tendency"], (1.0 + 0.6 + 0.0) / 3)
    assert math.isclose(style["opposite_side_castling_tendency"], 1 / 3)
    assert math.isclose(style["queenside_castling_tendency"], 1 / 3)


def test_opening_diversity_overall_and_by_color():
    samples = [
        sample("g1", desc(), desc(), opening="Opening A", color=chess.WHITE),
        sample("g2", desc(), desc(), opening="Opening B", color=chess.WHITE),
        sample("g3", desc(), desc(), opening="Opening A", color=chess.BLACK),
    ]

    style = aggregate(samples).style_vector
    expected_overall = 0.70 * (
        -((2 / 3) * math.log(2 / 3) + (1 / 3) * math.log(1 / 3)) / math.log(2)
    ) + 0.30 * (1 - 2 / 3)

    assert math.isclose(style["opening_diversity"], expected_overall)
    assert math.isclose(style["opening_diversity_white"], 0.85)
    assert math.isclose(style["opening_diversity_black"], 0.0)


def test_structure_diversity_entropy_uses_main_middlegame_structure_per_game():
    samples = [
        sample("g1", desc(structure_label="isolani"), desc()),
        sample("g1", desc(structure_label="isolani"), desc()),
        sample("g2", desc(structure_label="hanging-pawns"), desc()),
    ]

    profile = aggregate(samples)

    assert math.isclose(profile.style_vector["structure_diversity"], 0.85)
    assert profile.subfeatures["structure_distribution"] == {
        "isolani": 1,
        "hanging-pawns": 1,
    }


def test_performance_uses_wp_loss_then_cp_loss_fallback():
    samples = [
        sample("g1", desc(tactical=True), desc(), wp_loss=0.05, cp_loss=250),
        sample("g1", desc(tactical=True), desc(), wp_loss=0.10, cp_loss=250),
        sample(
            "g1",
            desc(quiet=True),
            desc(),
            wp_loss=None,
            cp_loss=150,
            wp_before=None,
            wp_after=None,
        ),
    ]

    skill = aggregate(samples).skill_vector

    assert math.isclose(skill["tactical_performance"], 1.0 - 0.075 / 0.25)
    assert math.isclose(skill["quiet_position_performance"], 0.5)


def test_confidence_scoring():
    assert sample_confidence(25, 100) == 0.25
    assert sample_confidence(100, 100) == 1.0
    assert sample_confidence(200, 100) == 1.0

    profile = aggregate([sample("g1", desc(tactical=True), desc(), wp_loss=0.0)])

    assert math.isclose(profile.confidence["tactical_performance"], 1 / 300)
    assert math.isclose(profile.confidence["tactical_position_choice"], 1 / 300)


def test_pawn_structure_sharpness_and_comfort():
    samples = [
        sample("g1", desc(fen=PAWN_FEN), desc(fen=PAWN_FEN), wp_loss=0.05),
        sample("g1", desc(fen=START_FEN), desc(fen=PAWN_FEN), wp_loss=0.00),
    ]

    profile = aggregate(samples)
    pawn = profile.subfeatures["pawn_structure"]

    assert pawn["isolated_pawn_exposure"] == 0.5
    assert pawn["doubled_pawn_exposure"] == 0.5
    assert pawn["passed_pawn_exposure"] == 0.5
    assert math.isclose(pawn["isolated_pawn_creation_rate"], 1.0)
    assert profile.style_vector["pawn_structure_sharpness"] is not None
    assert profile.skill_vector["pawn_structure_comfort"] is not None


def test_material_imbalance_preference_choice_creation_and_comfort():
    samples = [
        sample("g1", desc(fen=START_FEN), desc(fen=MATERIAL_FEN), wp_loss=0.00),
        sample("g1", desc(fen=MATERIAL_FEN), desc(fen=QUEENLESS_FEN), wp_loss=0.05),
    ]

    profile = aggregate(samples)
    material = profile.subfeatures["material_imbalance"]

    assert math.isclose(profile.style_vector["material_imbalance_preference"], 0.5)
    assert math.isclose(material["material_imbalance_choice"], 1.0)
    assert math.isclose(material["material_imbalance_creation_rate"], 1.0)
    assert material["material_imbalance_comfort"] is not None
    assert profile.skill_vector["material_imbalance_comfort"] is not None


def test_endgame_frequency_move_share_and_performance():
    samples = [
        sample("g1", desc(phase="middlegame"), desc(), wp_loss=0.0, score=1.0),
        sample("g1", desc(phase="endgame"), desc(), wp_loss=0.05, wp_before=0.70, score=1.0),
        sample("g2", desc(phase="middlegame"), desc(), wp_loss=0.0, score=0.0),
    ]

    profile = aggregate(samples)

    assert math.isclose(profile.style_vector["endgame_frequency"], 1 / 2)
    assert math.isclose(profile.style_vector["endgame_move_share"], 1 / 3)
    assert profile.skill_vector["endgame_performance"] is not None


def test_player_profile_output_and_opening_vector_mapping():
    profile = aggregate([sample("g1", desc(tactical=False, quiet=True), desc(tactical=True, quiet=False))])
    vector = player_opening_vector(profile)

    assert profile.player_name == "alice"
    assert profile.games_analyzed == 1
    assert profile.moves_analyzed == 1
    assert vector["tactical_density"] == profile.style_vector["tactical_position_choice"]
    assert vector["quiet_position_density"] == profile.style_vector["quiet_choice"]
    assert profile.subfeatures["matcher_vector"] == vector


def test_sample_builder_creates_samples_and_castling_summary_from_enriched_game():
    white_castle = make_move(
        color="white",
        username="alice",
        ply=1,
        fen_before="before-1",
        fen_after="after-1",
        is_castling=True,
        move_number=8,
        san="O-O",
        uci="e1g1",
    )
    black_reply = make_move(
        color="black",
        username="bob",
        ply=2,
        fen_before="after-1",
        fen_after="after-2",
    )
    game = EnrichedGame(
        uuid="game-1",
        url=None,
        white_username="alice",
        black_username="bob",
        white_rating=1500,
        black_rating=1500,
        white_result="win",
        black_result="resigned",
        result="1-0",
        time_class="rapid",
        time_control="600",
        rated=True,
        end_time=1,
        chesscom_white_accuracy=None,
        chesscom_black_accuracy=None,
        opening_eco="C20",
        opening_name="King's Pawn Game",
        moves=[white_castle, black_reply],
    )

    samples, summaries = PlayerSampleBuilder().build([game], "ALICE")

    assert len(samples) == 1
    assert samples[0].descriptor_before is white_castle
    assert samples[0].descriptor_after is black_reply
    assert samples[0].player_score == 1.0
    assert summaries[0].player_castled is True
    assert summaries[0].player_castle_move_number == 8


def make_move(
    *,
    color: str = "white",
    username: str = "alice",
    ply: int = 1,
    fen_before: str = START_FEN,
    fen_after: str = START_FEN,
    phase: str = "middlegame",
    tactical: bool = False,
    quiet: bool = False,
    is_castling: bool = False,
    move_number: int | None = None,
    san: str = "e4",
    uci: str = "e2e4",
) -> EnrichedMove:
    return EnrichedMove(
        game_uuid="game-1",
        game_url=None,
        ply=ply,
        move_number=move_number or (ply + 1) // 2,
        player_color=color,
        player_username=username,
        san=san,
        uci=uci,
        fen_before=fen_before,
        fen_after=fen_after,
        eval_before_cp=0,
        eval_after_cp=0,
        eval_best_move_cp=0,
        eval_played_move_cp=0,
        move_cp_loss=0,
        best_move_uci=None,
        top_engine_moves=[],
        best_move_cp_gain=0,
        win_prob_before=0.5,
        win_prob_after=0.5,
        win_prob_loss=0.0,
        clock_before=None,
        clock_after=None,
        clock_spent=None,
        phase=phase,
        position_type_tags=[],
        tactical_position=tactical,
        quiet_middlegame=quiet,
        complexity=50.0,
        number_of_legal_moves=20,
        eval_volatility_among_top_engine_lines=0.0,
        forcing_line_depth=0,
        low_gap_between_top_moves=0.0,
        engine_top_move_is_forcing=False,
        move_is_threat=False,
        is_capture=False,
        is_check=False,
        is_castling=is_castling,
        is_promotion=False,
        in_opening_book=True,
        opening_eco="C20",
        opening_name="King's Pawn Game",
    )


class PlayerFeatureTransformerTests(unittest.TestCase):
    def test_tactical_exposure_position_choice_and_move_choice_are_distinct(self):
        test_tactical_exposure_position_choice_and_move_choice_are_distinct()

    def test_quiet_exposure_choice_and_creation(self):
        test_quiet_exposure_choice_and_creation()

    def test_complexity_normalization_choice_and_delta(self):
        test_complexity_normalization_choice_and_delta()

    def test_castling_summaries_drive_castling_tendencies(self):
        test_castling_summaries_drive_castling_tendencies()

    def test_opening_diversity_overall_and_by_color(self):
        test_opening_diversity_overall_and_by_color()

    def test_structure_diversity_entropy_uses_main_middlegame_structure_per_game(self):
        test_structure_diversity_entropy_uses_main_middlegame_structure_per_game()

    def test_performance_uses_wp_loss_then_cp_loss_fallback(self):
        test_performance_uses_wp_loss_then_cp_loss_fallback()

    def test_confidence_scoring(self):
        test_confidence_scoring()

    def test_pawn_structure_sharpness_and_comfort(self):
        test_pawn_structure_sharpness_and_comfort()

    def test_material_imbalance_preference_choice_creation_and_comfort(self):
        test_material_imbalance_preference_choice_creation_and_comfort()

    def test_endgame_frequency_move_share_and_performance(self):
        test_endgame_frequency_move_share_and_performance()

    def test_player_profile_output_and_opening_vector_mapping(self):
        test_player_profile_output_and_opening_vector_mapping()

    def test_sample_builder_creates_samples_and_castling_summary_from_enriched_game(self):
        test_sample_builder_creates_samples_and_castling_summary_from_enriched_game()
