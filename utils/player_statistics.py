from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import chess

from utils.game_enrichment_transformer import EnrichedGame
from utils.global_statistics_transformer import GlobalStatistics
from utils.global_statistics_transformer import GlobalStatisticsTransformer
from utils.player_feature_transformer import (
    GameCastlingSummary,
    PlayerFeatureAggregator,
    PlayerMoveSample,
    PlayerProfile,
    PlayerSampleBuilder,
    player_opening_vector,
)
from utils.statistics_shared import DEFAULT_GLOBAL_STATISTICS_HPARAMS_PATH


@dataclass(frozen=True)
class PlayerStatisticsBundle:
    global_statistics: GlobalStatistics
    player_samples: list[PlayerMoveSample]
    castling_summaries: list[GameCastlingSummary]
    player_profile: PlayerProfile
    matcher_ready_player_vector: dict[str, Optional[float]]
    player_profiles_by_color: dict[str, PlayerProfile]
    matcher_ready_player_vectors: dict[str, dict[str, Optional[float]]]


class PlayerStatisticsBuilder:
    def __init__(
        self,
        hparams_path: str | Path = DEFAULT_GLOBAL_STATISTICS_HPARAMS_PATH,
    ):
        self.hparams_path = Path(hparams_path)
        self.global_transformer = GlobalStatisticsTransformer(self.hparams_path)
        self.sample_builder = PlayerSampleBuilder(self.hparams_path)
        self.feature_aggregator = PlayerFeatureAggregator(self.hparams_path)

    def build(
        self,
        enriched_games: list[EnrichedGame],
        player_name: str,
    ) -> PlayerStatisticsBundle:
        global_statistics = self.global_transformer.compute(
            enriched_games,
            username=player_name,
        )
        player_samples, castling_summaries = self.sample_builder.build(
            enriched_games,
            player_name=player_name,
        )
        player_profile = self.feature_aggregator.aggregate(
            player_samples,
            castling_summaries,
            player_name=player_name,
        )
        white_profile = self.feature_aggregator.aggregate(
            [sample for sample in player_samples if sample.player_color == chess.WHITE],
            [summary for summary in castling_summaries if summary.player_color == chess.WHITE],
            player_name=player_name,
        )
        black_profile = self.feature_aggregator.aggregate(
            [sample for sample in player_samples if sample.player_color == chess.BLACK],
            [summary for summary in castling_summaries if summary.player_color == chess.BLACK],
            player_name=player_name,
        )
        player_profiles_by_color = {
            "white": white_profile,
            "black": black_profile,
            "both": player_profile,
        }
        matcher_ready_player_vectors = {
            color: player_opening_vector(profile)
            for color, profile in player_profiles_by_color.items()
        }
        return PlayerStatisticsBundle(
            global_statistics=global_statistics,
            player_samples=player_samples,
            castling_summaries=castling_summaries,
            player_profile=player_profile,
            matcher_ready_player_vector=player_opening_vector(player_profile),
            player_profiles_by_color=player_profiles_by_color,
            matcher_ready_player_vectors=matcher_ready_player_vectors,
        )
