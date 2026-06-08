from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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
        return PlayerStatisticsBundle(
            global_statistics=global_statistics,
            player_samples=player_samples,
            castling_summaries=castling_summaries,
            player_profile=player_profile,
            matcher_ready_player_vector=player_opening_vector(player_profile),
        )
