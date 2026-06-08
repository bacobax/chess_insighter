from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import io

import chess.pgn
import requests

from backend.models import GameSummary, GamesQueryRequest
from utils.chesscom_repository import ChessComRepository


DRAW_RESULTS = {
    "agreed",
    "repetition",
    "stalemate",
    "insufficient",
    "50move",
    "timevsinsufficient",
}
LOSS_RESULTS = {"checkmated", "resigned", "timeout", "abandoned", "lose"}


class ChessComServiceError(RuntimeError):
    pass


class UnknownChessComUser(ValueError):
    pass


def validate_username(username: str) -> None:
    try:
        ChessComRepository(username).get_profile()
    except ValueError as exc:
        raise UnknownChessComUser(f"Chess.com user not found: {username}") from exc
    except requests.RequestException as exc:
        raise ChessComServiceError(f"Chess.com network failure: {exc}") from exc
    except RuntimeError as exc:
        raise ChessComServiceError(str(exc)) from exc


def query_games(request: GamesQueryRequest) -> tuple[list[dict[str, Any]], bool, int]:
    repo = ChessComRepository(request.username)
    try:
        repo.get_profile()
        archives = repo.get_archives()
    except ValueError as exc:
        raise UnknownChessComUser(f"Chess.com user not found: {request.username}") from exc
    except requests.RequestException as exc:
        raise ChessComServiceError(f"Chess.com network failure: {exc}") from exc
    except RuntimeError as exc:
        raise ChessComServiceError(str(exc)) from exc

    wanted = request.page * request.page_size + 1
    selected: list[dict[str, Any]] = []
    time_classes = None if request.time_classes is None else set(request.time_classes)

    for archive in reversed(archives):
        if not repo._archive_in_range(
            archive,
            since_year=request.since_year,
            since_month=request.since_month,
            until_year=request.until_year,
            until_month=request.until_month,
        ):
            continue
        try:
            month_games = repo.get_month_games(archive.year, archive.month)
        except requests.RequestException as exc:
            raise ChessComServiceError(f"Chess.com network failure: {exc}") from exc
        except RuntimeError as exc:
            raise ChessComServiceError(str(exc)) from exc

        for game in sorted(month_games, key=lambda item: item.get("end_time") or 0, reverse=True):
            if "pgn" not in game:
                continue
            if time_classes is not None and (game.get("time_class") or "").lower() not in time_classes:
                continue
            if request.rated_filter is not None and game.get("rated") is not request.rated_filter:
                continue
            selected.append(game)
            if len(selected) >= wanted:
                start = (request.page - 1) * request.page_size
                end = start + request.page_size
                return selected[start:end], True, len(selected)

    start = (request.page - 1) * request.page_size
    end = start + request.page_size
    return selected[start:end], len(selected) > end, len(selected)


def fetch_latest_games_for_report(
    *,
    username: str,
    max_games: int,
    time_classes: list[str] | None,
    rated_filter: bool | None,
    since_year: int | None,
    since_month: int | None,
    until_year: int | None,
    until_month: int | None,
) -> list[dict[str, Any]]:
    request = GamesQueryRequest(
        username=username,
        page=1,
        page_size=max_games,
        time_classes=time_classes,
        rated_filter=rated_filter,
        since_year=since_year,
        since_month=since_month,
        until_year=until_year,
        until_month=until_month,
    )
    games, _has_more, _total = query_games(request)
    return games


def summarize_games(username: str, games: list[dict[str, Any]]) -> list[GameSummary]:
    return [summarize_game(username, game) for game in games]


def summarize_game(username: str, game: dict[str, Any]) -> GameSummary:
    username_key = username.strip().lower()
    white = game.get("white", {}) or {}
    black = game.get("black", {}) or {}
    is_white = (white.get("username") or "").strip().lower() == username_key
    player = white if is_white else black
    opponent = black if is_white else white
    color = "white" if is_white else "black"
    player_result = player.get("result")
    opening_eco, opening_name = pgn_opening(game.get("pgn"))

    return GameSummary(
        id=game.get("uuid") or game.get("url"),
        url=game.get("url"),
        result=normalize_result(player_result, game.get("pgn"), color),
        player_username=player.get("username") or username,
        player_color=color,
        player_elo_before=None,
        player_elo_after=optional_int(player.get("rating")),
        opponent_username=opponent.get("username"),
        opponent_elo_before=None,
        opponent_elo_after=optional_int(opponent.get("rating")),
        opponent_result=opponent.get("result"),
        end_time=optional_int(game.get("end_time")),
        end_time_iso=end_time_iso(game.get("end_time")),
        time_class=game.get("time_class"),
        time_control=game.get("time_control"),
        rated=game.get("rated"),
        opening_eco=opening_eco,
        opening_name=opening_name,
    )


def normalize_result(chesscom_result: str | None, pgn: str | None, color: str) -> str:
    if chesscom_result == "win":
        return "win"
    if chesscom_result in LOSS_RESULTS:
        return "loss"
    if chesscom_result in DRAW_RESULTS:
        return "draw"
    if pgn:
        game = chess.pgn.read_game(io.StringIO(pgn))
        result = game.headers.get("Result") if game is not None else None
        if result == "1/2-1/2":
            return "draw"
        if result == "1-0":
            return "win" if color == "white" else "loss"
        if result == "0-1":
            return "win" if color == "black" else "loss"
    return "unknown"


def pgn_opening(pgn: str | None) -> tuple[str | None, str | None]:
    if not pgn:
        return None, None
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        return None, None
    eco = game.headers.get("ECO")
    name = game.headers.get("Opening")
    return eco, name


def end_time_iso(value: Any) -> str | None:
    timestamp = optional_int(value)
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def optional_int(value: Any) -> int | None:
    try:
        return None if value in (None, "") else int(value)
    except (TypeError, ValueError):
        return None
