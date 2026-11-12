"""Training plan builder: turns enriched games + mistakes-analyzer output into
an error diagnosis, a short opening repertoire and a weekly routine.

Pure logic, no engine and no FastAPI. Every win-probability threshold uses the
analyzer's own 0–1 scale (``default_cp_to_expected_points``), and mistake vs
blunder comes from the analyzer's ``severity``.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median
from typing import Any, Iterable

import chess

from utils.game_enrichment_transformer import EnrichedGame, EnrichedMove


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class TrainingPlanConfig:
    error_severities: tuple[str, ...] = ("mistake", "blunder")
    # Process-tag heuristics (centipawns from the player's point of view).
    time_trouble_clock_fraction: float = 0.10
    time_trouble_fast_move_seconds: float = 2.0
    technique_winning_cp: int = 300
    technique_after_cp: int = 150
    technique_drawn_cp: int = 60
    technique_drawn_after_cp: int = -150
    quick_refutation_opponent_moves: int = 2
    missed_threat_opponent_moves: int = 3
    missed_opportunity_gain_cp: int = 150
    # Context buckets.
    winning_cp: int = 150
    clock_high_fraction: float = 0.50
    opponent_gap: int = 100
    # Motif promotion rule.
    motif_min_occurrences: int = 4
    motif_min_games: int = 3
    # Repertoire.
    simple_repertoire_below_rating: int = 1800
    opening_min_games: int = 3
    fix_first_eval_cp: int = -50
    fix_first_error_move: int = 12
    middlegame_problem_score: float = 0.45
    eval_ply: int = 30
    # Routine.
    reevaluate_after_days: int = 42


PROCESS_TAGS: tuple[str, ...] = (
    "missed_threat",
    "missed_opportunity",
    "miscalculation",
    "evaluation",
    "hope_chess",
    "technique",
    "time_trouble",
)

# Weaknesses that mean "study tactics/strategy before opening theory".
TACTICAL_OR_STRATEGIC = {"missed_threat", "missed_opportunity", "miscalculation", "hope_chess", "evaluation"}

PROCESS_INFO: dict[str, dict[str, str]] = {
    "missed_threat": {
        "title": "Missed threats",
        "definition": "Your move allowed a tactic you could have stopped.",
        "training": "A blunder check before every move: their checks, captures and threats. Plus defensive puzzles.",
        "secondary": "Mixed puzzles that include defensive positions",
    },
    "missed_opportunity": {
        "title": "Missed opportunities",
        "definition": "You had a strong forcing move and played something quiet instead.",
        "training": "Mixed puzzles with no theme given, then themed sets for your top motif.",
        "secondary": "Themed blocks for your top motif",
    },
    "miscalculation": {
        "title": "Miscalculation",
        "definition": "The idea was right, but the line failed a few moves later.",
        "training": "Write the whole line out, 3–5 moves deep, before checking the answer.",
        "secondary": "Longer games",
    },
    "evaluation": {
        "title": "Misjudged positions",
        "definition": "No tactic: a bad trade, the wrong plan or the wrong pawn break.",
        "training": "Annotated master games in your openings' structures, then judge positions before checking.",
        "secondary": "Play positions out against the engine",
    },
    "hope_chess": {
        "title": "Hope chess",
        "definition": "You made a threat that only works if the opponent misses the obvious reply.",
        "training": "The blunder check, plus one rule: assume the opponent finds the best reply.",
        "secondary": "Slow games",
    },
    "technique": {
        "title": "Converting and holding",
        "definition": "You were winning, or holding a draw, and let it slip.",
        "training": "Endgame drills: basic theoretical endgames, then converting against the engine.",
        "secondary": "Rook endgame study",
    },
    "time_trouble": {
        "title": "Time trouble",
        "definition": "Errors made with under 10% of your clock left, or with no thought on a critical move.",
        "training": "Still have half your clock at move 20. Play time controls with increment.",
        "secondary": "Fewer games, longer time controls",
    },
}

# Primary + secondary training block per weakness, as (kind, label, text).
WEAKNESS_BLOCKS: dict[str, tuple[tuple[str, str, str], tuple[str, str, str]]] = {
    "missed_threat": (("own_errors", "Own errors", "Find the threat you missed in your own positions"), ("puzzles", "Puzzles", "Defensive puzzles")),
    "missed_opportunity": (("puzzles", "Puzzles", "Mixed puzzles, no theme given"), ("own_errors", "Own errors", "Find the winning move you missed")),
    "miscalculation": (("calculation", "Calculation", "Write the whole line out before checking"), ("own_errors", "Own errors", "Replay the lines that failed in your games")),
    "evaluation": (("study", "Model games", "Annotated games in your openings' structures"), ("own_errors", "Own errors", "Judge your misjudged positions again")),
    "hope_chess": (("own_errors", "Own errors", "Find the reply that refuted your threat"), ("puzzles", "Puzzles", "Defensive puzzles")),
    "technique": (("endgame", "Endgame", "Convert winning endgames against the engine"), ("own_errors", "Own errors", "Replay the positions you failed to convert")),
    "time_trouble": (("play", "Play", "A game with increment, keeping half your clock at move 20"), ("own_errors", "Own errors", "Your time-trouble errors, solved with a short timer")),
}

MOTIF_LABELS: dict[str, str] = {
    "fork": "Fork",
    "absolute_pin": "Pin",
    "skewer": "Skewer",
    "discovered_check": "Discovered check",
    "double_check": "Double check",
    "checkmate_in_k": "Mating net",
    "king_attraction": "King attraction",
}

DOMAINS: tuple[str, ...] = ("opening", "middlegame_tactics", "middlegame_positional", "endgame")

DRAW_RESULTS = {"agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"}

SLOT_LABELS = {
    "white": "As White",
    "black_vs_e4": "Black vs 1.e4",
    "black_vs_d4": "Black vs 1.d4",
    "black_vs_other": "Black vs everything else",
}

# Short, low-theory openings recommended in simple mode. Each line and trap is
# checked for legality in the tests.
SIMPLE_REPERTOIRE: dict[str, dict[str, Any]] = {
    "white": {
        "name": "Italian Game · Giuoco Pianissimo",
        "choice": "e4",
        "line": ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "c3", "Nf6", "d3", "d6", "O-O", "O-O"],
        "learn_depth": "Learn 6–8 moves",
        "why": "Simple development with no sharp lines: you reach a normal middlegame by move 8.",
        "plans": "Re1, Nbd2–f1–g3, then prepare d4",
        "trap": "Before you castle, watch for …Ng4 and …Bxf2+ tricks against f2",
        "trap_line": [],
    },
    "black_vs_e4": {
        "name": "Petrov Defence",
        "choice": "e5",
        "line": ["e4", "e5", "Nf3", "Nf6", "Nxe5", "d6", "Nf3", "Nxe4", "d4", "d5", "Bd3"],
        "learn_depth": "Learn 6 moves",
        "why": "One line to learn against 1.e4, and very hard for White to surprise you.",
        "plans": "Develop with …Be7, …O-O, …Nc6 and hold the e4 knight",
        "trap": "After 3.Nxe5, play 3…d6 first. 3…Nxe4? 4.Qe2 Nf6?? 5.Nc6+ wins the queen.",
        "trap_line": ["e4", "e5", "Nf3", "Nf6", "Nxe5", "Nxe4", "Qe2", "Nf6", "Nc6+"],
    },
    "black_vs_d4": {
        "name": "Queen's Gambit Declined",
        "choice": "d5",
        "line": ["d4", "d5", "c4", "e6", "Nc3", "Nf6", "Bg5", "Be7", "e3", "O-O"],
        "learn_depth": "Learn 5–7 moves",
        "why": "The same solid setup against almost everything White plays after 1.d4.",
        "plans": "…Nbd7, …c6, then free your game with …dxc4 and …e5, or …c5",
        "trap": "The Elephant Trap: after 4…Nbd7 5.cxd5 exd5 6.Nxd5?? Nxd5! 7.Bxd8 Bb4+ wins a piece.",
        "trap_line": ["d4", "d5", "c4", "e6", "Nc3", "Nf6", "Bg5", "Nbd7", "cxd5", "exd5", "Nxd5", "Nxd5", "Bxd8", "Bb4+"],
    },
}

BASE_ROUTINE: list[dict[str, Any]] = [
    {"day": "Mon", "focus": "Your errors + mixed puzzles", "session": "flashcards",
     "blocks": [("own_errors", "Own errors", 15, "Flashcards from your games"), ("puzzles", "Puzzles", 30, "Mixed puzzles, no theme given")]},
    {"day": "Tue", "focus": "weakness:0", "session": "weakness:0", "blocks": "weakness:0"},
    {"day": "Wed", "focus": "Openings", "session": "repertoire",
     "blocks": [("repertoire", "Openings", 25, "Drill your openings with spaced repetition"), ("study", "Model game", 20, "One annotated game in your openings")]},
    {"day": "Thu", "focus": "weakness:1", "session": "weakness:1", "blocks": "weakness:1"},
    {"day": "Fri", "focus": "Your errors + themed puzzles", "session": "flashcards",
     "blocks": [("own_errors", "Own errors", 15, "Flashcards from your games"), ("puzzles", "Themed", 30, "themed")]},
    {"day": "Sat", "focus": "Slow games", "session": "play",
     "blocks": [("play", "Play", 30, "Slow game (15+10) with the blunder check"), ("play", "Play", 30, "Second slow game")]},
    {"day": "Sun", "focus": "Self-review", "session": "review",
     "blocks": [("review", "Review", 30, "Look at Saturday's games before turning on the engine"), ("own_errors", "Log", 15, "New errors become flashcards")]},
]

ROUTINE_RULES = [
    "Review every game you play in under 10 minutes: find the critical moment and why you went wrong.",
    "In slow games, check before every move: their checks, captures and threats.",
    "Keep fast games to 30% or less of your playing time.",
    "Keep one error log. It is the data for your next check.",
]

REVIEW_STEPS_DAYS = (1, 3, 7, 21)
RETIRE_AFTER_STREAK = 3
RETIRE_MIN_INTERVAL = 7


# ---------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------

def game_id(game: Any) -> str | None:
    if isinstance(game, dict):
        return game.get("uuid") or game.get("url")
    return getattr(game, "uuid", None) or getattr(game, "url", None)


def user_color(game: EnrichedGame, username: str) -> str | None:
    key = username.strip().lower()
    if (game.white_username or "").lower() == key:
        return "white"
    if (game.black_username or "").lower() == key:
        return "black"
    return None


def orient(cp: int | None, color: str) -> int | None:
    if cp is None:
        return None
    return cp if color == "white" else -cp


def base_seconds(time_control: str | None) -> float | None:
    """Base clock in seconds for live games; None for daily ("1/259200")."""
    if not time_control or "/" in time_control:
        return None
    try:
        return float(time_control.split("+", 1)[0])
    except ValueError:
        return None


def game_score(game: EnrichedGame, color: str) -> float:
    result = (game.white_result if color == "white" else game.black_result) or ""
    if result == "win":
        return 1.0
    if result in DRAW_RESULTS:
        return 0.5
    return 0.0


def per_100(count: int, moves: int) -> float:
    return round(100 * count / moves, 2) if moves else 0.0


def is_forcing_san(san: str | None) -> bool:
    return bool(san) and ("x" in san or "+" in san or "#" in san)


def uci_to_san(fen: str, uci: str | None) -> str | None:
    if not uci:
        return None
    try:
        board = chess.Board(fen)
        return board.san(chess.Move.from_uci(uci))
    except (ValueError, AssertionError):
        return None


def clock_bucket(move: EnrichedMove, base: float | None, config: TrainingPlanConfig) -> str | None:
    if base is None or move.clock_before is None or base <= 0:
        return None
    fraction = move.clock_before / base
    if fraction > config.clock_high_fraction:
        return "over_50"
    if fraction >= config.time_trouble_clock_fraction:
        return "10_to_50"
    return "under_10"


def state_bucket(cp: int | None, config: TrainingPlanConfig) -> str | None:
    if cp is None:
        return None
    if cp > config.winning_cp:
        return "winning"
    if cp < -config.winning_cp:
        return "losing"
    return "equal"


def opponent_bucket(gap: int | None, config: TrainingPlanConfig) -> str | None:
    if gap is None:
        return None
    if gap > config.opponent_gap:
        return "higher"
    if gap < -config.opponent_gap:
        return "lower"
    return "similar"


# ---------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------

def classify_process(
    item: dict[str, Any],
    move: EnrichedMove | None,
    base: float | None,
    config: TrainingPlanConfig,
) -> str:
    """Assign the single most specific process tag (root cause) to an error."""
    before = item.get("user_eval_before_cp")
    after = item.get("user_eval_after_cp")
    line = item.get("best_line_moves") or []
    opponent_moves = int(item.get("theoretical_punishment_depth") or 0)
    tactics = item.get("tactics") or []
    played_san = item.get("san") or ""

    if move is not None and base and move.clock_before is not None:
        if move.clock_before / base < config.time_trouble_clock_fraction:
            return "time_trouble"
        if (
            move.clock_spent is not None
            and move.clock_spent < config.time_trouble_fast_move_seconds
            and move.tactical_position
        ):
            return "time_trouble"

    if before is not None and after is not None:
        if before >= config.technique_winning_cp and after < config.technique_after_cp:
            return "technique"
        if (
            move is not None
            and move.phase == "endgame"
            and abs(before) <= config.technique_drawn_cp
            and after <= config.technique_drawn_after_cp
        ):
            return "technique"

    quick = 0 < opponent_moves <= config.quick_refutation_opponent_moves
    played_threat = "+" in played_san or bool(move and move.move_is_threat)
    if played_threat and quick:
        return "hope_chess"

    best_san = uci_to_san(item["fen_before"], move.best_move_uci) if move else None
    if is_forcing_san(played_san) and quick:
        same_piece = bool(move and move.best_move_uci and move.best_move_uci[:2] == item.get("uci", "")[:2])
        if same_piece or is_forcing_san(best_san):
            return "miscalculation"

    if (
        move is not None
        and move.engine_top_move_is_forcing
        and not is_forcing_san(played_san)
        and (move.best_move_cp_gain or 0) >= config.missed_opportunity_gain_cp
    ):
        return "missed_opportunity"

    first_reply = next((m for m in line if m.get("side_to_move") != item.get("player_color")), None)
    if tactics or (
        first_reply is not None
        and is_forcing_san(first_reply.get("san"))
        and 0 < opponent_moves <= config.missed_threat_opponent_moves
    ):
        return "missed_threat"

    return "evaluation"


def classify_domain(item: dict[str, Any], move: EnrichedMove | None, process: str) -> str:
    phase = move.phase if move is not None else None
    if phase == "opening":
        return "opening"
    if phase == "endgame":
        return "endgame"
    tactical = bool(item.get("tactics")) or bool(move and move.tactical_position)
    if tactical or process in {"missed_threat", "miscalculation", "hope_chess", "missed_opportunity"}:
        return "middlegame_tactics"
    return "middlegame_positional"


def item_motifs(item: dict[str, Any]) -> list[str]:
    themes = {tag.get("theme") for tag in item.get("tactics") or [] if isinstance(tag, dict)}
    return sorted(MOTIF_LABELS[theme] for theme in themes if theme in MOTIF_LABELS)


# ---------------------------------------------------------------------
# Plan assembly
# ---------------------------------------------------------------------

@dataclass
class _GameContext:
    game: EnrichedGame
    color: str
    base: float | None
    rating: int | None
    opponent_rating: int | None
    moves_by_ply: dict[int, EnrichedMove] = field(default_factory=dict)


def build_training_plan(
    games: list[EnrichedGame],
    mistakes: list[dict[str, Any]],
    username: str,
    *,
    config: TrainingPlanConfig | None = None,
    today: date | None = None,
    previous_cards: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the plan payload. ``mistakes`` are serialized MistakeAnalysisItem
    dicts carrying a stable ``mistake_id``."""
    config = config or TrainingPlanConfig()
    today = today or date.today()

    contexts: dict[str, _GameContext] = {}
    for game in games:
        gid = game_id(game)
        color = user_color(game, username)
        if gid is None or color is None:
            continue
        rating = game.white_rating if color == "white" else game.black_rating
        opponent = game.black_rating if color == "white" else game.white_rating
        contexts[gid] = _GameContext(
            game=game,
            color=color,
            base=base_seconds(game.time_control),
            rating=rating,
            opponent_rating=opponent,
            moves_by_ply={move.ply: move for move in game.moves},
        )
    if not contexts:
        raise ValueError("None of the analysed games belong to this player.")

    errors = []
    for item in mistakes:
        if item.get("severity") not in config.error_severities:
            continue
        gid = item.get("game_uuid") or item.get("game_url")
        ctx = contexts.get(gid or "")
        if ctx is None:
            continue
        move = ctx.moves_by_ply.get(int(item["ply"]))
        process = classify_process(item, move, ctx.base, config)
        domain = classify_domain(item, move, process)
        errors.append({"item": item, "ctx": ctx, "move": move, "process": process, "domain": domain, "motifs": item_motifs(item)})

    diagnosis = _diagnosis(contexts, errors, config)
    rating = _player_rating(contexts)
    repertoire = _repertoire(contexts, errors, diagnosis, rating, config)
    routine = _routine(diagnosis, repertoire)
    cards = _cards(errors, today, previous_cards or {})

    time_classes = Counter(ctx.game.time_class or "unknown" for ctx in contexts.values())
    return {
        "metadata": {
            "username": username,
            "games_analyzed": len(contexts),
            "moves_analyzed": diagnosis["moves_analyzed"],
            "rating": rating,
            "time_classes": dict(time_classes),
            "score": round(sum(game_score(c.game, c.color) for c in contexts.values()) / len(contexts), 3),
            "created_on": today.isoformat(),
            "reevaluate_on": (today + timedelta(days=config.reevaluate_after_days)).isoformat(),
        },
        "diagnosis": diagnosis,
        "repertoire": repertoire,
        "routine": routine,
        "cards": cards,
    }


def _player_rating(contexts: dict[str, _GameContext]) -> int | None:
    ratings = [ctx.rating for ctx in contexts.values() if ctx.rating]
    return int(median(ratings)) if ratings else None


def _diagnosis(contexts: dict[str, _GameContext], errors: list[dict[str, Any]], config: TrainingPlanConfig) -> dict[str, Any]:
    moves_total = 0
    denominators: dict[str, Counter] = {"clock": Counter(), "state": Counter(), "color": Counter(), "opponent": Counter()}
    for ctx in contexts.values():
        gap = (ctx.opponent_rating - ctx.rating) if ctx.opponent_rating and ctx.rating else None
        for move in ctx.game.moves:
            if move.player_color != ctx.color:
                continue
            moves_total += 1
            for key, bucket in _move_buckets(move, ctx, gap, config).items():
                if bucket:
                    denominators[key][bucket] += 1

    numerators: dict[str, Counter] = {key: Counter() for key in denominators}
    for error in errors:
        ctx, move = error["ctx"], error["move"]
        gap = (ctx.opponent_rating - ctx.rating) if ctx.opponent_rating and ctx.rating else None
        if move is None:
            continue
        for key, bucket in _move_buckets(move, ctx, gap, config).items():
            if bucket:
                numerators[key][bucket] += 1

    count = len(errors)
    process_counts = Counter(error["process"] for error in errors)
    process_loss: dict[str, list[float]] = defaultdict(list)
    for error in errors:
        process_loss[error["process"]].append(float(error["item"].get("wp_loss") or 0.0))

    process_tags = [
        {
            "tag": tag,
            "title": PROCESS_INFO[tag]["title"],
            "count": process_counts[tag],
            "rate_per_100": per_100(process_counts[tag], moves_total),
            "share": round(process_counts[tag] / count, 3) if count else 0.0,
            "avg_wp_loss": round(sum(process_loss[tag]) / len(process_loss[tag]), 3) if process_loss[tag] else None,
        }
        for tag in PROCESS_TAGS
    ]
    process_tags.sort(key=lambda row: (row["count"], row["avg_wp_loss"] or 0), reverse=True)
    top = [
        {**row, **{k: PROCESS_INFO[row["tag"]][k] for k in ("definition", "training", "secondary")}}
        for row in process_tags
        if row["count"] > 0
    ][:3]

    domain_counts = Counter(error["domain"] for error in errors)
    domains = [
        {"domain": domain, "count": domain_counts[domain], "share": round(domain_counts[domain] / count, 3) if count else 0.0}
        for domain in DOMAINS
    ]

    motif_counts: Counter = Counter()
    motif_games: dict[str, set[str]] = defaultdict(set)
    for error in errors:
        for motif in error["motifs"]:
            motif_counts[motif] += 1
            motif_games[motif].add(game_id(error["ctx"].game) or "")
    motifs = [
        {
            "motif": motif,
            "count": n,
            "games": len(motif_games[motif]),
            "own_block": n >= config.motif_min_occurrences and len(motif_games[motif]) >= config.motif_min_games,
        }
        for motif, n in motif_counts.most_common()
    ]

    context = {
        key: [
            {"bucket": bucket, "moves": denominators[key][bucket], "errors": numerators[key][bucket],
             "rate_per_100": per_100(numerators[key][bucket], denominators[key][bucket])}
            for bucket in order
            if denominators[key][bucket]
        ]
        for key, order in {
            "clock": ("over_50", "10_to_50", "under_10"),
            "state": ("winning", "equal", "losing"),
            "color": ("white", "black"),
            "opponent": ("lower", "similar", "higher"),
        }.items()
    }

    severity_counts = Counter(error["item"].get("severity") for error in errors)
    return {
        "moves_analyzed": moves_total,
        "error_count": count,
        "blunder_count": severity_counts.get("blunder", 0),
        "rate_per_100": per_100(count, moves_total),
        "process_tags": process_tags,
        "top_weaknesses": top,
        "domains": domains,
        "motifs": motifs,
        "context": context,
        "insights": _insights(context, domains),
    }


def _move_buckets(move: EnrichedMove, ctx: _GameContext, gap: int | None, config: TrainingPlanConfig) -> dict[str, str | None]:
    return {
        "clock": clock_bucket(move, ctx.base, config),
        "state": state_bucket(orient(move.eval_before_cp, ctx.color), config),
        "color": ctx.color,
        "opponent": opponent_bucket(gap, config),
    }


def _insights(context: dict[str, list[dict[str, Any]]], domains: list[dict[str, Any]]) -> list[dict[str, str]]:
    insights: list[dict[str, str]] = []
    clock = {row["bucket"]: row for row in context.get("clock", [])}
    low, high = clock.get("under_10"), clock.get("over_50")
    if low and high and high["rate_per_100"] > 0 and low["moves"] >= 20:
        ratio = low["rate_per_100"] / high["rate_per_100"]
        if ratio >= 1.5:
            insights.append({
                "headline": f"{ratio:.1f}× more errors with under 10% of your clock left.",
                "detail": "Time trouble is a habit you can fix, not bad luck.",
            })
    opening = next((row for row in domains if row["domain"] == "opening"), None)
    if opening is not None and sum(row["count"] for row in domains):
        share = round(opening["share"] * 100)
        if share < 25:
            insights.append({
                "headline": f"Only {share}% of your errors happen in the opening.",
                "detail": f"{100 - share}% come later, in the middlegame and endgame. That is why the repertoire stays short.",
            })
        else:
            insights.append({
                "headline": f"{share}% of your errors happen in the opening.",
                "detail": "Learning your main lines a little deeper will save points.",
            })
    state = {row["bucket"]: row for row in context.get("state", [])}
    winning, equal = state.get("winning"), state.get("equal")
    if winning and equal and winning["moves"] >= 20 and winning["rate_per_100"] > equal["rate_per_100"]:
        insights.append({
            "headline": "More errors when you're winning than when it's equal.",
            "detail": "Converting winning positions gets some endgame time.",
        })
    colors = {row["bucket"]: row for row in context.get("color", [])}
    white, black = colors.get("white"), colors.get("black")
    if white and black and min(white["moves"], black["moves"]) >= 50:
        worse, better = (black, white) if black["rate_per_100"] > white["rate_per_100"] else (white, black)
        if better["rate_per_100"] and worse["rate_per_100"] / better["rate_per_100"] >= 1.2:
            insights.append({
                "headline": f"More errors as {worse['bucket'].title()} ({worse['rate_per_100']:.1f} vs {better['rate_per_100']:.1f} per 100 moves).",
                "detail": "Check whether it starts in that color's openings.",
            })
    return insights[:3]


# ---------------------------------------------------------------------
# Repertoire
# ---------------------------------------------------------------------

def opening_slot(game: EnrichedGame, color: str) -> str:
    if color == "white":
        return "white"
    first = next((move.san for move in game.moves if move.ply == 1), None)
    if first == "e4":
        return "black_vs_e4"
    if first == "d4":
        return "black_vs_d4"
    return "black_vs_other"


def player_choice(game: EnrichedGame, color: str) -> str | None:
    """The player's own opening decision: first move as White, first reply as Black."""
    ply = 1 if color == "white" else 2
    return next((move.san for move in game.moves if move.ply == ply), None)


def choice_label(choice: str, slot: str) -> str:
    return f"1.{choice}" if slot == "white" else f"1…{choice}"


def opening_family(name: str | None) -> str:
    if not name:
        return "Unknown opening"
    return name.split(":", 1)[0].strip()


def _repertoire(
    contexts: dict[str, _GameContext],
    errors: list[dict[str, Any]],
    diagnosis: dict[str, Any],
    rating: int | None,
    config: TrainingPlanConfig,
) -> dict[str, Any]:
    first_error: dict[str, int] = {}
    for error in errors:
        gid = game_id(error["ctx"].game) or ""
        move_number = int(error["item"].get("move_number") or 0)
        if move_number and (gid not in first_error or move_number < first_error[gid]):
            first_error[gid] = move_number

    # Group by the player's own move, never by the opening name: the opponent's
    # reply often decides the name (1.e4 c5 is a "Sicilian" for White too).
    groups: dict[tuple[str, str], list[_GameContext]] = defaultdict(list)
    for ctx in contexts.values():
        choice = player_choice(ctx.game, ctx.color)
        if choice:
            groups[(opening_slot(ctx.game, ctx.color), choice)].append(ctx)

    played: list[dict[str, Any]] = []
    for (slot, choice), members in groups.items():
        evals = []
        for ctx in members:
            move = ctx.moves_by_ply.get(config.eval_ply)
            value = orient(move.eval_after_cp, ctx.color) if move else None
            if value is not None:
                evals.append(max(-1000, min(1000, value)))
        first_errors = [first_error[g] for g in (game_id(c.game) for c in members) if g in first_error]
        sequences = Counter(tuple(m.san for m in sorted(c.game.moves, key=lambda x: x.ply)[:6]) for c in members)
        families = Counter(opening_family(c.game.opening_name) for c in members)
        ecos = Counter(c.game.opening_eco for c in members if c.game.opening_eco)
        played.append({
            "slot": slot,
            "slot_label": SLOT_LABELS[slot],
            "choice": choice_label(choice, slot),
            "name": ", ".join(name for name, _ in families.most_common(3)),
            "eco": ecos.most_common(1)[0][0] if ecos else None,
            "moves": san_line(sequences.most_common(1)[0][0]) if sequences else "",
            "games": len(members),
            "score": round(sum(game_score(c.game, c.color) for c in members) / len(members), 3),
            "avg_eval_at_15": round(sum(evals) / len(evals)) if evals else None,
            "first_error_move": int(median(first_errors)) if first_errors else None,
            "_raw_choice": choice,
            "_members": members,
        })
    played.sort(key=lambda row: (row["slot"], -row["games"]))

    by_slot: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in played:
        by_slot[row["slot"]].append(row)
    for slot, rows in by_slot.items():
        frequent = [row for row in rows if row["games"] >= config.opening_min_games]
        for row in rows:
            row["verdict"] = _verdict(row, frequent, config)

    top = diagnosis["top_weaknesses"][0]["tag"] if diagnosis["top_weaknesses"] else None
    opening_share = next((d["share"] for d in diagnosis["domains"] if d["domain"] == "opening"), 0.0)
    reasons = []
    if rating is not None and rating < config.simple_repertoire_below_rating:
        reasons.append(f"Rating {rating}, below the {config.simple_repertoire_below_rating} level where deeper theory starts to pay off")
    if top in TACTICAL_OR_STRATEGIC:
        reasons.append(f"Your top weakness is {PROCESS_INFO[top]['title'].lower()}, not the opening")
    if opening_share < 0.25:
        reasons.append(f"Only {round(opening_share * 100)}% of your errors happen in the opening")
    mode = "simple" if (rating is not None and rating < config.simple_repertoire_below_rating) or top in TACTICAL_OR_STRATEGIC else "theory"
    if mode == "theory":
        reasons = [f"Rating {rating}" if rating else "Rating unknown", f"{round(opening_share * 100)}% of your errors happen in the opening"]

    def describe(row: dict[str, Any]) -> str:
        return f"{row['choice']} ({row['name']}, {round(row['score'] * 100)}% in {row['games']} games)"

    recommended = []
    for slot in ("white", "black_vs_e4", "black_vs_d4"):
        rows = by_slot.get(slot, [])
        if mode == "simple":
            entry = SIMPLE_REPERTOIRE[slot]
            mine = [r for r in rows if r["_raw_choice"] == entry["choice"]]
            others = [r for r in rows if r not in mine and r["games"] >= config.opening_min_games]
            recommended.append({
                "slot": slot,
                "slot_label": SLOT_LABELS[slot],
                "name": entry["name"],
                "line": san_line(entry["line"]),
                "learn_depth": entry["learn_depth"],
                "why": entry["why"],
                "plans": entry["plans"],
                "trap": entry["trap"],
                "your_games": sum(r["games"] for r in mine),
                "your_score": _weighted_score(mine),
                "replaces": [describe(r) for r in others],
            })
        elif rows:
            main = rows[0]
            lines = Counter(tuple(m.san for m in sorted(c.game.moves, key=lambda x: x.ply)[:16]) for c in main["_members"])
            recommended.append({
                "slot": slot,
                "slot_label": SLOT_LABELS[slot],
                "name": f"{main['choice']} · {main['name'].split(', ')[0]}",
                "line": san_line(lines.most_common(1)[0][0]),
                "learn_depth": "Main line 8–12 moves, side lines you met 4–6",
                "why": f"Your most played choice here ({main['games']} games, {round(main['score'] * 100)}%).",
                "plans": None,
                "trap": None,
                "your_games": main["games"],
                "your_score": main["score"],
                "replaces": [describe(r) for r in rows[1:] if r["games"] >= config.opening_min_games],
            })
    for row in played:
        del row["_raw_choice"], row["_members"]
    return {"mode": mode, "reasons": reasons, "played": played, "recommended": recommended}


def _verdict(row: dict[str, Any], frequent: list[dict[str, Any]], config: TrainingPlanConfig) -> str:
    if row["games"] < config.opening_min_games:
        return "ignore"
    # Several of your own choices against the same move (or as White): keep one.
    if len(frequent) > 1 and row is not frequent[0]:
        return "consolidate"
    bad_eval = row["avg_eval_at_15"] is not None and row["avg_eval_at_15"] <= config.fix_first_eval_cp
    early = row["first_error_move"] is not None and row["first_error_move"] <= config.fix_first_error_move
    if bad_eval and early:
        return "fix_first"
    if row["score"] < config.middlegame_problem_score and not bad_eval:
        return "middlegame"
    return "keep"


def _weighted_score(rows: list[dict[str, Any]]) -> float | None:
    games = sum(r["games"] for r in rows)
    return round(sum(r["score"] * r["games"] for r in rows) / games, 3) if games else None


def parse_line_text(line: str) -> list[str]:
    """"1.e4 e5 2.Nf3 Nc6" (or "1. e4 e5", "1…e5") → ["e4", "e5", "Nf3", "Nc6"]."""
    moves = []
    for token in line.replace("…", " ").split():
        token = token.split(".")[-1]
        if token and not token.isdigit():
            moves.append(token)
    if not moves:
        raise ValueError("The opening line has no moves.")
    return moves


def san_line(moves: Iterable[str]) -> str:
    parts = []
    for index, san in enumerate(moves):
        parts.append(f"{index // 2 + 1}.{san}" if index % 2 == 0 else san)
    return " ".join(parts)


# ---------------------------------------------------------------------
# Routine and cards
# ---------------------------------------------------------------------

def _routine(diagnosis: dict[str, Any], repertoire: dict[str, Any]) -> dict[str, Any]:
    weaknesses = [row["tag"] for row in diagnosis["top_weaknesses"]]
    while len(weaknesses) < 2:
        weaknesses.append(["missed_threat", "miscalculation"][len(weaknesses)])
    themed = [m["motif"] for m in diagnosis["motifs"] if m["own_block"]][:3]
    opening_names = ", ".join(r["name"].split(" · ")[0] for r in repertoire["recommended"]) or "your openings"

    days = []
    for template in BASE_ROUTINE:
        session = template["session"]
        focus = template["focus"]
        weakness = None
        if isinstance(template["blocks"], str):
            index = int(template["blocks"].split(":")[1])
            weakness = weaknesses[index]
            primary, secondary = WEAKNESS_BLOCKS[weakness]
            blocks = [(*primary[:2], 25 if index == 0 else 30, primary[2]), (*secondary[:2], 25 if index == 0 else 15, secondary[2])]
            focus = f"Weakness #{index + 1} · {PROCESS_INFO[weakness]['title']}"
            session = "weakness"
        else:
            blocks = list(template["blocks"])
        rendered = []
        for kind, label, minutes, text in blocks:
            if text == "themed":
                text = " · ".join(themed) if themed else "Your most frequent motif"
            if kind == "repertoire":
                text = f"Drill {opening_names} with spaced repetition"
            rendered.append({"kind": kind, "label": label, "minutes": minutes, "text": text})
        days.append({
            "day": template["day"],
            "focus": focus,
            "session": session,
            "weakness": weakness,
            "blocks": rendered,
            "minutes": sum(block["minutes"] for block in rendered),
        })
    return {
        "base_minutes": sum(day["minutes"] for day in days),
        "days": days,
        "puzzle_split": {"mixed": 0.7, "themed": 0.3, "themed_motifs": themed},
        "rules": ROUTINE_RULES,
    }


def _cards(errors: list[dict[str, Any]], today: date, previous: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    cards = []
    for error in errors:
        item, move, ctx = error["item"], error["move"], error["ctx"]
        card_id = item.get("mistake_id")
        if not card_id:
            continue
        line = item.get("best_line_moves") or []
        prior = previous.get(card_id, {})
        cards.append({
            "card_id": card_id,
            "game_url": item.get("game_url"),
            "game_end_time": ctx.game.end_time,
            "opponent": ctx.game.black_username if ctx.color == "white" else ctx.game.white_username,
            "player_color": ctx.color,
            "move_number": item.get("move_number"),
            "ply": item.get("ply"),
            "fen_before": item["fen_before"],
            "played_san": item.get("san"),
            "played_uci": item.get("uci"),
            "best_san": uci_to_san(item["fen_before"], move.best_move_uci) if move else None,
            "best_uci": move.best_move_uci if move else None,
            "refutation_san": [m.get("san") for m in line[:4] if m.get("san")],
            "wp_loss": item.get("wp_loss"),
            "severity": item.get("severity"),
            "process": error["process"],
            "domain": error["domain"],
            "motifs": error["motifs"],
            "clock_fraction": round(move.clock_before / ctx.base, 3) if move and move.clock_before is not None and ctx.base else None,
            "eval_before_cp": item.get("user_eval_before_cp"),
            "due_on": prior.get("due_on", today.isoformat()),
            "interval_days": prior.get("interval_days", 0),
            "streak": prior.get("streak", 0),
            "reviews": prior.get("reviews", 0),
            "retired": prior.get("retired", False),
            "label": prior.get("label"),
            "note": prior.get("note"),
        })
    cards.sort(key=lambda card: card["wp_loss"] or 0, reverse=True)
    return cards


def review_card(card: dict[str, Any], grade: str, today: date | None = None) -> dict[str, Any]:
    """Spaced repetition on the 1 → 3 → 7 → 21 day ladder. A card retires after
    three correct answers in a row at intervals of 7 days or more."""
    today = today or date.today()
    interval = int(card.get("interval_days") or 0)
    streak = int(card.get("streak") or 0)
    if grade == "again":
        interval, streak = REVIEW_STEPS_DAYS[0], 0
    elif grade == "hard":
        interval = interval or REVIEW_STEPS_DAYS[0]
        streak = 0
    elif grade == "good":
        larger = [step for step in REVIEW_STEPS_DAYS if step > interval]
        interval = larger[0] if larger else REVIEW_STEPS_DAYS[-1]
        streak = streak + 1 if interval >= RETIRE_MIN_INTERVAL else 0
    else:
        raise ValueError(f"Unknown review grade: {grade}")
    return {
        **card,
        "interval_days": interval,
        "streak": streak,
        "reviews": int(card.get("reviews") or 0) + 1,
        "retired": streak >= RETIRE_AFTER_STREAK,
        "due_on": (today + timedelta(days=interval)).isoformat(),
    }
