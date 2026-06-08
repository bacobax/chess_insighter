from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable, Iterable, Optional

import chess

from utils.game_enrichment_transformer import EnrichedGame, EnrichedMove
from utils.opening_feature_transformer import (
    castling_side,
    center_state_scores,
    doubled_pawns,
    isolated_pawns,
    king_safety_risk_for_color,
    material_imbalance_score,
    open_files,
    passed_pawns,
    pawn_structure_signature,
    semi_open_files,
)


STYLE_VECTOR_V1 = {
    "tactical_exposure",
    "tactical_position_choice",
    "tactical_move_choice",
    "tactical_creation_rate",
    "tactical_defusal_rate",
    "quiet_exposure",
    "quiet_choice",
    "quiet_creation_rate",
    "complexity_exposure",
    "complexity_choice",
    "complexity_delta",
    "high_complexity_choice_rate",
    "king_safety_risk_tolerance",
    "king_risk_delta",
    "early_castling_tendency",
    "opposite_side_castling_tendency",
    "queenside_castling_tendency",
    "pawn_structure_sharpness",
    "material_imbalance_preference",
    "endgame_frequency",
    "endgame_move_share",
    "opening_diversity",
    "opening_diversity_white",
    "opening_diversity_black",
    "structure_diversity",
}


SKILL_VECTOR_V1 = {
    "tactical_performance",
    "quiet_position_performance",
    "complexity_performance",
    "king_safety_performance",
    "pawn_structure_comfort",
    "material_imbalance_comfort",
    "endgame_performance",
    "advantage_capitalization",
    "resourcefulness",
}


CONFIDENCE_TARGETS = {
    "opening_diversity": 50,
    "opening_diversity_white": 50,
    "opening_diversity_black": 50,
    "structure_diversity": 50,
    "endgame_performance": 30,
    "tactical_performance": 300,
    "quiet_position_performance": 300,
    "complexity_performance": 200,
    "king_safety_performance": 100,
    "material_imbalance_comfort": 100,
    "pawn_structure_comfort": 100,
    "advantage_capitalization": 30,
    "resourcefulness": 30,
}


PLAYER_TO_OPENING_MAP = {
    "tactical_density": "tactical_position_choice",
    "quiet_position_density": "quiet_choice",
    "king_safety_risk": "king_safety_risk_tolerance",
    "early_castling_tendency": "early_castling_tendency",
    "opposite_side_castling_tendency": "opposite_side_castling_tendency",
    "middlegame_complexity": "complexity_choice",
    "pawn_structure_sharpness": "pawn_structure_sharpness",
    "material_imbalance": "material_imbalance_preference",
    "endgame_likelihood_proxy": "endgame_frequency",
    "structure_diversity": "structure_diversity",
}


@dataclass(frozen=True)
class PlayerMoveSample:
    game_id: str
    player_name: str
    player_color: chess.Color
    ply: int
    move_number: int
    move_uci: str
    san: Optional[str]
    opening_name: Optional[str]
    eco: Optional[str]
    descriptor_before: Any
    descriptor_after: Optional[Any]
    result: str
    player_score: Optional[float]
    cp_loss: Optional[float] = None
    wp_loss: Optional[float] = None
    player_wp_before: Optional[float] = None
    player_wp_after: Optional[float] = None
    player_cp_before: Optional[float] = None
    player_cp_after: Optional[float] = None


@dataclass(frozen=True)
class GameCastlingSummary:
    game_id: str
    player_color: chess.Color
    player_castled: bool
    player_castle_side: Optional[str]
    player_castle_move_number: Optional[int]
    opponent_castled: bool
    opponent_castle_side: Optional[str]
    opponent_castle_move_number: Optional[int]


@dataclass(frozen=True)
class PlayerProfile:
    player_name: str
    games_analyzed: int
    moves_analyzed: int
    style_vector: dict[str, Optional[float]]
    skill_vector: dict[str, Optional[float]]
    subfeatures: dict[str, Any]
    confidence: dict[str, float]


def mean_bool(values: Iterable[Optional[bool]]) -> Optional[float]:
    items = [value for value in values if value is not None]
    if not items:
        return None
    return sum(1.0 for value in items if value) / len(items)


def safe_mean(values: Iterable[Optional[float]]) -> Optional[float]:
    items = [float(value) for value in values if value is not None]
    if not items:
        return None
    return sum(items) / len(items)


def normalize_loss_wp(mean_wp_loss: float) -> float:
    return clamp01(1.0 - min(max(0.0, mean_wp_loss) / 0.25, 1.0))


def normalize_loss_cp(mean_cp_loss: float) -> float:
    return clamp01(1.0 - min(max(0.0, mean_cp_loss) / 300.0, 1.0))


def weighted_mean_available(
    values: dict[str, Optional[float]],
    weights: dict[str, float],
) -> Optional[float]:
    total_weight = sum(weights[key] for key, value in values.items() if value is not None and key in weights)
    if total_weight <= 0:
        return None
    return sum(
        float(value) * weights[key] / total_weight
        for key, value in values.items()
        if value is not None and key in weights
    )


def sample_confidence(n: int, target: int) -> float:
    if target <= 0:
        return 1.0 if n > 0 else 0.0
    return clamp01(n / target)


def player_opening_vector(profile: PlayerProfile) -> dict[str, Optional[float]]:
    return {
        opening_field: profile.style_vector.get(player_field)
        for opening_field, player_field in PLAYER_TO_OPENING_MAP.items()
    }


class PlayerSampleBuilder:
    def build(
        self,
        games: list[EnrichedGame],
        player_name: str,
    ) -> tuple[list[PlayerMoveSample], list[GameCastlingSummary]]:
        username_key = _username_key(player_name)
        samples: list[PlayerMoveSample] = []
        castling_summaries: list[GameCastlingSummary] = []

        for index, game in enumerate(games):
            player_color_name = self._target_color(game, username_key)
            if player_color_name is None:
                continue

            game_id = self._game_id(game, index)
            player_color = color_from_name(player_color_name)
            player_score = self._target_result_score(game, player_color_name)
            castling_summaries.append(self._castling_summary(game, game_id, player_color))

            for move_index, move in enumerate(game.moves):
                if move.player_color != player_color_name:
                    continue

                descriptor_after = None
                if move_index + 1 < len(game.moves):
                    candidate = game.moves[move_index + 1]
                    if getattr(candidate, "fen_before", None) == getattr(move, "fen_after", None):
                        descriptor_after = candidate

                samples.append(
                    PlayerMoveSample(
                        game_id=game_id,
                        player_name=player_name,
                        player_color=player_color,
                        ply=move.ply,
                        move_number=move.move_number,
                        move_uci=move.uci,
                        san=move.san,
                        opening_name=move.opening_name or game.opening_name,
                        eco=move.opening_eco or game.opening_eco,
                        descriptor_before=move,
                        descriptor_after=descriptor_after,
                        result=game.result or "unknown",
                        player_score=player_score,
                        cp_loss=float(move.move_cp_loss) if move.move_cp_loss is not None else None,
                        wp_loss=move.win_prob_loss,
                        player_wp_before=move.win_prob_before,
                        player_wp_after=move.win_prob_after,
                        player_cp_before=oriented_cp(move.eval_before_cp, player_color),
                        player_cp_after=oriented_cp(move.eval_after_cp, player_color),
                    )
                )

        return samples, castling_summaries

    @staticmethod
    def _game_id(game: EnrichedGame, index: int) -> str:
        return game.uuid or game.url or f"game-{index + 1}"

    @staticmethod
    def _target_color(game: EnrichedGame, username_key: str) -> Optional[str]:
        if _username_key(game.white_username) == username_key:
            return "white"
        if _username_key(game.black_username) == username_key:
            return "black"
        for move in game.moves:
            if _username_key(move.player_username) == username_key:
                return move.player_color
        return None

    @staticmethod
    def _target_result_score(game: EnrichedGame, color_name: str) -> Optional[float]:
        chesscom_result = game.white_result if color_name == "white" else game.black_result
        if chesscom_result == "win":
            return 1.0
        if chesscom_result in {"checkmated", "resigned", "timeout", "abandoned", "lose"}:
            return 0.0
        if chesscom_result in {"agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"}:
            return 0.5
        if game.result == "1/2-1/2":
            return 0.5
        if game.result == "1-0":
            return 1.0 if color_name == "white" else 0.0
        if game.result == "0-1":
            return 1.0 if color_name == "black" else 0.0
        return None

    @staticmethod
    def _castling_summary(
        game: EnrichedGame,
        game_id: str,
        player_color: chess.Color,
    ) -> GameCastlingSummary:
        data: dict[chess.Color, dict[str, Any]] = {
            chess.WHITE: {"castled": False, "side": None, "move_number": None},
            chess.BLACK: {"castled": False, "side": None, "move_number": None},
        }

        for move in game.moves:
            if not move.is_castling:
                continue
            color = color_from_name(move.player_color)
            data[color]["castled"] = True
            data[color]["move_number"] = move.move_number
            data[color]["side"] = normalized_castling_side(_castling_side_from_fen(move.fen_after, color))

        opponent = not player_color
        return GameCastlingSummary(
            game_id=game_id,
            player_color=player_color,
            player_castled=data[player_color]["castled"],
            player_castle_side=data[player_color]["side"],
            player_castle_move_number=data[player_color]["move_number"],
            opponent_castled=data[opponent]["castled"],
            opponent_castle_side=data[opponent]["side"],
            opponent_castle_move_number=data[opponent]["move_number"],
        )


class PlayerFeatureAggregator:
    def aggregate(
        self,
        samples: list[PlayerMoveSample],
        castling_summaries: Optional[list[GameCastlingSummary]] = None,
        player_name: Optional[str] = None,
    ) -> PlayerProfile:
        castling_summaries = castling_summaries or []
        player_name = player_name or (samples[0].player_name if samples else "")
        games = sorted({sample.game_id for sample in samples})
        middlegame_samples = [
            sample for sample in samples if descriptor_phase(sample.descriptor_before) == "middlegame"
        ]
        middlegame_with_after = [
            sample
            for sample in middlegame_samples
            if sample.descriptor_after is not None
        ]
        complexity_scale = complexity_percentile(
            [
                raw_complexity
                for sample in middlegame_samples
                for raw_complexity in [
                    descriptor_complexity_raw(sample.descriptor_before),
                    descriptor_complexity_raw(sample.descriptor_after),
                ]
                if raw_complexity is not None
            ],
            95,
        )

        style_vector = self._style_vector(
            samples,
            middlegame_samples,
            middlegame_with_after,
            castling_summaries,
            complexity_scale,
        )
        skill_vector, skill_counts = self._skill_vector(
            samples,
            middlegame_samples,
            complexity_scale,
        )

        subfeatures = self._subfeatures(samples, middlegame_samples, castling_summaries)
        subfeatures["complexity_scale_p95"] = complexity_scale
        subfeatures["matcher_vector"] = {
            opening_field: style_vector.get(player_field)
            for opening_field, player_field in PLAYER_TO_OPENING_MAP.items()
        }
        subfeatures["skill_sample_counts"] = skill_counts

        confidence = PlayerConfidenceEstimator().estimate(
            samples=samples,
            middlegame_samples=middlegame_samples,
            middlegame_with_after=middlegame_with_after,
            castling_summaries=castling_summaries,
            complexity_scale=complexity_scale,
            style_vector=style_vector,
            skill_vector=skill_vector,
            skill_counts=skill_counts,
            subfeatures=subfeatures,
        )

        return PlayerProfile(
            player_name=player_name,
            games_analyzed=len(games),
            moves_analyzed=len(samples),
            style_vector=style_vector,
            skill_vector=skill_vector,
            subfeatures=subfeatures,
            confidence=confidence,
        )

    def _style_vector(
        self,
        samples: list[PlayerMoveSample],
        middlegame_samples: list[PlayerMoveSample],
        middlegame_with_after: list[PlayerMoveSample],
        castling_summaries: list[GameCastlingSummary],
        complexity_scale: Optional[float],
    ) -> dict[str, Optional[float]]:
        before_tactical = [descriptor_tactical(sample.descriptor_before) for sample in middlegame_samples]
        after_tactical = [descriptor_tactical(sample.descriptor_after) for sample in middlegame_with_after]
        before_quiet = [descriptor_quiet(sample.descriptor_before) for sample in middlegame_samples]
        after_quiet = [descriptor_quiet(sample.descriptor_after) for sample in middlegame_with_after]

        before_complexities = [
            descriptor_complexity(sample.descriptor_before, complexity_scale)
            for sample in middlegame_samples
        ]
        after_complexities = [
            descriptor_complexity(sample.descriptor_after, complexity_scale)
            for sample in middlegame_with_after
        ]

        before_king_risks = [
            get_player_king_safety(sample.descriptor_before, sample.player_color)
            for sample in middlegame_samples
        ]
        risk_deltas = [
            difference(
                get_player_king_safety(sample.descriptor_after, sample.player_color),
                get_player_king_safety(sample.descriptor_before, sample.player_color),
            )
            for sample in middlegame_with_after
        ]

        opening_diversity, opening_white, opening_black, opening_distributions = opening_diversities(samples)
        structure_diversity, _structure_distribution = structure_diversity_from_samples(middlegame_samples)
        pawn_subfeatures = pawn_structure_subfeatures(middlegame_samples)
        material_subfeatures = material_imbalance_subfeatures(middlegame_samples)

        total_games = len({sample.game_id for sample in samples})
        endgame_games = {
            sample.game_id
            for sample in samples
            if descriptor_phase(sample.descriptor_before) == "endgame"
        }
        endgame_moves = [
            sample for sample in samples if descriptor_phase(sample.descriptor_before) == "endgame"
        ]

        return {
            "tactical_exposure": mean_bool(before_tactical),
            "tactical_position_choice": mean_bool(after_tactical),
            "tactical_move_choice": mean_bool(tactical_move_choice(sample) for sample in middlegame_samples),
            "tactical_creation_rate": transition_rate(
                middlegame_with_after,
                lambda sample: not descriptor_tactical(sample.descriptor_before),
                lambda sample: descriptor_tactical(sample.descriptor_after),
            ),
            "tactical_defusal_rate": transition_rate(
                middlegame_with_after,
                lambda sample: descriptor_tactical(sample.descriptor_before),
                lambda sample: not descriptor_tactical(sample.descriptor_after),
            ),
            "quiet_exposure": mean_bool(before_quiet),
            "quiet_choice": mean_bool(after_quiet),
            "quiet_creation_rate": transition_rate(
                middlegame_with_after,
                lambda sample: not descriptor_quiet(sample.descriptor_before),
                lambda sample: descriptor_quiet(sample.descriptor_after),
            ),
            "complexity_exposure": safe_mean(before_complexities),
            "complexity_choice": safe_mean(after_complexities),
            "complexity_delta": safe_mean(
                difference(
                    descriptor_complexity(sample.descriptor_after, complexity_scale),
                    descriptor_complexity(sample.descriptor_before, complexity_scale),
                )
                for sample in middlegame_with_after
            ),
            "high_complexity_choice_rate": mean_bool(
                (
                    None
                    if raw_value is None or complexity_scale is None
                    else raw_value >= complexity_scale
                )
                for sample in middlegame_with_after
                for raw_value in [descriptor_complexity_raw(sample.descriptor_after)]
            ) if middlegame_with_after else None,
            "king_safety_risk_tolerance": safe_mean(before_king_risks),
            "king_risk_delta": safe_mean(risk_deltas),
            "early_castling_tendency": safe_mean(
                castling_earliness_score(summary.player_castle_move_number)
                for summary in castling_summaries
            ),
            "opposite_side_castling_tendency": mean_bool(
                summary.player_castled
                and summary.opponent_castled
                and summary.player_castle_side != summary.opponent_castle_side
                for summary in castling_summaries
            ),
            "queenside_castling_tendency": mean_bool(
                summary.player_castle_side == "queenside" for summary in castling_summaries
            ),
            "pawn_structure_sharpness": pawn_subfeatures["pawn_structure_sharpness"],
            "material_imbalance_preference": material_subfeatures["material_imbalance_preference"],
            "endgame_frequency": len(endgame_games) / total_games if total_games else None,
            "endgame_move_share": len(endgame_moves) / len(samples) if samples else None,
            "opening_diversity": opening_diversity,
            "opening_diversity_white": opening_white,
            "opening_diversity_black": opening_black,
            "structure_diversity": structure_diversity,
        }

    def _skill_vector(
        self,
        samples: list[PlayerMoveSample],
        middlegame_samples: list[PlayerMoveSample],
        complexity_scale: Optional[float],
    ) -> tuple[dict[str, Optional[float]], dict[str, int]]:
        tactical_samples = [
            sample for sample in middlegame_samples if descriptor_tactical(sample.descriptor_before)
        ]
        quiet_samples = [
            sample for sample in middlegame_samples if descriptor_quiet(sample.descriptor_before)
        ]
        complex_samples = [
            sample
            for sample in middlegame_samples
            if complexity_scale is not None
            and (descriptor_complexity_raw(sample.descriptor_before) or 0.0) >= complexity_scale
        ]
        king_risk_samples = [
            sample
            for sample in middlegame_samples
            if (get_player_king_safety(sample.descriptor_before, sample.player_color) or 0.0) >= 0.65
        ]
        material_samples = [
            sample for sample in middlegame_samples if has_material_imbalance(sample.descriptor_before)
        ]
        endgame_samples = [
            sample for sample in samples if descriptor_phase(sample.descriptor_before) == "endgame"
        ]

        pawn_comfort_values = pawn_structure_comfort_values(middlegame_samples)
        pawn_structure_comfort = safe_mean(pawn_comfort_values.values())
        advantage, advantage_count = advantage_capitalization(samples)
        resource, resource_count = resourcefulness(samples)

        skill_vector = {
            "tactical_performance": performance_score(tactical_samples),
            "quiet_position_performance": performance_score(quiet_samples),
            "complexity_performance": performance_score(complex_samples),
            "king_safety_performance": performance_score(king_risk_samples),
            "pawn_structure_comfort": pawn_structure_comfort,
            "material_imbalance_comfort": performance_score(material_samples),
            "endgame_performance": endgame_performance(samples, endgame_samples),
            "advantage_capitalization": advantage,
            "resourcefulness": resource,
        }
        counts = {
            "tactical_performance": loss_sample_count(tactical_samples),
            "quiet_position_performance": loss_sample_count(quiet_samples),
            "complexity_performance": loss_sample_count(complex_samples),
            "king_safety_performance": loss_sample_count(king_risk_samples),
            "pawn_structure_comfort": sum(
                1 for sample in middlegame_samples if get_player_pawn_structure(sample.descriptor_before, sample.player_color)
            ),
            "material_imbalance_comfort": loss_sample_count(material_samples),
            "endgame_performance": loss_sample_count(endgame_samples),
            "advantage_capitalization": advantage_count,
            "resourcefulness": resource_count,
        }
        return skill_vector, counts

    @staticmethod
    def _subfeatures(
        samples: list[PlayerMoveSample],
        middlegame_samples: list[PlayerMoveSample],
        castling_summaries: list[GameCastlingSummary],
    ) -> dict[str, Any]:
        opening_diversity, opening_white, opening_black, opening_distributions = opening_diversities(samples)
        structure_diversity, structure_distribution = structure_diversity_from_samples(middlegame_samples)
        pawn_subfeatures = pawn_structure_subfeatures(middlegame_samples)
        material_subfeatures = material_imbalance_subfeatures(middlegame_samples)
        return {
            "opening_diversity": opening_diversity,
            "opening_diversity_white": opening_white,
            "opening_diversity_black": opening_black,
            "opening_distribution": opening_distributions["all"],
            "opening_distribution_white": opening_distributions["white"],
            "opening_distribution_black": opening_distributions["black"],
            "structure_diversity": structure_diversity,
            "structure_distribution": structure_distribution,
            "pawn_structure": pawn_subfeatures,
            "pawn_structure_comfort": pawn_structure_comfort_values(middlegame_samples),
            "material_imbalance": material_subfeatures,
            "castling_summaries": castling_summaries,
            "sample_counts": {
                "games": len({sample.game_id for sample in samples}),
                "moves": len(samples),
                "middlegame_moves": len(middlegame_samples),
                "descriptor_after": sum(1 for sample in samples if sample.descriptor_after is not None),
            },
        }


class PlayerConfidenceEstimator:
    def estimate(
        self,
        *,
        samples: list[PlayerMoveSample],
        middlegame_samples: list[PlayerMoveSample],
        middlegame_with_after: list[PlayerMoveSample],
        castling_summaries: list[GameCastlingSummary],
        complexity_scale: Optional[float],
        style_vector: dict[str, Optional[float]],
        skill_vector: dict[str, Optional[float]],
        skill_counts: dict[str, int],
        subfeatures: dict[str, Any],
    ) -> dict[str, float]:
        games = len({sample.game_id for sample in samples})
        endgame_samples = [
            sample for sample in samples if descriptor_phase(sample.descriptor_before) == "endgame"
        ]
        structure_games = sum(subfeatures.get("structure_distribution", {}).values())
        confidence: dict[str, float] = {}

        style_counts = {
            "tactical_exposure": len(middlegame_samples),
            "tactical_position_choice": len(middlegame_with_after),
            "tactical_move_choice": len(middlegame_samples),
            "tactical_creation_rate": len(middlegame_with_after),
            "tactical_defusal_rate": len(middlegame_with_after),
            "quiet_exposure": len(middlegame_samples),
            "quiet_choice": len(middlegame_with_after),
            "quiet_creation_rate": len(middlegame_with_after),
            "complexity_exposure": count_available(
                descriptor_complexity(sample.descriptor_before, complexity_scale)
                for sample in middlegame_samples
            ),
            "complexity_choice": count_available(
                descriptor_complexity(sample.descriptor_after, complexity_scale)
                for sample in middlegame_with_after
            ),
            "complexity_delta": count_available(
                difference(
                    descriptor_complexity(sample.descriptor_after, complexity_scale),
                    descriptor_complexity(sample.descriptor_before, complexity_scale),
                )
                for sample in middlegame_with_after
            ),
            "high_complexity_choice_rate": count_available(
                descriptor_complexity_raw(sample.descriptor_after)
                for sample in middlegame_with_after
            ),
            "king_safety_risk_tolerance": count_available(
                get_player_king_safety(sample.descriptor_before, sample.player_color)
                for sample in middlegame_samples
            ),
            "king_risk_delta": count_available(
                difference(
                    get_player_king_safety(sample.descriptor_after, sample.player_color),
                    get_player_king_safety(sample.descriptor_before, sample.player_color),
                )
                for sample in middlegame_with_after
            ),
            "early_castling_tendency": len(castling_summaries),
            "opposite_side_castling_tendency": len(castling_summaries),
            "queenside_castling_tendency": len(castling_summaries),
            "pawn_structure_sharpness": count_available(
                get_player_pawn_structure(sample.descriptor_before, sample.player_color)
                for sample in middlegame_samples
            ),
            "material_imbalance_preference": len(middlegame_samples),
            "endgame_frequency": games,
            "endgame_move_share": len(samples),
            "opening_diversity": games,
            "opening_diversity_white": sum(1 for sample in unique_game_samples(samples) if sample.player_color == chess.WHITE),
            "opening_diversity_black": sum(1 for sample in unique_game_samples(samples) if sample.player_color == chess.BLACK),
            "structure_diversity": structure_games,
        }
        style_targets = {
            "opening_diversity": CONFIDENCE_TARGETS["opening_diversity"],
            "opening_diversity_white": CONFIDENCE_TARGETS["opening_diversity_white"],
            "opening_diversity_black": CONFIDENCE_TARGETS["opening_diversity_black"],
            "structure_diversity": CONFIDENCE_TARGETS["structure_diversity"],
            "endgame_frequency": 30,
            "endgame_move_share": 100,
            "king_safety_risk_tolerance": 100,
            "king_risk_delta": 100,
            "pawn_structure_sharpness": 100,
            "material_imbalance_preference": 100,
            "complexity_exposure": 200,
            "complexity_choice": 200,
            "complexity_delta": 200,
            "high_complexity_choice_rate": 200,
            "early_castling_tendency": 50,
            "opposite_side_castling_tendency": 50,
            "queenside_castling_tendency": 50,
        }
        for feature in STYLE_VECTOR_V1:
            target = style_targets.get(feature, 300)
            confidence[feature] = (
                sample_confidence(style_counts.get(feature, 0), target)
                if style_vector.get(feature) is not None
                else 0.0
            )

        for feature in SKILL_VECTOR_V1:
            target = CONFIDENCE_TARGETS.get(feature, 100)
            count = skill_counts.get(feature, 0)
            if feature == "endgame_performance" and skill_vector.get(feature) is not None:
                count = max(count, len(endgame_samples))
            confidence[feature] = (
                sample_confidence(count, target)
                if skill_vector.get(feature) is not None
                else 0.0
            )

        return confidence


def descriptor_phase(descriptor: Any) -> Optional[str]:
    value = get_field(descriptor, "phase")
    return str(value).lower() if value is not None else None


def descriptor_tactical(descriptor: Any) -> Optional[bool]:
    if descriptor is None:
        return None
    value = get_field(descriptor, "tactical_position")
    if value is not None:
        return bool(value)
    tags = get_field(descriptor, "position_type_tags") or get_field(descriptor, "tags")
    if tags is not None:
        return "tactical" in tags
    return None


def descriptor_quiet(descriptor: Any) -> Optional[bool]:
    if descriptor is None:
        return None
    value = get_field(descriptor, "quiet_middlegame")
    if value is not None:
        return bool(value)
    tags = get_field(descriptor, "position_type_tags") or get_field(descriptor, "tags")
    if tags is not None:
        return "quiet_middlegame" in tags
    return None


def descriptor_complexity(descriptor: Any, scale: Optional[float] = None) -> Optional[float]:
    raw = descriptor_complexity_raw(descriptor)
    if raw is None:
        return None
    return normalize_complexity(raw, scale)


def descriptor_complexity_raw(descriptor: Any) -> Optional[float]:
    if descriptor is None:
        return None
    raw = get_field(descriptor, "complexity")
    if raw is None:
        return None
    return float(raw)


def normalize_complexity(value: float, scale: Optional[float] = None) -> float:
    if 0.0 <= value <= 1.0:
        return clamp01(value)
    if scale is None or scale <= 0:
        return clamp01(value / 100.0)
    return clamp01(value / scale)


def complexity_percentile(values: list[float], percentile: float) -> Optional[float]:
    if not values:
        return None
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (percentile / 100.0) * (len(sorted_values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = rank - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


def tactical_move_choice(sample: PlayerMoveSample) -> Optional[bool]:
    descriptor = sample.descriptor_before
    indicators = [
        get_field(descriptor, "is_capture"),
        get_field(descriptor, "is_check"),
        get_field(descriptor, "is_promotion"),
        get_field(descriptor, "move_is_threat"),
    ]
    san = sample.san or get_field(descriptor, "san")
    if san:
        san_is_tactical = any(marker in str(san) for marker in ["+", "#", "x"])
        if san_is_tactical:
            return True
    if any(value is not None for value in indicators):
        return any(bool(value) for value in indicators if value is not None)
    return None


def get_player_king_safety(descriptor: Any, player_color: chess.Color) -> Optional[float]:
    if descriptor is None:
        return None
    for field in [
        "player_king_safety_risk",
        "king_safety_risk",
        "king_risk",
        "king_safety",
    ]:
        value = get_field(descriptor, field)
        if value is not None:
            return clamp01(float(value))

    board = board_from_descriptor(descriptor)
    if board is None:
        return None
    side = castling_side(board.king(player_color))
    castled = side is not None
    move_number = int(get_field(descriptor, "move_number") or board.fullmove_number)
    return king_safety_risk_for_color(board, player_color, move_number, castled)


def get_player_pawn_structure(descriptor: Any, player_color: chess.Color) -> Optional[dict[str, Optional[float]]]:
    board = board_from_descriptor(descriptor)
    if board is None:
        return None
    open_center_score, closed_center_score = center_state_scores(board)
    return {
        "isolated_pawn": 1.0 if isolated_pawns(board, player_color) > 0 else 0.0,
        "doubled_pawn": 1.0 if doubled_pawns(board, player_color) > 0 else 0.0,
        "backward_pawn": None,
        "passed_pawn": 1.0 if passed_pawns(board, player_color) > 0 else 0.0,
        "open_center": open_center_score,
        "closed_center": closed_center_score,
        "semi_open_file": 1.0 if semi_open_files(board, player_color) > 0 else 0.0,
        "open_file": 1.0 if open_files(board) > 0 else 0.0,
    }


def has_material_imbalance(descriptor: Any) -> Optional[bool]:
    score = material_imbalance_value(descriptor)
    return score is not None and score > 0.05


def material_imbalance_value(descriptor: Any) -> Optional[float]:
    value = get_field(descriptor, "material_imbalance")
    if value is not None:
        return clamp01(float(value))
    board = board_from_descriptor(descriptor)
    if board is None:
        return None
    return material_imbalance_score(board)


def get_player_material_imbalance_details(descriptor: Any, player_color: chess.Color) -> dict[str, Optional[float]]:
    board = board_from_descriptor(descriptor)
    if board is None:
        return {}
    opponent = not player_color
    player_rooks = len(board.pieces(chess.ROOK, player_color))
    opponent_rooks = len(board.pieces(chess.ROOK, opponent))
    player_bishops = len(board.pieces(chess.BISHOP, player_color))
    opponent_bishops = len(board.pieces(chess.BISHOP, opponent))
    player_queens = len(board.pieces(chess.QUEEN, player_color))
    opponent_queens = len(board.pieces(chess.QUEEN, opponent))
    return {
        "bishop_pair": 1.0 if player_bishops >= 2 and opponent_bishops < 2 else 0.0,
        "exchange_down": 1.0 if player_rooks < opponent_rooks else 0.0,
        "exchange_up": 1.0 if player_rooks > opponent_rooks else 0.0,
        "queenless_middlegame": 1.0 if player_queens + opponent_queens == 0 and descriptor_phase(descriptor) == "middlegame" else 0.0,
    }


def pawn_structure_subfeatures(samples: list[PlayerMoveSample]) -> dict[str, Optional[float]]:
    keys = [
        "isolated_pawn",
        "doubled_pawn",
        "backward_pawn",
        "passed_pawn",
        "open_center",
        "closed_center",
        "semi_open_file",
    ]
    exposures = {
        f"{key}_exposure": safe_mean(
            (structure or {}).get(key)
            for sample in samples
            for structure in [get_player_pawn_structure(sample.descriptor_before, sample.player_color)]
        )
        for key in keys
    }
    choices = {
        f"{key}_choice": safe_mean(
            (structure or {}).get(key)
            for sample in samples
            if sample.descriptor_after is not None
            for structure in [get_player_pawn_structure(sample.descriptor_after, sample.player_color)]
        )
        for key in keys
    }
    creation = {}
    for key in ["isolated_pawn", "doubled_pawn", "passed_pawn"]:
        creation[f"{key}_creation_rate"] = transition_rate(
            [sample for sample in samples if sample.descriptor_after is not None],
            lambda sample, key=key: not truthy_structure(sample.descriptor_before, sample.player_color, key),
            lambda sample, key=key: truthy_structure(sample.descriptor_after, sample.player_color, key),
        )

    structural_damage_rate = safe_mean(
        [
            value
            for key in ["isolated_pawn_creation_rate", "doubled_pawn_creation_rate"]
            for value in [creation.get(key)]
            if value is not None
        ]
    )
    weights = {
        "isolated_pawn_exposure": 0.20,
        "doubled_pawn_exposure": 0.15,
        "backward_pawn_exposure": 0.15,
        "passed_pawn_exposure": 0.20,
        "semi_open_file_exposure": 0.15,
        "open_center_exposure": 0.15,
    }
    result = {**exposures, **choices, **creation}
    result["structural_damage_rate"] = structural_damage_rate
    result["pawn_structure_sharpness"] = weighted_mean_available(result, weights)
    return result


def pawn_structure_comfort_values(samples: list[PlayerMoveSample]) -> dict[str, Optional[float]]:
    comfort: dict[str, Optional[float]] = {}
    for key in ["isolated_pawn", "doubled_pawn", "passed_pawn", "closed_center", "open_center"]:
        comfort[f"{key}_comfort"] = performance_score(
            [
                sample
                for sample in samples
                if truthy_structure(sample.descriptor_before, sample.player_color, key)
            ]
        )
    return comfort


def material_imbalance_subfeatures(samples: list[PlayerMoveSample]) -> dict[str, Optional[float]]:
    with_after = [sample for sample in samples if sample.descriptor_after is not None]
    before = [has_material_imbalance(sample.descriptor_before) for sample in samples]
    after = [has_material_imbalance(sample.descriptor_after) for sample in with_after]
    result: dict[str, Optional[float]] = {
        "material_imbalance_preference": mean_bool(before),
        "material_imbalance_choice": mean_bool(after),
        "material_imbalance_creation_rate": transition_rate(
            with_after,
            lambda sample: not has_material_imbalance(sample.descriptor_before),
            lambda sample: has_material_imbalance(sample.descriptor_after),
        ),
        "material_imbalance_comfort": performance_score(
            [sample for sample in samples if has_material_imbalance(sample.descriptor_before)]
        ),
    }
    for key in ["bishop_pair", "exchange_down", "exchange_up", "queenless_middlegame"]:
        feature_samples = [
            sample
            for sample in samples
            if get_player_material_imbalance_details(sample.descriptor_before, sample.player_color).get(key)
        ]
        result[f"{key}_comfort"] = performance_score(feature_samples)
    return result


def performance_score(samples: list[PlayerMoveSample]) -> Optional[float]:
    wp_losses = [max(0.0, float(sample.wp_loss)) for sample in samples if sample.wp_loss is not None]
    if wp_losses:
        return normalize_loss_wp(sum(wp_losses) / len(wp_losses))
    cp_losses = [max(0.0, float(sample.cp_loss)) for sample in samples if sample.cp_loss is not None]
    if cp_losses:
        return normalize_loss_cp(sum(cp_losses) / len(cp_losses))
    return None


def loss_sample_count(samples: list[PlayerMoveSample]) -> int:
    return sum(1 for sample in samples if sample.wp_loss is not None or sample.cp_loss is not None)


def advantage_capitalization(samples: list[PlayerMoveSample]) -> tuple[Optional[float], int]:
    wp_samples = [sample for sample in samples if sample.player_wp_before is not None and sample.player_wp_before >= 0.65]
    if wp_samples:
        accuracy = performance_score(wp_samples)
        blunder_rate = mean_bool(
            sample.wp_loss is not None and sample.wp_loss >= 0.20 for sample in wp_samples
        )
        conversion_rate = game_rate(
            samples,
            lambda game_samples: any((sample.player_wp_before or 0.0) >= 0.70 for sample in game_samples),
            lambda game_samples: (game_samples[0].player_score if game_samples else None) == 1.0,
        )
        score = weighted_mean_available(
            {
                "accuracy_while_better": accuracy,
                "conversion_rate": conversion_rate,
                "low_blunder_rate": None if blunder_rate is None else 1.0 - blunder_rate,
            },
            {
                "accuracy_while_better": 0.45,
                "conversion_rate": 0.35,
                "low_blunder_rate": 0.20,
            },
        )
        return score, len(wp_samples)

    cp_samples = [sample for sample in samples if sample.player_cp_before is not None and sample.player_cp_before >= 200]
    if not cp_samples:
        return None, 0
    return performance_score(cp_samples), len(cp_samples)


def resourcefulness(samples: list[PlayerMoveSample]) -> tuple[Optional[float], int]:
    wp_samples = [sample for sample in samples if sample.player_wp_before is not None and sample.player_wp_before <= 0.35]
    if wp_samples:
        defensive_accuracy = performance_score(wp_samples)
        recovery_rate = mean_bool(
            sample.player_wp_after is not None
            and sample.player_wp_before is not None
            and sample.player_wp_after - sample.player_wp_before >= 0.05
            for sample in wp_samples
        )
        save_rate = game_rate(
            samples,
            lambda game_samples: any((sample.player_wp_before or 1.0) <= 0.30 for sample in game_samples),
            lambda game_samples: (game_samples[0].player_score if game_samples else None) is not None
            and (game_samples[0].player_score or 0.0) >= 0.5,
        )
        score = weighted_mean_available(
            {
                "defensive_accuracy": defensive_accuracy,
                "recovery_rate": recovery_rate,
                "save_rate": save_rate,
            },
            {
                "defensive_accuracy": 0.40,
                "recovery_rate": 0.30,
                "save_rate": 0.30,
            },
        )
        return score, len(wp_samples)

    cp_samples = [sample for sample in samples if sample.player_cp_before is not None and sample.player_cp_before <= -200]
    if not cp_samples:
        return None, 0
    return performance_score(cp_samples), len(cp_samples)


def endgame_performance(
    all_samples: list[PlayerMoveSample],
    endgame_samples: list[PlayerMoveSample],
) -> Optional[float]:
    endgame_accuracy = performance_score(endgame_samples)
    if endgame_accuracy is None:
        return None
    first_endgame_by_game: dict[str, PlayerMoveSample] = {}
    for sample in endgame_samples:
        first_endgame_by_game.setdefault(sample.game_id, sample)
    if not first_endgame_by_game or all(sample.player_wp_before is None for sample in first_endgame_by_game.values()):
        return endgame_accuracy

    conversion_rate = safe_mean(
        1.0 if sample.player_score == 1.0 else 0.0
        for sample in first_endgame_by_game.values()
        if sample.player_wp_before is not None and sample.player_wp_before >= 0.65 and sample.player_score is not None
    )
    save_rate = safe_mean(
        1.0 if sample.player_score is not None and sample.player_score >= 0.5 else 0.0
        for sample in first_endgame_by_game.values()
        if sample.player_wp_before is not None and sample.player_wp_before <= 0.35 and sample.player_score is not None
    )
    equal_hold_rate = safe_mean(
        1.0 if sample.player_score is not None and sample.player_score >= 0.5 else 0.0
        for sample in first_endgame_by_game.values()
        if sample.player_wp_before is not None
        and 0.45 <= sample.player_wp_before <= 0.55
        and sample.player_score is not None
    )
    return weighted_mean_available(
        {
            "endgame_accuracy": endgame_accuracy,
            "conversion_rate": conversion_rate,
            "save_rate": save_rate,
            "equal_endgame_hold_rate": equal_hold_rate,
        },
        {
            "endgame_accuracy": 0.45,
            "conversion_rate": 0.25,
            "save_rate": 0.20,
            "equal_endgame_hold_rate": 0.10,
        },
    )


def opening_diversities(
    samples: list[PlayerMoveSample],
) -> tuple[Optional[float], Optional[float], Optional[float], dict[str, dict[str, int]]]:
    all_game_samples = unique_game_samples(samples)
    white_game_samples = [sample for sample in all_game_samples if sample.player_color == chess.WHITE]
    black_game_samples = [sample for sample in all_game_samples if sample.player_color == chess.BLACK]
    all_distribution = label_distribution(opening_label(sample) for sample in all_game_samples)
    white_distribution = label_distribution(opening_label(sample) for sample in white_game_samples)
    black_distribution = label_distribution(opening_label(sample) for sample in black_game_samples)
    return (
        diversity_score(all_distribution),
        diversity_score(white_distribution),
        diversity_score(black_distribution),
        {
            "all": all_distribution,
            "white": white_distribution,
            "black": black_distribution,
        },
    )


def structure_diversity_from_samples(samples: list[PlayerMoveSample]) -> tuple[Optional[float], dict[str, int]]:
    by_game: dict[str, list[str]] = {}
    for sample in samples:
        label = structure_label(sample.descriptor_before)
        if label is not None:
            by_game.setdefault(sample.game_id, []).append(label)
    main_structures = [mode(labels) for labels in by_game.values() if labels]
    distribution = label_distribution(main_structures)
    return diversity_score(distribution), distribution


def diversity_score(distribution: dict[str, int]) -> Optional[float]:
    total = sum(distribution.values())
    if total == 0:
        return None
    top_share = max(distribution.values()) / total
    entropy = normalized_entropy(distribution)
    return clamp01(0.70 * entropy + 0.30 * (1.0 - top_share))


def normalized_entropy(distribution: dict[str, int]) -> float:
    total = sum(distribution.values())
    if total <= 1 or len(distribution) <= 1:
        return 0.0
    entropy = 0.0
    for count in distribution.values():
        probability = count / total
        entropy -= probability * math.log(probability)
    return clamp01(entropy / math.log(len(distribution)))


def label_distribution(labels: Iterable[Optional[str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for label in labels:
        if not label:
            continue
        counts[label] = counts.get(label, 0) + 1
    return counts


def mode(labels: list[str]) -> str:
    counts = label_distribution(labels)
    return max(counts, key=lambda key: (counts[key], key))


def opening_label(sample: PlayerMoveSample) -> Optional[str]:
    return sample.opening_name or sample.eco


def structure_label(descriptor: Any) -> Optional[str]:
    explicit = get_field(descriptor, "structure_label")
    if explicit:
        return str(explicit)
    board = board_from_descriptor(descriptor)
    if board is None:
        return None
    return pawn_structure_signature(board)


def unique_game_samples(samples: list[PlayerMoveSample]) -> list[PlayerMoveSample]:
    by_game: dict[str, PlayerMoveSample] = {}
    for sample in samples:
        if sample.game_id not in by_game:
            by_game[sample.game_id] = sample
    return list(by_game.values())


def game_rate(
    samples: list[PlayerMoveSample],
    game_predicate: Callable[[list[PlayerMoveSample]], bool],
    success_predicate: Callable[[list[PlayerMoveSample]], bool],
) -> Optional[float]:
    by_game: dict[str, list[PlayerMoveSample]] = {}
    for sample in samples:
        by_game.setdefault(sample.game_id, []).append(sample)
    selected = [items for items in by_game.values() if game_predicate(items)]
    if not selected:
        return None
    return sum(1.0 for items in selected if success_predicate(items)) / len(selected)


def transition_rate(
    samples: list[PlayerMoveSample],
    before_predicate: Callable[[PlayerMoveSample], Optional[bool]],
    after_predicate: Callable[[PlayerMoveSample], Optional[bool]],
) -> Optional[float]:
    eligible = [sample for sample in samples if before_predicate(sample)]
    if not eligible:
        return None
    return sum(1.0 for sample in eligible if after_predicate(sample)) / len(eligible)


def truthy_structure(descriptor: Any, player_color: chess.Color, key: str) -> Optional[bool]:
    structure = get_player_pawn_structure(descriptor, player_color)
    if structure is None:
        return None
    value = structure.get(key)
    return value is not None and value > 0.0


def castling_earliness_score(move_number: Optional[int]) -> float:
    if move_number is None:
        return 0.0
    if move_number <= 8:
        return 1.0
    if move_number <= 10:
        return 0.8
    if move_number <= 12:
        return 0.6
    if move_number <= 15:
        return 0.3
    return 0.0


def _castling_side_from_fen(fen: str, color: chess.Color) -> Optional[str]:
    try:
        board = chess.Board(fen)
    except ValueError:
        return None
    return castling_side(board.king(color))


def normalized_castling_side(side: Optional[str]) -> Optional[str]:
    if side == "king":
        return "kingside"
    if side == "queen":
        return "queenside"
    return side


def board_from_descriptor(descriptor: Any) -> Optional[chess.Board]:
    if descriptor is None:
        return None
    board = get_field(descriptor, "board")
    if isinstance(board, chess.Board):
        return board
    fen = get_field(descriptor, "fen") or get_field(descriptor, "fen_before")
    if not fen:
        return None
    try:
        return chess.Board(str(fen))
    except ValueError:
        return None


def get_field(obj: Any, field: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


def oriented_cp(cp: Optional[float], player_color: chess.Color) -> Optional[float]:
    if cp is None:
        return None
    return float(cp) if player_color == chess.WHITE else -float(cp)


def color_from_name(color: str) -> chess.Color:
    return chess.WHITE if str(color).lower() == "white" else chess.BLACK


def difference(left: Optional[float], right: Optional[float]) -> Optional[float]:
    if left is None or right is None:
        return None
    return left - right


def count_available(values: Iterable[Any]) -> int:
    return sum(1 for value in values if value is not None)


def _username_key(username: Optional[str]) -> str:
    return (username or "").strip().lower()


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
