from __future__ import annotations

import unittest

from utils.game_enrichment_transformer import (
    EnginePositionInfo,
    GameEnrichmentTransformer,
)


class CountingTransformer(GameEnrichmentTransformer):
    def __init__(self):
        super().__init__(stockfish_path="unused")
        self.rich_analysis_calls = 0

    def _analyse_position_rich(self, *, engine, board):
        self.rich_analysis_calls += 1
        return EnginePositionInfo(
            eval_cp=0,
            best_move_uci=None,
            top_moves=[],
            best_move_cp_gain=0,
            eval_volatility_among_top_engine_lines=0.0,
            low_gap_between_top_moves=0.0,
            forcing_line_depth=0,
            number_of_legal_moves=board.legal_moves.count(),
            complexity=float(board.legal_moves.count()),
            absolute_complexity=0.0,
            engine_top_move_is_forcing=False,
        )

    def _analyse_forced_move(self, *, engine, board, move):
        return 0


def test_transform_game_reuses_after_move_position_as_next_before_position():
    transformer = CountingTransformer()
    game_data = {
        "pgn": '[Result "*"]\n\n1. e4 c5 *',
        "white": {"username": "white", "rating": 1500},
        "black": {"username": "black", "rating": 1500},
    }

    enriched_game = transformer.transform_game(
        game_data=game_data,
        engine=object(),
        position_analysis_cache={},
    )

    assert len(enriched_game.moves) == 2
    assert transformer.rich_analysis_calls == 3


class GameEnrichmentTransformerTests(unittest.TestCase):
    def test_transform_game_reuses_after_move_position_as_next_before_position(self):
        test_transform_game_reuses_after_move_position_as_next_before_position()
