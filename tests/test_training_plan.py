from __future__ import annotations

from datetime import date

import chess
import pytest

from backend.models import TrainingCardReviewRequest, TrainingPlanResponse
from backend.services.training_plan_service import TrainingPlanStore, is_standard_game
from utils.game_enrichment_transformer import EnrichedGame, EnrichedMove
from utils.training_plan import (
    SIMPLE_REPERTOIRE,
    TrainingPlanConfig,
    build_training_plan,
    classify_process,
    review_card,
)


ITALIAN = ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "c3", "Nf6", "d3", "d6", "O-O", "O-O",
           "Re1", "a6", "a4", "Ba7", "Nbd2", "h6", "Nf1", "Re8", "Ng3", "Be6"]
SICILIAN = ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6", "Be2", "e5",
            "Nb3", "Be7", "O-O", "O-O", "Be3", "Be6", "Qd2", "Nbd7", "a4", "Rc8"]


def make_game(uid: str, sans: list[str], *, me: str = "white", result: str = "win",
              clock: float | None = 500.0, time_control: str = "600+5", rating: int = 1500,
              opponent_rating: int = 1500, opening: str = "Italian Game: Giuoco Pianissimo") -> EnrichedGame:
    board = chess.Board()
    moves = []
    for index, san in enumerate(sans):
        ply = index + 1
        fen_before = board.fen()
        move = board.parse_san(san)
        color = "white" if board.turn == chess.WHITE else "black"
        board.push(move)
        moves.append(EnrichedMove(
            game_uuid=uid, game_url=f"https://chess.test/{uid}", ply=ply, move_number=(ply + 1) // 2,
            player_color=color, player_username=None, san=san, uci=move.uci(),
            fen_before=fen_before, fen_after=board.fen(),
            eval_before_cp=20, eval_after_cp=20, eval_best_move_cp=20, eval_played_move_cp=20, move_cp_loss=0,
            best_move_uci=move.uci(), top_engine_moves=[], best_move_cp_gain=0,
            win_prob_before=0.5, win_prob_after=0.5, win_prob_loss=0.0,
            clock_before=clock, clock_after=clock, clock_spent=10.0,
            phase="opening" if ply <= 16 else "middlegame", position_type_tags=[],
            tactical_position=False, quiet_middlegame=True, complexity=None, number_of_legal_moves=30,
            eval_volatility_among_top_engine_lines=None, forcing_line_depth=0, low_gap_between_top_moves=None,
            engine_top_move_is_forcing=False, move_is_threat=False, is_capture="x" in san, is_check="+" in san,
            is_castling=san.startswith("O-O"), is_promotion=False, in_opening_book=ply <= 10,
            opening_eco="C53", opening_name=opening,
        ))
    names = {"white": "me", "black": "opp"} if me == "white" else {"white": "opp", "black": "me"}
    other = {"win": "resigned", "resigned": "win", "agreed": "agreed"}[result]
    return EnrichedGame(
        uuid=uid, url=f"https://chess.test/{uid}",
        white_username=names["white"], black_username=names["black"],
        white_rating=rating if me == "white" else opponent_rating,
        black_rating=rating if me == "black" else opponent_rating,
        white_result=result if me == "white" else other, black_result=result if me == "black" else other,
        result=None, time_class="rapid", time_control=time_control, rated=True, end_time=1_700_000_000,
        chesscom_white_accuracy=None, chesscom_black_accuracy=None,
        opening_eco="C53", opening_name=opening, moves=moves,
    )


def mistake(game: EnrichedGame, ply: int, *, severity: str = "mistake", wp_loss: float = 0.1,
            before: int = 0, after: int = -200, depth: int = 3, tactics: list[str] | None = None,
            reply_san: str = "Qd8+") -> dict:
    move = next(m for m in game.moves if m.ply == ply)
    return {
        "mistake_id": f"{game.uuid}-{ply}", "game_uuid": game.uuid, "game_url": game.url, "ply": ply,
        "move_number": move.move_number, "player_color": move.player_color, "san": move.san, "uci": move.uci,
        "fen_before": move.fen_before, "fen_after": move.fen_after, "severity": severity, "wp_loss": wp_loss,
        "user_eval_before_cp": before, "user_eval_after_cp": after,
        "best_line_moves": [{"side_to_move": "black" if move.player_color == "white" else "white", "san": reply_san}],
        "theoretical_punishment_depth": depth,
        "tactics": [{"theme": theme} for theme in (tactics or [])],
    }


@pytest.mark.parametrize("slot", sorted(SIMPLE_REPERTOIRE))
def test_curated_repertoire_lines_are_legal(slot):
    entry = SIMPLE_REPERTOIRE[slot]
    for line in (entry["line"], entry["trap_line"]):
        board = chess.Board()
        for san in line:
            board.push_san(san)


def test_classify_process_follows_priority_rules():
    config = TrainingPlanConfig()
    game = make_game("g1", ITALIAN)
    move = next(m for m in game.moves if m.ply == 13)

    low_clock = EnrichedMove(**{**move.__dict__, "clock_before": 30.0})
    assert classify_process(mistake(game, 13), low_clock, 600, config) == "time_trouble"
    assert classify_process(mistake(game, 13, before=450, after=60), move, 600, config) == "technique"
    assert classify_process(mistake(game, 13, depth=2), move, 600, config) == "missed_threat"
    assert classify_process(mistake(game, 13, depth=6, reply_san="h6"), move, 600, config) == "evaluation"
    assert classify_process(mistake(game, 13, depth=6, reply_san="h6", tactics=["fork"]), move, 600, config) == "missed_threat"
    threat = EnrichedMove(**{**move.__dict__, "move_is_threat": True})
    assert classify_process(mistake(game, 13, depth=1), threat, 600, config) == "hope_chess"
    # Daily games have no base clock, so no time trouble is inferred.
    assert classify_process(mistake(game, 13), low_clock, None, config) != "time_trouble"


def test_build_training_plan_diagnosis_repertoire_routine_and_cards():
    games = [make_game(f"w{i}", ITALIAN, result="win" if i % 2 else "resigned") for i in range(4)]
    games += [make_game(f"s{i}", SICILIAN, me="black", result="resigned", opening="Sicilian Defense: Najdorf") for i in range(3)]
    mistakes = []
    for game in games[:4]:
        mistakes.append(mistake(game, 19, tactics=["fork"], depth=2))
    mistakes.append(mistake(games[4], 20, severity="blunder", wp_loss=0.3, depth=6, reply_san="h6"))
    mistakes.append(mistake(games[5], 18, severity="inaccuracy"))

    plan = build_training_plan(games, mistakes, "me", today=date(2026, 11, 10),
                               previous_cards={"w0-19": {"interval_days": 7, "streak": 1, "due_on": "2026-11-12", "reviews": 2}})
    TrainingPlanResponse.model_validate({
        "id": "x", "username": "me", "request_params": {}, "created_at": "now", "updated_at": "now", **plan,
    })

    diagnosis = plan["diagnosis"]
    assert diagnosis["moves_analyzed"] == 4 * 11 + 3 * 11
    assert diagnosis["error_count"] == 5  # the inaccuracy is not an error
    assert diagnosis["top_weaknesses"][0]["tag"] == "missed_threat"
    assert diagnosis["top_weaknesses"][0]["count"] == 4
    fork = next(m for m in diagnosis["motifs"] if m["motif"] == "Fork")
    assert fork == {"motif": "Fork", "count": 4, "games": 4, "own_block": True}

    repertoire = plan["repertoire"]
    assert repertoire["mode"] == "simple"
    names = [r["name"] for r in repertoire["recommended"]]
    assert names[0].startswith("Italian") and names[1] == "Petrov Defence"
    assert repertoire["recommended"][0]["your_games"] == 4
    assert any("Sicilian" in text for text in repertoire["recommended"][1]["replaces"])

    days = plan["routine"]["days"]
    assert [d["day"] for d in days] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    assert days[1]["weakness"] == "missed_threat"
    assert "Fork" in days[4]["blocks"][1]["text"]

    cards = {card["card_id"]: card for card in plan["cards"]}
    assert cards["w0-19"]["interval_days"] == 7 and cards["w0-19"]["reviews"] == 2
    assert cards["w1-19"]["due_on"] == "2026-11-10"
    assert cards["w1-19"]["best_san"] == next(m for m in games[1].moves if m.ply == 19).san
    assert plan["metadata"]["reevaluate_on"] == "2026-12-22"


def test_theory_mode_keeps_players_own_lines_above_rating_threshold():
    games = [make_game(f"w{i}", ITALIAN, rating=2100) for i in range(3)]
    mistakes = [mistake(games[0], 13, before=450, after=60)]
    plan = build_training_plan(games, mistakes, "me", today=date(2026, 11, 10))
    assert plan["repertoire"]["mode"] == "theory"
    assert plan["repertoire"]["recommended"][0]["name"] == "1.e4 · Italian Game"
    assert plan["repertoire"]["recommended"][0]["line"].startswith("1.e4 e5 2.Nf3")


def test_repertoire_groups_by_players_own_move_not_opening_name():
    # As White: always 1.e4, but the opponent's reply changes the opening name.
    white = [make_game(f"i{i}", ITALIAN) for i in range(3)]
    white += [make_game(f"s{i}", SICILIAN, opening="Sicilian Defense: Najdorf") for i in range(3)]
    # As Black: always 1…e5, against both the Italian and a Ruy Lopez.
    ruy = ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O", "Be7", "Re1", "b5",
           "Bb3", "d6", "c3", "O-O", "h3", "Nb8", "d4", "Nbd7", "Nbd2", "Bb7"]
    black = [make_game(f"bi{i}", ITALIAN, me="black") for i in range(3)]
    black += [make_game(f"br{i}", ruy, me="black", opening="Ruy Lopez: Closed") for i in range(3)]
    plan = build_training_plan(white + black, [], "me", today=date(2026, 11, 10))

    repertoire = plan["repertoire"]
    as_white = next(r for r in repertoire["recommended"] if r["slot"] == "white")
    vs_e4 = next(r for r in repertoire["recommended"] if r["slot"] == "black_vs_e4")
    assert as_white["replaces"] == [] and as_white["your_games"] == 6
    assert vs_e4["replaces"] == [] and vs_e4["your_games"] == 6
    assert all(row["verdict"] != "consolidate" for row in repertoire["played"])
    assert {row["choice"] for row in repertoire["played"]} == {"1.e4", "1…e5"}


def test_several_replies_to_the_same_move_are_consolidated():
    games = [make_game(f"e{i}", ITALIAN, me="black") for i in range(4)]
    games += [make_game(f"c{i}", SICILIAN, me="black", opening="Sicilian Defense") for i in range(3)]
    plan = build_training_plan(games, [], "me", today=date(2026, 11, 10))
    verdicts = {row["choice"]: row["verdict"] for row in plan["repertoire"]["played"]}
    assert verdicts["1…c5"] == "consolidate" and verdicts["1…e5"] != "consolidate"
    vs_e4 = next(r for r in plan["repertoire"]["recommended"] if r["slot"] == "black_vs_e4")
    assert vs_e4["your_games"] == 4 and vs_e4["replaces"][0].startswith("1…c5")


def test_review_card_ladder_and_retirement():
    card = {"interval_days": 0, "streak": 0, "reviews": 0}
    today = date(2026, 11, 10)
    card = review_card(card, "good", today)
    assert card["interval_days"] == 1 and card["due_on"] == "2026-11-11"
    card = review_card(card, "good", today)
    card = review_card(card, "good", today)
    assert card["interval_days"] == 7 and card["streak"] == 1
    card = review_card(card, "hard", today)
    assert card["interval_days"] == 7 and card["streak"] == 0
    for _ in range(3):
        card = review_card(card, "good", today)
    assert card["retired"] is True
    card = review_card(card, "again", today)
    assert card["interval_days"] == 1 and card["retired"] is False


def test_training_plan_store_review_roundtrip():
    store = TrainingPlanStore()
    store.save("owner", "Me", {"cards": [{"card_id": "c1", "interval_days": 0, "streak": 0, "reviews": 0}]})
    updated = store.review("owner", "me", "c1", TrainingCardReviewRequest(grade="good", label="missed_threat", note="  saw it late "))
    assert updated["interval_days"] == 1 and updated["note"] == "saw it late"
    assert store.get("owner", "ME")["cards"][0]["reviews"] == 1


def test_is_standard_game_filters_variants_and_short_games():
    long_pgn = "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6 5. d3 d6 6. O-O O-O 7. Re1 a6 8. a4 Ba7 9. Nbd2 h6 10. Nf1 Re8 *"
    assert is_standard_game({"rules": "chess", "pgn": long_pgn})
    assert not is_standard_game({"rules": "chess960", "pgn": long_pgn})
    assert not is_standard_game({"rules": "chess", "pgn": "1. e4 e5 2. Qh5 Nc6 *"})


def test_training_plan_http_endpoints(monkeypatch):
    from fastapi.testclient import TestClient

    from backend import main as api_main
    from backend.services.auth_service import AuthRepository
    from backend.settings import settings

    sent: dict[str, str] = {}

    async def fake_send(*, recipient: str, token: str):
        sent.update(token=token)

    started: list[str] = []
    monkeypatch.setattr(api_main, "send_verification_email", fake_send)
    monkeypatch.setattr(api_main, "run_training_plan_job", lambda job: started.append(job.request.username))
    client = TestClient(api_main.app)
    try:
        client.post("/api/auth/register", json={"email": "member@example.com", "password": "correct horse battery staple"})
        client.post("/api/auth/verify-email", json={"token": sent["token"]})
        client.post("/api/auth/login", json={"email": "member@example.com", "password": "correct horse battery staple"})
        csrf = {"X-CSRF-Token": client.cookies.get(settings.csrf_cookie_name)}

        assert client.get("/api/players/me/training-plan").status_code == 404

        accepted = client.post("/api/training-plans/builds", json={"username": "me", "max_games": 30}, headers=csrf)
        assert accepted.status_code == 202 and started == ["me"]
        status = client.get(f"/api/training-plans/builds/{accepted.json()['build_id']}")
        assert status.status_code == 200 and status.json()["status"] == "queued"
        assert client.post("/api/training-plans/builds", json={"username": "me", "max_games": 500}, headers=csrf).status_code == 422

        user_id = AuthRepository().authenticate("member@example.com", "correct horse battery staple")[0].id
        games = [make_game(f"w{i}", ITALIAN) for i in range(3)]
        plan = build_training_plan(games, [mistake(games[0], 19, depth=2)], "me", today=date(2026, 11, 10))
        TrainingPlanStore().save(user_id, "me", {
            "id": "plan-1", "username": "me", "request_params": {"username": "me"},
            "created_at": "2026-11-10T00:00:00Z", "updated_at": "2026-11-10T00:00:00Z", **plan,
        })

        loaded = client.get("/api/players/ME/training-plan")
        assert loaded.status_code == 200 and loaded.json()["cards"][0]["card_id"] == "w0-19"
        reviewed = client.post("/api/players/me/training-plan/cards/w0-19/review", json={"grade": "good"}, headers=csrf)
        assert reviewed.status_code == 200 and reviewed.json()["interval_days"] == 1
        assert client.post("/api/players/me/training-plan/cards/missing/review", json={"grade": "good"}, headers=csrf).status_code == 404

    finally:
        client.close()


def test_parse_line_text_reads_numbered_san():
    from utils.training_plan import parse_line_text

    assert parse_line_text("1.d4 d5 2.c4 e6 3.Nc3…Nf6") == ["d4", "d5", "c4", "e6", "Nc3", "Nf6"]
    assert parse_line_text("1. e4 e5") == ["e4", "e5"]
    with pytest.raises(ValueError):
        parse_line_text("1. 2.")
