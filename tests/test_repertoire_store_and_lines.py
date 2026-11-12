from __future__ import annotations

import asyncio
from types import SimpleNamespace

import chess
import chess.engine
import pytest

from backend import main as api_main
from backend.models import RepertoireLinesRequest, RepertoireSeedRequest
from backend.services import repertoire_lines as lines_module
from backend.services.explorer_service import ExplorerService
from backend.services.repertoire_lines import LineSettings, repertoire_lines
from backend.services.repertoire_repository import ChoiceNotPlayable, RepertoireStore
from backend.services.repertoire_service import RepertoireConfig, _Popularity
from utils.opening_popularity import position_key


def uci_line(*sans: str) -> list[str]:
    board = chess.Board()
    return [board.push_san(san).uci() for san in sans]


def epd_after(*sans: str) -> str:
    board = chess.Board()
    for san in sans:
        board.push_san(san)
    return position_key(board)


def no_explorer() -> ExplorerService:
    return ExplorerService(token=None)


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


def live_explorer(*responses) -> ExplorerService:
    return ExplorerService(token="secret", session=Session(*responses), sleep=lambda _: None, lock_wait=0.1)


class FakeEngine:
    """White-view scores: e4 +30, d4 +25, Nf3 +20, a4 -60, everything else -20."""

    id = {"name": "FakeFish"}
    SCORES = {"e2e4": 30, "d2d4": 25, "g1f3": 20, "a2a4": -60}

    def _info(self, move):
        cp = self.SCORES.get(move.uci(), -20)
        return {"pv": [move], "score": chess.engine.PovScore(chess.engine.Cp(cp), chess.WHITE)}

    def analyse(self, board, limit, multipv=None, root_moves=None):
        moves = list(root_moves) if root_moves else sorted(board.legal_moves, key=lambda m: self.SCORES.get(m.uci(), -20), reverse=True)
        return [self._info(move) for move in moves[: multipv or 1]]


# --- line walk on a controlled popularity tree ----------------------------------------

def fake_popularity(table: dict[str, tuple[int, list[tuple[str, float]]]]):
    """``epd -> (total games, [(san, share)])``; unknown positions are "pending"."""

    def lookup(board, explorer, *, live=True):
        entry = table.get(position_key(board))
        if entry is None:
            return _Popularity("none", "pending", 0, [])
        total, replies = entry
        moves = []
        for san, share in replies:
            move = board.parse_san(san)
            moves.append({"uci": move.uci(), "san": san, "games": int(total * share), "share": share})
        return _Popularity("snapshot", "ready", total, moves)

    return lookup


TREE = {
    epd_after("e4"): (10_000, [("e5", 0.5), ("c5", 0.3), ("e6", 0.14), ("a6", 0.05), ("h5", 0.01)]),
    epd_after("e4", "c5"): (3_000, [("Nf3", 0.7)]),
    epd_after("e4", "e5", "Nf3"): (5_000, [("Nc6", 0.8), ("Nf6", 0.2)]),
    epd_after("e4", "e5", "Nf3", "Nf6"): (12, [("Nxe5", 1.0)]),
}

CHOICES = {
    epd_after(): {"uci": "e2e4"},
    epd_after("e4", "e5"): {"uci": "g1f3"},
    epd_after("e4", "e5", "Nf3", "Nc6"): {"uci": "f1c4"},
}


def test_walk_stops_on_cap_choice_book_and_cutoff(monkeypatch):
    monkeypatch.setattr(lines_module, "popularity", fake_popularity(TREE))
    result = repertoire_lines(
        "white", CHOICES, line_settings=LineSettings(min_reach=0.06, max_own_moves=3), explorer=no_explorer(), fetch_budget=0,
    )
    by_san = {" ".join(line["san"]): line for line in result["lines"]}
    assert by_san["e4 e5 Nf3 Nc6 Bc4"]["status"] == "complete"
    assert by_san["e4 e5 Nf3 Nc6 Bc4"]["endReason"] == "move_cap"
    assert by_san["e4 e5 Nf3 Nc6 Bc4"]["reach"] == pytest.approx(0.4)
    assert by_san["e4 e5 Nf3 Nf6"]["status"] == "out_of_book"  # 12 games
    assert by_san["e4 c5"]["status"] == "needs_choice"
    assert by_san["e4 e6"]["status"] == "needs_choice"
    assert "e4 a6" not in by_san  # 5% < the 6% reach cutoff
    assert result["coverage"] == {
        "complete": 0.4, "outOfBook": 0.1, "needsChoice": 0.44, "pending": 0.0, "noData": 0.0, "pruned": 0.06,
    }
    assert sum(result["coverage"].values()) == pytest.approx(1.0)
    assert result["choicesUsed"] == 3 and result["status"] == "ready"
    # Most likely first.
    assert [line["reach"] for line in result["lines"]] == sorted((line["reach"] for line in result["lines"]), reverse=True)


def test_walk_reports_pending_when_the_fetch_budget_runs_out(monkeypatch):
    monkeypatch.setattr(lines_module, "popularity", fake_popularity({}))
    result = repertoire_lines("white", CHOICES, explorer=live_explorer(), fetch_budget=0)
    assert result["status"] == "pending" and result["retryAfter"] == 1.0
    assert [(line["san"], line["status"]) for line in result["lines"]] == [(["e4"], "pending")]


# 1.a3 h6 2.h3 a6 3.b3: neither the catalog nor the snapshot knows Black's replies.
ODD_START = uci_line("a3", "h6", "h3", "a6")
UNKNOWN_CHOICE = {epd_after("a3", "h6", "h3", "a6"): {"uci": "b2b3"}}


def unknown_walk(explorer):
    return repertoire_lines("white", UNKNOWN_CHOICE, start_prefix_uci=ODD_START, explorer=explorer, fetch_budget=3)


def test_walk_without_explorer_ends_in_no_data_not_pending():
    result = unknown_walk(no_explorer())
    assert result["status"] == "ready" and result["retryAfter"] is None
    assert [(line["san"][-1], line["status"]) for line in result["lines"]] == [("b3", "no_data")]
    assert result["coverage"]["noData"] == 1.0


def test_walk_with_rejected_token_ends_in_no_data():
    explorer = live_explorer(Response(401))
    result = unknown_walk(explorer)
    assert result["status"] == "ready"
    assert [line["status"] for line in result["lines"]] == ["no_data"]


def test_walk_rate_limit_is_pending_with_its_retry_time():
    explorer = live_explorer(Response(429, headers={"Retry-After": "20"}))
    result = unknown_walk(explorer)
    assert result["status"] == "pending" and result["retryAfter"] == 20
    assert explorer._session.calls == 1


def test_walk_reuses_a_choice_after_a_transposition(monkeypatch):
    table = {
        epd_after("Nf3"): (1000, [("d5", 1.0)]),
        epd_after("Nf3", "d5", "d4"): (1000, [("Nf6", 1.0)]),
    }
    monkeypatch.setattr(lines_module, "popularity", fake_popularity(table))
    # The choice was saved after 1.d4 d5 2.Nf3, reached here as 1.Nf3 d5 2.d4.
    choices = {epd_after(): {"uci": "g1f3"}, epd_after("Nf3", "d5"): {"uci": "d2d4"}, epd_after("d4", "d5", "Nf3", "Nf6"): {"uci": "c2c4"}}
    result = repertoire_lines("white", choices, line_settings=LineSettings(max_own_moves=3), explorer=no_explorer(), fetch_budget=0)
    assert [line["san"] for line in result["lines"]] == [["Nf3", "d5", "d4", "Nf6", "c4"]]


def test_walk_from_a_slot_start(monkeypatch):
    monkeypatch.setattr(lines_module, "popularity", fake_popularity({}))
    result = repertoire_lines("black", {epd_after("e4"): {"uci": "e7e5"}}, start_prefix_uci=uci_line("e4"), explorer=no_explorer(), fetch_budget=0)
    assert result["startPrefixUci"] == ["e2e4"]
    assert result["lines"][0]["san"] == ["e4", "e5"] and result["lines"][0]["status"] == "no_data"


# --- store ---------------------------------------------------------------------------

def test_new_repertoire_is_empty_with_default_settings():
    repertoire = RepertoireStore().get("owner-1", "white")
    assert repertoire["choices"] == {}
    assert repertoire["settings"] == {"cpTolerance": 50, "minEvalCp": -100, "minReach": 0.02, "maxOwnMoves": 10}


def test_choice_is_checked_against_the_engine():
    store = RepertoireStore()
    saved = store.set_choice("owner-1", "white", [], "d2d4", engine=FakeEngine())
    choice = saved["choices"][epd_after()]
    assert choice["san"] == "d4" and choice["cpLoss"] == 5 and choice["source"] == "user"

    with pytest.raises(ChoiceNotPlayable, match="90 cp behind"):
        store.set_choice("owner-1", "white", [], "a2a4", engine=FakeEngine())
    with pytest.raises(ValueError, match="opponent's move"):
        store.set_choice("owner-1", "white", uci_line("e4"), "e7e5", engine=FakeEngine())
    with pytest.raises(ValueError, match="not a legal move"):
        store.set_choice("owner-1", "white", [], "e2e5", engine=FakeEngine())


def test_settings_change_what_is_playable():
    store = RepertoireStore()
    store.update_settings("owner-1", "white", {"cpTolerance": 0})
    with pytest.raises(ChoiceNotPlayable):
        store.set_choice("owner-1", "white", [], "d2d4", engine=FakeEngine())
    with pytest.raises(ValueError, match="Unknown"):
        store.update_settings("owner-1", "white", {"depth": 30})


def test_choices_are_per_account_and_colour_and_removable():
    store = RepertoireStore()
    store.set_choice("owner-1", "white", [], "e2e4", engine=FakeEngine())
    assert store.get("owner-2", "white")["choices"] == {}
    assert store.get("owner-1", "black")["choices"] == {}
    assert store.remove_choice("owner-1", "white", [])["choices"] == {}


def test_seed_fills_gaps_without_overwriting():
    store = RepertoireStore()
    store.set_choice("owner-1", "black", uci_line("d4"), "g8f6", engine=FakeEngine())
    seeded = store.seed("owner-1", "black")
    choices = seeded["choices"]
    assert choices[epd_after("e4")]["san"] == "e5" and choices[epd_after("e4")]["source"] == "seed"
    # The user's 1…Nf6 against 1.d4 is kept over the seed's 1…d5.
    assert choices[epd_after("d4")]["san"] == "Nf6" and choices[epd_after("d4")]["source"] == "user"
    count = len(choices)
    assert len(store.seed("owner-1", "black")["choices"]) == count

    custom = store.seed("owner-2", "white", ["1.d4 d5 2.c4"])["choices"]
    assert [c["san"] for c in custom.values()] == ["d4", "c4"]


# --- routes, with the real snapshot ---------------------------------------------------

def request_for(owner: str):
    return SimpleNamespace(state=SimpleNamespace(auth_user=SimpleNamespace(id=owner)))


def test_seeded_italian_expands_into_lines_from_the_snapshot(monkeypatch):
    monkeypatch.setattr(lines_module, "get_explorer_service", no_explorer)
    request = request_for("owner-1")
    api_main.seed_repertoire("white", RepertoireSeedRequest(), request)
    response = asyncio.run(api_main.repertoire_lines_route("white", RepertoireLinesRequest(fetchBudget=0), request))

    assert response.lines and len(response.lines) <= 50
    assert response.choicesUsed >= 3
    main = next(line for line in response.lines if line.san[:6] == ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5"])
    assert main.openingName and main.openingName.startswith("Italian Game")
    total = sum(getattr(response.coverage, key) for key in ("complete", "outOfBook", "needsChoice", "pending", "noData", "pruned"))
    assert total == pytest.approx(1.0, abs=0.01)
    # Black's popular replies the seed has no answer for show up as gaps.
    assert any(line.status == "needs_choice" for line in response.lines)


def test_line_ends_complete_when_every_reply_is_under_the_cutoff(monkeypatch):
    table = {
        epd_after("e4"): (10_000, [("e5", 1.0)]),
        epd_after("e4", "e5", "Nf3"): (10_000, [("Nc6", 0.5), ("d6", 0.5)]),
    }
    monkeypatch.setattr(lines_module, "popularity", fake_popularity(table))
    choices = {epd_after(): {"uci": "e2e4"}, epd_after("e4", "e5"): {"uci": "g1f3"}}
    result = repertoire_lines("white", choices, line_settings=LineSettings(min_reach=0.6), explorer=no_explorer(), fetch_budget=0)
    [line] = result["lines"]
    assert line["san"] == ["e4", "e5", "Nf3"]
    assert (line["status"], line["endReason"]) == ("complete", "below_cutoff")
    assert result["coverage"]["complete"] == 1.0 and result["coverage"]["pruned"] == 0.0
