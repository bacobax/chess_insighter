from __future__ import annotations

from datetime import datetime, timedelta, timezone

import chess
import chess.engine
import pytest
import requests

from backend.services import engine_eval_service
from backend.services.engine_eval_service import EngineUnavailable, cached_evaluation, evaluate_position
from backend.services.explorer_service import ExplorerService
from utils.lichess_explorer import (
    ExplorerAuthRejected,
    ExplorerRateLimited,
    ExplorerResponseError,
    ExplorerTransientError,
    normalized_moves,
    request_explorer_position,
)


PAYLOAD = {
    "white": 60,
    "draws": 10,
    "black": 30,
    "moves": [
        {"uci": "e2e4", "san": "e4", "white": 30, "draws": 5, "black": 15, "averageRating": 1650},
        {"uci": "d2d4", "san": "d4", "white": 20, "draws": 5, "black": 15, "averageRating": 1700},
    ],
    "opening": None,
    "topGames": [],
    "recentGames": [],
}


class Response:
    def __init__(self, status_code, body=None, headers=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class Clock:
    def __init__(self):
        self.t = 1000.0
        self.slept = []

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.t += seconds


NOW = datetime(2026, 11, 12, tzinfo=timezone.utc)


def service(session, clock=None, token="secret", now=NOW):
    clock = clock or Clock()
    return ExplorerService(token=token, session=session, monotonic=clock, now=lambda: now, sleep=clock.sleep, lock_wait=0.1)


# --- shared client -------------------------------------------------------------

def test_request_sends_cohort_and_token():
    session = Session(Response(200, PAYLOAD))
    assert request_explorer_position(chess.Board(), session=session, token="t", since="2024-10", until="2026-09") == PAYLOAD
    call = session.calls[0]
    assert call["headers"]["Authorization"] == "Bearer t"
    assert call["params"]["speeds"] == "blitz,rapid"
    assert call["params"]["since"] == "2024-10" and call["params"]["topGames"] == 0


@pytest.mark.parametrize(
    "response, error",
    [
        (Response(429, headers={"Retry-After": "7"}), ExplorerRateLimited),
        (Response(503), ExplorerTransientError),
        (requests.ConnectionError("boom"), ExplorerTransientError),
        (Response(401), ExplorerAuthRejected),
        (Response(400), ExplorerResponseError),
        (Response(200, ValueError("bad json")), ExplorerResponseError),
    ],
)
def test_request_raises_typed_errors(response, error):
    with pytest.raises(error) as raised:
        request_explorer_position(chess.Board(), session=Session(response), token="t", since="a", until="b")
    if error is ExplorerRateLimited:
        assert raised.value.retry_after == 7.0


def test_normalized_moves_shares_add_up():
    moves, total, covered = normalized_moves(PAYLOAD)
    assert total == 100 and covered == 90
    assert [round(m["share"], 3) for m in moves] == [0.556, 0.444]


# --- explorer service ------------------------------------------------------------

def test_service_fetches_once_then_serves_cache():
    session = Session(Response(200, PAYLOAD))
    explorer = service(session)
    first = explorer.position(chess.Board())
    assert first.status == "ready" and first.total_games == 100
    assert [m.san for m in first.moves] == ["e4", "d4"]
    assert first.moves[0].average_rating == 1650
    assert session.calls[0]["params"]["until"] == "2026-10"

    # A second process-wide instance reads the shared MongoDB cache.
    again = service(Session()).position(chess.Board())
    assert again.status == "ready" and again.moves == first.moves
    assert len(session.calls) == 1


def test_rate_limit_answers_pending_without_new_requests():
    clock = Clock()
    session = Session(Response(429, headers={"Retry-After": "30"}), Response(200, PAYLOAD))
    explorer = service(session, clock)
    board = chess.Board()
    pending = explorer.position(board)
    assert pending.status == "pending" and pending.retry_after == 30

    clock.t += 10
    still = explorer.position(board)
    assert still.status == "pending" and still.retry_after == 20
    assert len(session.calls) == 1

    clock.t += 25
    assert explorer.position(board).status == "ready"
    assert len(session.calls) == 2


def test_requests_are_spaced_by_min_interval():
    clock = Clock()
    session = Session(Response(200, PAYLOAD), Response(200, PAYLOAD))
    explorer = service(session, clock)
    board = chess.Board()
    explorer.position(board)
    board.push_uci("e2e4")
    explorer.position(board)
    assert clock.slept == [pytest.approx(1.0)]


def test_stale_cache_is_refreshed_and_served_when_refresh_fails():
    service(Session(Response(200, PAYLOAD))).position(chess.Board())
    later = NOW + timedelta(days=120)

    stale = service(Session(Response(503)), now=later).position(chess.Board())
    assert stale.status == "ready" and stale.stale

    fresher = {**PAYLOAD, "white": 70}
    refreshed = service(Session(Response(200, fresher)), now=later).position(chess.Board())
    assert refreshed.total_games == 110 and not refreshed.stale


def test_without_token_is_unavailable_and_never_calls_out():
    session = Session()
    result = service(session, token=None).position(chess.Board())
    assert result.status == "unavailable" and "LICHESS_API_TOKEN" in result.message
    assert session.calls == []


def test_rejected_token_is_unavailable():
    result = service(Session(Response(403))).position(chess.Board())
    assert result.status == "unavailable"


def test_castling_is_normalized_to_the_engine_form():
    board = chess.Board("r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
    payload = {**PAYLOAD, "moves": [{"uci": "e1h1", "san": "O-O", "white": 3, "draws": 0, "black": 1}]}
    result = service(Session(Response(200, payload))).position(board)
    assert [m.uci for m in result.moves] == ["e1g1"]


def test_missing_san_is_derived_from_the_board():
    payload = {**PAYLOAD, "moves": [{"uci": "g1f3", "white": 1, "draws": 0, "black": 0}]}
    result = service(Session(Response(200, payload))).position(chess.Board())
    assert result.moves[0].san == "Nf3"


# --- engine evaluations ------------------------------------------------------------

class FakeEngine:
    """Scores from White's view: e4 +40, d4 +30, Nf3 +25, c4 +20, then 0."""

    id = {"name": "FakeFish"}
    SCORES = {"e2e4": 40, "d2d4": 30, "g1f3": 25, "c2c4": 20}

    def __init__(self):
        self.calls = []

    def _info(self, board, move):
        cp = self.SCORES.get(move.uci(), -60)
        score = chess.engine.PovScore(chess.engine.Cp(cp), chess.WHITE)
        return {"pv": [move], "score": score}

    def analyse(self, board, limit, multipv=None, root_moves=None):
        self.calls.append({"multipv": multipv, "root_moves": [m.uci() for m in root_moves or []]})
        if root_moves:
            return [self._info(board, move) for move in root_moves][:multipv or 1]
        ordered = sorted(board.legal_moves, key=lambda m: self.SCORES.get(m.uci(), -60), reverse=True)
        return [self._info(board, move) for move in ordered[:multipv]]


def test_evaluation_ranks_top_moves_and_computes_cp_loss():
    engine = FakeEngine()
    result = evaluate_position(chess.Board(), depth=12, multipv=3, engine=engine)
    assert result.best_move == "e2e4" and result.engine == "FakeFish"
    assert [m.uci for m in result.ranked()] == ["e2e4", "d2d4", "g1f3"]
    assert result.cp_loss("d2d4") == 10
    assert result.cp_loss("c2c4") is None
    assert engine.calls == [{"multipv": 3, "root_moves": []}]


def test_extra_moves_are_searched_alone_and_cached():
    engine = FakeEngine()
    evaluate_position(chess.Board(), depth=12, multipv=3, engine=engine)
    result = evaluate_position(chess.Board(), moves=["c2c4", "e2e4", "a2a3", "e7e5"], depth=12, multipv=3, engine=engine)
    # e2e4 was already known; c2c4 and a2a3 are new (one restricted search); e7e5 is illegal.
    assert engine.calls[1:] == [{"multipv": 2, "root_moves": ["c2c4", "a2a3"]}]
    assert result.cp_loss("c2c4") == 20 and result.cp_loss("a2a3") == 100
    assert result.moves["c2c4"].rank is None and result.moves["e2e4"].rank == 1

    # Everything cached now: no engine needed.
    cached = evaluate_position(chess.Board(), moves=["c2c4"], depth=12, multipv=3, engine=None)
    assert cached.cp_loss("c2c4") == 20
    assert cached_evaluation(chess.Board(), depth=12) is not None
    assert cached_evaluation(chess.Board(), depth=18) is None


def test_scores_are_from_the_side_to_move():
    board = chess.Board()
    board.push_uci("e2e4")
    engine = FakeEngine()
    result = evaluate_position(board, depth=12, multipv=2, engine=engine)
    # Every Black reply scores -60 for White, i.e. +60 for Black.
    assert all(move.cp == 60 for move in result.moves.values())


def test_missing_stockfish_raises(monkeypatch):
    monkeypatch.setattr(engine_eval_service.settings.__class__, "stockfish_path", property(lambda self: None))
    with pytest.raises(EngineUnavailable):
        evaluate_position(chess.Board(), depth=12)
