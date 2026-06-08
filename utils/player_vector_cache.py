from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Optional

import chess
import chess.engine
import chess.pgn

from utils.chesscom_repository import ChessComRepository
from utils.game_enrichment_transformer import EnrichedGame, EnrichedMove, GameEnrichmentTransformer
from utils.opening_repository import OpeningRepository
from utils.player_feature_transformer import (
    PlayerFeatureAggregator,
    PlayerSampleBuilder,
    player_opening_vector,
)
from utils.position_feature_extractor import (
    FEATURES,
    analyse_position_safe,
    extract_position_features,
)
from utils.statistics_shared import DEFAULT_GLOBAL_STATISTICS_HPARAMS_PATH


DEFAULT_PLAYER_VECTOR_CACHE = ".cache/player_vectors.json"


@dataclass(frozen=True)
class CachedPlayerVector:
    vector: dict[str, Optional[float]]
    feature_order: list[str]
    metadata: dict[str, Any]
    confidence: dict[str, float]
    cache_key: dict[str, Any]
    created_at: str
    cache_hit: bool = False


class PlayerVectorCache:
    def __init__(self, path: str | Path = DEFAULT_PLAYER_VECTOR_CACHE):
        self.path = Path(path)

    def get(self, key: dict[str, Any]) -> Optional[CachedPlayerVector]:
        data = self._read()
        entry = data.get(self.key_id(key))
        if entry is None:
            return None
        return CachedPlayerVector(
            vector=entry["vector"],
            feature_order=list(entry["feature_order"]),
            metadata=dict(entry.get("metadata", {})),
            confidence=dict(entry.get("confidence", {})),
            cache_key=dict(entry["cache_key"]),
            created_at=str(entry["created_at"]),
            cache_hit=True,
        )

    def set(self, value: CachedPlayerVector) -> None:
        data = self._read()
        data[self.key_id(value.cache_key)] = {
            "vector": value.vector,
            "feature_order": value.feature_order,
            "metadata": value.metadata,
            "confidence": value.confidence,
            "cache_key": value.cache_key,
            "created_at": value.created_at,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return raw if isinstance(raw, dict) else {}

    @staticmethod
    def key_id(key: dict[str, Any]) -> str:
        payload = json.dumps(key, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def chesscom_cache_key(
    *,
    username: str,
    max_games: int,
    since_year: Optional[int],
    since_month: Optional[int],
    time_classes: Optional[set[str]],
    rated_filter: Optional[bool],
    engine_depth: int,
) -> dict[str, Any]:
    return {
        "source": "chess.com",
        "username": username.strip().lower(),
        "max_games": int(max_games),
        "since_year": since_year,
        "since_month": since_month,
        "time_classes": None if time_classes is None else sorted({item.strip().lower() for item in time_classes}),
        "rated_filter": rated_filter,
        "engine_depth": int(engine_depth),
    }


def pgn_cache_key(
    *,
    pgn_path: str | Path,
    player_name: str,
    engine_depth: int,
) -> dict[str, Any]:
    path = Path(pgn_path).expanduser().resolve()
    stat = path.stat()
    return {
        "source": "pgn",
        "path": str(path),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "player_name": player_name.strip().lower(),
        "engine_depth": int(engine_depth),
    }


def load_or_compute_chesscom_vector(
    *,
    username: str,
    max_games: int,
    since_year: Optional[int],
    since_month: Optional[int],
    time_classes: Optional[set[str]],
    rated_filter: Optional[bool],
    engine_path: Optional[str],
    engine_depth: int,
    no_engine: bool,
    opening_repository: Optional[OpeningRepository],
    cache_path: str | Path = DEFAULT_PLAYER_VECTOR_CACHE,
    refresh: bool = False,
) -> CachedPlayerVector:
    key = chesscom_cache_key(
        username=username,
        max_games=max_games,
        since_year=since_year,
        since_month=since_month,
        time_classes=time_classes,
        rated_filter=rated_filter,
        engine_depth=engine_depth,
    )
    cache = PlayerVectorCache(cache_path)
    if not refresh:
        cached = cache.get(key)
        if cached is not None:
            return cached

    raw_games = fetch_chesscom_games(
        username=username,
        max_games=max_games,
        since_year=since_year,
        since_month=since_month,
        time_classes=time_classes,
        rated_filter=rated_filter,
    )
    if not raw_games:
        raise RuntimeError("No games found. Check username, date range, time classes, and rated filter.")

    engine_used = False
    fallback_reason = None
    if not no_engine and engine_path:
        try:
            transformer = GameEnrichmentTransformer(
                stockfish_path=engine_path,
                opening_repository=opening_repository,
                engine_limit=chess.engine.Limit(depth=engine_depth),
            )
            enriched_games = transformer.transform_games(raw_games)
            engine_used = True
        except Exception as exc:
            fallback_reason = str(exc)
            enriched_games = heuristic_enrich_game_data(raw_games, opening_repository=opening_repository, engine_depth=engine_depth)
    else:
        fallback_reason = "engine disabled" if no_engine else "engine path not provided"
        enriched_games = heuristic_enrich_game_data(raw_games, opening_repository=opening_repository, engine_depth=engine_depth)

    value = build_cached_vector(
        key=key,
        player_name=username,
        enriched_games=enriched_games,
        metadata={
            "source": "chess.com",
            "username": username,
            "games_selected": len(raw_games),
            "games_enriched": len(enriched_games),
            "engine_used": engine_used,
            "fallback_reason": fallback_reason,
        },
    )
    cache.set(value)
    return value


def load_or_compute_pgn_vector(
    *,
    pgn_path: str | Path,
    player_name: str,
    engine_path: Optional[str],
    engine_depth: int,
    no_engine: bool,
    opening_repository: Optional[OpeningRepository],
    cache_path: str | Path = DEFAULT_PLAYER_VECTOR_CACHE,
    refresh: bool = False,
) -> CachedPlayerVector:
    key = pgn_cache_key(pgn_path=pgn_path, player_name=player_name, engine_depth=engine_depth)
    cache = PlayerVectorCache(cache_path)
    if not refresh:
        cached = cache.get(key)
        if cached is not None:
            return cached

    raw_games = pgn_file_to_game_data(pgn_path)
    if not raw_games:
        raise RuntimeError(f"No parseable games found in {pgn_path}")

    engine_used = False
    fallback_reason = None
    if not no_engine and engine_path:
        try:
            transformer = GameEnrichmentTransformer(
                stockfish_path=engine_path,
                opening_repository=opening_repository,
                engine_limit=chess.engine.Limit(depth=engine_depth),
            )
            enriched_games = transformer.transform_games(raw_games)
            engine_used = True
        except Exception as exc:
            fallback_reason = str(exc)
            enriched_games = heuristic_enrich_game_data(raw_games, opening_repository=opening_repository, engine_depth=engine_depth)
    else:
        fallback_reason = "engine disabled" if no_engine else "engine path not provided"
        enriched_games = heuristic_enrich_game_data(raw_games, opening_repository=opening_repository, engine_depth=engine_depth)

    value = build_cached_vector(
        key=key,
        player_name=player_name,
        enriched_games=enriched_games,
        metadata={
            "source": "pgn",
            "player_name": player_name,
            "pgn_path": str(Path(pgn_path).expanduser().resolve()),
            "games_selected": len(raw_games),
            "games_enriched": len(enriched_games),
            "engine_used": engine_used,
            "fallback_reason": fallback_reason,
        },
    )
    cache.set(value)
    return value


def fetch_chesscom_games(
    *,
    username: str,
    max_games: int,
    since_year: Optional[int],
    since_month: Optional[int],
    time_classes: Optional[set[str]],
    rated_filter: Optional[bool],
) -> list[dict[str, Any]]:
    repo = ChessComRepository(username)
    selected: list[dict[str, Any]] = []
    normalized_time_classes = None if time_classes is None else {item.lower() for item in time_classes}
    for game_data in repo.iter_all_games(since_year=since_year, since_month=since_month):
        if "pgn" not in game_data:
            continue
        if normalized_time_classes is not None and game_data.get("time_class") not in normalized_time_classes:
            continue
        if rated_filter is not None and game_data.get("rated") is not rated_filter:
            continue
        selected.append(game_data)
        if len(selected) >= max_games:
            break
    return selected


def pgn_file_to_game_data(pgn_path: str | Path) -> list[dict[str, Any]]:
    games: list[dict[str, Any]] = []
    path = Path(pgn_path)
    with path.open("r", encoding="utf-8", errors="replace") as file:
        while True:
            game = chess.pgn.read_game(file)
            if game is None:
                break
            exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=True)
            pgn_text = game.accept(exporter)
            games.append(
                {
                    "pgn": pgn_text,
                    "uuid": game.headers.get("Site") or None,
                    "url": game.headers.get("Site") or None,
                    "white": {
                        "username": game.headers.get("White"),
                        "rating": _optional_int(game.headers.get("WhiteElo")),
                    },
                    "black": {
                        "username": game.headers.get("Black"),
                        "rating": _optional_int(game.headers.get("BlackElo")),
                    },
                    "rated": None,
                    "time_class": None,
                    "time_control": game.headers.get("TimeControl"),
                }
            )
    return games


def heuristic_enrich_game_data(
    games: list[dict[str, Any]],
    *,
    opening_repository: Optional[OpeningRepository],
    engine_depth: int,
) -> list[EnrichedGame]:
    return [
        heuristic_enrich_single_game(game_data, opening_repository=opening_repository, engine_depth=engine_depth)
        for game_data in games
        if "pgn" in game_data
    ]


def heuristic_enrich_single_game(
    game_data: dict[str, Any],
    *,
    opening_repository: Optional[OpeningRepository],
    engine_depth: int,
) -> EnrichedGame:
    game = chess.pgn.read_game(io.StringIO(game_data["pgn"]))
    if game is None:
        raise ValueError("Could not parse PGN")

    white = game_data.get("white", {}) or {}
    black = game_data.get("black", {}) or {}
    white_username = white.get("username") or game.headers.get("White")
    black_username = black.get("username") or game.headers.get("Black")
    game_opening = opening_repository.detect_from_pgn_game(game) if opening_repository is not None else None
    current_opening = None

    board = game.board()
    moves: list[EnrichedMove] = []
    engine_cache = {}
    for ply, node in enumerate(game.mainline(), start=1):
        move = node.move
        if move is None:
            continue

        color_name = "white" if board.turn == chess.WHITE else "black"
        color = board.turn
        player_username = white_username if color == chess.WHITE else black_username
        fen_before = board.fen()
        san = board.san(move)
        is_capture = board.is_capture(move)
        is_check = board.gives_check(move)
        is_castling = board.is_castling(move)
        is_promotion = move.promotion is not None
        opening_before = opening_repository.get_by_board(board) if opening_repository is not None else None
        phase = classify_phase(board, ply, opening_before is not None)
        engine_info = analyse_position_safe(board, None, engine_depth=engine_depth, cache=engine_cache)
        features = extract_position_features(board, color, None, engine_depth=engine_depth, engine_cache=engine_cache)

        board.push(move)
        fen_after = board.fen()
        opening_after = opening_repository.get_by_board(board) if opening_repository is not None else None
        if opening_after is not None:
            current_opening = opening_after

        moves.append(
            EnrichedMove(
                game_uuid=game_data.get("uuid"),
                game_url=game_data.get("url"),
                ply=ply,
                move_number=(ply + 1) // 2,
                player_color=color_name,
                player_username=player_username,
                san=san,
                uci=move.uci(),
                fen_before=fen_before,
                fen_after=fen_after,
                eval_before_cp=None,
                eval_after_cp=None,
                eval_best_move_cp=None,
                eval_played_move_cp=None,
                move_cp_loss=None,
                best_move_uci=None,
                top_engine_moves=[],
                best_move_cp_gain=int(engine_info.best_move_cp_gain),
                win_prob_before=None,
                win_prob_after=None,
                win_prob_loss=None,
                clock_before=None,
                clock_after=node.clock(),
                clock_spent=None,
                phase=phase,
                position_type_tags=position_tags(features, phase),
                tactical_position=features["tactical_density"] >= 0.55,
                quiet_middlegame=phase == "middlegame" and features["quiet_position_density"] >= 0.60,
                complexity=features["middlegame_complexity"],
                number_of_legal_moves=chess.Board(fen_before).legal_moves.count(),
                eval_volatility_among_top_engine_lines=engine_info.eval_volatility,
                forcing_line_depth=engine_info.forcing_line_depth,
                low_gap_between_top_moves=engine_info.low_gap_between_top_moves,
                engine_top_move_is_forcing=engine_info.best_move_is_forcing,
                move_is_threat=False,
                is_capture=is_capture,
                is_check=is_check,
                is_castling=is_castling,
                is_promotion=is_promotion,
                in_opening_book=opening_after is not None,
                opening_eco=current_opening.eco if current_opening else None,
                opening_name=current_opening.name if current_opening else None,
            )
        )

    return EnrichedGame(
        uuid=game_data.get("uuid"),
        url=game_data.get("url"),
        white_username=white_username,
        black_username=black_username,
        white_rating=white.get("rating"),
        black_rating=black.get("rating"),
        white_result=white.get("result"),
        black_result=black.get("result"),
        result=game.headers.get("Result"),
        time_class=game_data.get("time_class"),
        time_control=game_data.get("time_control"),
        rated=game_data.get("rated"),
        end_time=game_data.get("end_time"),
        chesscom_white_accuracy=(game_data.get("accuracies") or {}).get("white"),
        chesscom_black_accuracy=(game_data.get("accuracies") or {}).get("black"),
        opening_eco=game_opening.eco if game_opening else None,
        opening_name=game_opening.name if game_opening else None,
        moves=moves,
    )


def build_cached_vector(
    *,
    key: dict[str, Any],
    player_name: str,
    enriched_games: list[EnrichedGame],
    metadata: dict[str, Any],
    hparams_path: str | Path = DEFAULT_GLOBAL_STATISTICS_HPARAMS_PATH,
) -> CachedPlayerVector:
    samples, castling_summaries = PlayerSampleBuilder(hparams_path).build(enriched_games, player_name)
    if not samples:
        raise RuntimeError(f"No moves found for player {player_name!r}. Check player identity in source games.")
    profile = PlayerFeatureAggregator(hparams_path).aggregate(samples, castling_summaries, player_name=player_name)
    vector = player_opening_vector(profile)
    metadata = {
        **metadata,
        "player_name": profile.player_name,
        "games_analyzed": profile.games_analyzed,
        "moves_analyzed": profile.moves_analyzed,
    }
    return CachedPlayerVector(
        vector=vector,
        feature_order=list(FEATURES),
        metadata=metadata,
        confidence=profile.confidence,
        cache_key=key,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def classify_phase(board: chess.Board, ply: int, in_book: bool) -> str:
    if in_book or ply <= 20:
        return "opening"
    queens = len(board.pieces(chess.QUEEN, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.BLACK))
    non_pawn_material = 0
    values = {chess.KNIGHT: 300, chess.BISHOP: 300, chess.ROOK: 500, chess.QUEEN: 900}
    for piece, value in values.items():
        non_pawn_material += value * (
            len(board.pieces(piece, chess.WHITE)) + len(board.pieces(piece, chess.BLACK))
        )
    if non_pawn_material <= 2600 or (queens == 0 and non_pawn_material <= 3600):
        return "endgame"
    return "middlegame"


def position_tags(features: dict[str, float], phase: str) -> list[str]:
    tags = [phase]
    if features["tactical_density"] >= 0.55:
        tags.append("tactical")
    if phase == "middlegame" and features["quiet_position_density"] >= 0.60:
        tags.append("quiet_middlegame")
    return tags


def _optional_int(value: Any) -> Optional[int]:
    try:
        return None if value in (None, "") else int(value)
    except (TypeError, ValueError):
        return None
