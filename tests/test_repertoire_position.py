from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import chess
import chess.engine
import pytest

from backend import main as api_main
from backend.models import RepertoirePositionRequest
from backend.services import engine_eval_service, repertoire_service
from backend.services.explorer_service import ExplorerService
from backend.services.repertoire_service import RepertoireConfig, repertoire_position, replay_prefix
from backend.settings import settings
from utils.opening_catalog_index import catalog_index
from utils.opening_popularity import position_key


def uci_line(*sans: str) -> list[str]:
    board = chess.Board()
    return [board.push_san(san).uci() for san in sans]


ITALIAN = uci_line("e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5")
# Petrov sideline past the named lines: 5.Qe2 Qe7, White (the opponent) to move.
PETROV_OFF_BOOK = uci_line("e4", "e5", "Nf3", "Nf6", "Nxe5", "d6", "Nf3", "Nxe4", "Qe2", "Qe7")


class FakeEngine:
    """White-view scores: c3 +40, O-O +35, d3 +30, Nc3 +25, b4 -90, everything else -150."""

    id = {"name": "FakeFish"}
    SCORES = {"c2c3": 40, "e1g1": 35, "d2d3": 30, "b1c3": 25, "b2b4": -90}

    def __init__(self):
        self.calls = []

    def _info(self, board, move):
        cp = self.SCORES.get(move.uci(), -150)
        return {"pv": [move], "score": chess.engine.PovScore(chess.engine.Cp(cp), chess.WHITE)}

    def analyse(self, board, limit, multipv=None, root_moves=None):
        self.calls.append({"multipv": multipv, "root_moves": [m.uci() for m in root_moves or []]})
        if root_moves:
            return [self._info(board, move) for move in root_moves][:multipv or 1]
        ordered = sorted(board.legal_moves, key=lambda m: self.SCORES.get(m.uci(), -150), reverse=True)
        return [self._info(board, move) for move in ordered[:multipv]]


class Response:
    def __init__(self, status_code, body=None, headers=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}

    def json(self):
        return self._body


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, *args, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


def explorer(*responses, token="secret"):
    return ExplorerService(
        token=token,
        session=Session(*responses),
        now=lambda: datetime(2026, 11, 12, tzinfo=timezone.utc),
        sleep=lambda _: None,
        lock_wait=0.1,
    )


LIVE_REPLIES = {
    "white": 500, "draws": 100, "black": 400,
    "moves": [
        {"uci": "d2d4", "san": "d4", "white": 300, "draws": 60, "black": 240},
        {"uci": "b1c3", "san": "Nc3", "white": 150, "draws": 30, "black": 120},
        {"uci": "a2a3", "san": "a3", "white": 5, "draws": 1, "black": 4},
    ],
    "opening": {"eco": "C42", "name": "Petrov's Defense: Classical Attack"},
}


def test_own_turn_marks_playable_moves_with_both_rules():
    engine = FakeEngine()
    config = RepertoireConfig(engine_depth=10, cp_tolerance=50, min_eval_cp=-100)
    result = repertoire_position("white", ITALIAN, config=config, explorer=explorer(), engine=engine)

    assert result["status"] == "ready" and result["ownTurn"]
    assert result["popularity"]["source"] == "snapshot"
    assert result["engine"] == {"status": "ready", "depth": 10, "bestMove": "c2c3", "evalCp": 40}
    moves = {m["uci"]: m for m in result["moves"]}
    assert moves["c2c3"]["playable"] and moves["c2c3"]["cpLoss"] == 0
    assert moves["d2d3"]["playable"] and moves["d2d3"]["cpLoss"] == 10
    # b4 is popular enough to list but loses 130 cp.
    assert moves["b2b4"]["playable"] is False and moves["b2b4"]["cpLoss"] == 130
    # Playable moves come first.
    flags = [m["playable"] for m in result["moves"]]
    assert flags == sorted(flags, key=lambda flag: flag is not True)
    # The snapshot's e1h1 and the engine's e1g1 are one move.
    assert len(moves) == len(result["moves"])
    assert "e1h1" not in moves and moves["e1g1"]["share"] > 0.1 and moves["e1g1"]["engineRank"] == 2
    assert result["opening"]["name"].startswith("Italian Game")
    assert result["labPrefixUci"] == ITALIAN


def test_eval_floor_rejects_a_move_within_tolerance():
    engine = FakeEngine()
    config = RepertoireConfig(engine_depth=10, cp_tolerance=500, min_eval_cp=0)
    result = repertoire_position("white", ITALIAN, config=config, explorer=explorer(), engine=engine)
    moves = {m["uci"]: m for m in result["moves"]}
    assert moves["c2c3"]["playable"]
    assert moves["b2b4"]["playable"] is False  # within 500 cp, but -90 for White


def test_opponent_turn_past_the_catalog_uses_live_explorer_without_engine():
    engine = FakeEngine()
    live = explorer(Response(200, LIVE_REPLIES))
    result = repertoire_position("black", PETROV_OFF_BOOK, config=RepertoireConfig(engine_depth=10), explorer=live, engine=engine)

    assert not result["ownTurn"] and result["status"] == "ready"
    assert result["popularity"]["source"] == "live" and result["popularity"]["totalGames"] == 1000
    # Shares are over the 910 games the listed moves cover; a3 (1%) is under the 2% floor.
    assert [(m["san"], round(m["share"], 2)) for m in result["moves"]] == [("d4", 0.66), ("Nc3", 0.33)]
    assert result["engine"]["status"] == "skipped" and engine.calls == []
    assert result["labPrefixUci"] is None
    # Deepest catalogued name along the path, not the Explorer's.
    assert result["opening"]["exact"] is False and result["opening"]["ply"] < len(PETROV_OFF_BOOK)


def test_transposition_points_the_lab_at_the_catalogued_move_order():
    transposed = uci_line("Nf3", "d5", "d4")
    result = repertoire_position("white", transposed, explorer=explorer(), engine=FakeEngine(), config=RepertoireConfig(engine_depth=10))
    lab = result["labPrefixUci"]
    assert lab is not None
    assert position_key(replay_prefix(lab)[-1]) == result["epd"]


def test_catalog_index_names_and_prefixes():
    index = catalog_index(str(settings.openings_path))
    board = replay_prefix(uci_line("e4", "e5", "Nf3", "Nf6"))[-1]
    assert index.opening_at(board).name.startswith("Russian Game") or index.opening_at(board).name.startswith("Petrov")
    assert index.lab_prefix_for(board) == tuple(uci_line("e4", "e5", "Nf3", "Nf6"))


def test_rate_limited_explorer_answers_pending():
    result = repertoire_position(
        "black", PETROV_OFF_BOOK, explorer=explorer(Response(429, headers={"Retry-After": "12"})), engine=FakeEngine(),
    )
    assert result["status"] == "pending" and result["retryAfter"] == 12
    assert result["moves"] == [] and result["popularity"]["status"] == "pending"


def test_busy_engine_answers_pending_with_known_shares():
    config = RepertoireConfig(engine_depth=10, engine_wait_seconds=0)
    assert engine_eval_service._engine_lock.acquire()
    try:
        result = repertoire_position("white", ITALIAN, config=config, explorer=explorer(), engine=FakeEngine())
    finally:
        engine_eval_service._engine_lock.release()
    assert result["status"] == "pending" and result["engine"]["status"] == "pending"
    assert result["retryAfter"] == repertoire_service.ENGINE_BUSY_RETRY_SECONDS
    assert result["moves"] and all(m["playable"] is None for m in result["moves"])


def test_without_engine_moves_have_no_verdict(monkeypatch):
    monkeypatch.setattr(settings.__class__, "stockfish_path", property(lambda self: None))
    result = repertoire_position("white", ITALIAN, config=RepertoireConfig(engine_depth=10), explorer=explorer())
    assert result["status"] == "ready" and result["engine"]["status"] == "unavailable"
    assert result["moves"] and all(m["playable"] is None for m in result["moves"])


def test_illegal_prefix_is_rejected():
    with pytest.raises(ValueError, match="illegal"):
        replay_prefix(["e2e4", "e2e4"])


def test_route_validates_and_serializes(monkeypatch):
    monkeypatch.setattr(repertoire_service, "get_explorer_service", lambda: explorer())
    # White's repertoire with Black to move: an opponent turn, so no engine search.
    body = RepertoirePositionRequest.model_validate({"color": "white", "prefixUci": uci_line("e4", "e5", "Nf3")})
    response = asyncio.run(api_main.repertoire_position_route(body))
    assert response.ownTurn is False and response.sideToMove == "black"
    assert response.popularity.source == "snapshot"
    assert "b8c6" in [move.uci for move in response.moves]
