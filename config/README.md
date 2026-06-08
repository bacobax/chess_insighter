# Statistics Configuration Guide

`global_statistics_hparams.yaml` controls how strict, sensitive, and result-driven the chess analysis is.

Think of these values as tuning knobs. They do not change the games. They change how the code interprets the games: which moves count for a metric, how severe a mistake is considered, and how multiple ingredients are combined into a score.

Most scores are on a `0.0` to `1.0` scale:

- `1.0` usually means very good performance, very high tendency, or full credit.
- `0.5` usually means neutral, partial credit, or draw-like credit.
- `0.0` usually means poor performance, no tendency, or no credit.
- `None` means the code did not have enough usable evidence to compute that metric.

## General Notes About Weights

Many sections have a `weights` block. A weight says how much that ingredient matters in the final combined score.

Example:

```yaml
weights:
  conversion_rate: 0.5
  eval_preservation_when_ahead: 0.3
  low_blunder_rate_when_ahead: 0.2
```

This means conversion rate matters most, evaluation preservation matters second, and avoiding blunders matters third.

If you raise one weight, that part matters more. If you lower it, that part matters less. In most places, weights should add up to `1.0` so the final score stays easy to interpret.

## `sampling`

### `min_samples`

This is a reliability filter.

For some metrics, the code only lets a game contribute if there are at least this many relevant moves in that game.

Example:

```yaml
min_samples: 3
```

For a tactics score:

- Game A has 5 tactical moves with usable data: included.
- Game B has 2 tactical moves with usable data: ignored.
- Game C has 3 tactical moves with usable data: included.

The reason is that one or two moves can be noisy. A single mistake should not define the whole tactical quality of a game.

Raising `min_samples` makes the analysis more conservative. Scores are based on stronger evidence, but more metrics may become `None`, especially with few games.

Lowering `min_samples` makes scores appear more often. This is useful for small datasets, but outlier moves can affect the score more.

## `complexity`

These values decide what counts as simple, complex, or very complex based on the complexity values in the analyzed games.

They are percentiles, not fixed chess values. A percentile compares a move to the rest of the moves in the dataset.

### `simple_percentile`

This sets the boundary for simple positions.

```yaml
simple_percentile: 50
```

With `50`, positions below the median complexity are treated as simple.

Raising it, for example to `60`, means more positions count as simple.

Lowering it, for example to `40`, means only the easiest positions count as simple.

This mostly affects time-management analysis, especially whether the player is spending too much time on positions the code considers simple.

### `complex_percentile`

This sets the boundary for complex positions.

```yaml
complex_percentile: 85
```

With `85`, only positions more complex than about 85% of positions are treated as complex.

Raising it makes the complex bucket stricter. Fewer moves count as calculation-heavy.

Lowering it makes the complex bucket broader. More moves are treated as calculation positions.

This affects calculation scores and time-management checks around critical positions.

### `high_percentile`

This sets the boundary for very high complexity.

```yaml
high_percentile: 90
```

Raising it means only the most extreme positions count as high complexity.

Lowering it means more positions enter the high-complexity bucket.

This mainly affects the time-spent-by-complexity breakdown.

## `opening`

These parameters control how the opening score is built.

The opening score is based on three ideas:

- Did the player stay in known opening book?
- Did the player avoid losing win probability just after the opening?
- Did the player get good results from games where they had book positions?

### `post_opening_move_count`

This controls how many player moves after the opening are used to judge whether the opening led to a stable position.

```yaml
post_opening_move_count: 6
```

With `6`, the code looks at the first 6 player moves after leaving the opening phase.

Raising it makes the metric judge a longer transition into the middlegame.

Lowering it makes the metric focus only on the immediate moment after the opening.

### `weights.book_accuracy`

This controls how much the opening score rewards staying in the opening book.

Raising it makes book knowledge matter more.

Lowering it makes the score care less about whether moves were in the opening database.

### `weights.eval_stability_after_opening`

This controls how much the opening score rewards not losing win probability after the opening.

Raising it makes the opening score more about reaching a stable, playable middlegame.

Lowering it makes early middlegame stability less important.

### `weights.result_from_opening_positions`

This controls how much game result matters for the opening score.

Raising it makes wins, draws, and losses influence the opening score more.

Lowering it makes the opening score more about move quality and position stability, rather than final result.

## `time_management`

These settings decide when the code thinks the player was in time trouble, blundered under time pressure, underthought a hard position, or overthought an easy one.

### `time_pressure_seconds`

This is the clock threshold for time trouble.

```yaml
time_pressure_seconds: 30.0
```

With `30.0`, any move played with less than 30 seconds remaining counts as a time-pressure move.

Raising it makes more moves count as time pressure.

Lowering it focuses only on more severe time trouble.

### `blunder_win_prob_loss`

This is how much win probability must drop for a move to count as a blunder in time-management analysis.

```yaml
blunder_win_prob_loss: 0.10
```

With `0.10`, a move that loses at least 10 percentage points of win probability counts as a blunder.

Raising it means only larger mistakes count.

Lowering it means smaller mistakes also count.

### `critical_underthinking_seconds`

This is the maximum thinking time that counts as underthinking in critical positions.

```yaml
critical_underthinking_seconds: 5.0
```

With `5.0`, if the player spends 5 seconds or less in a tactical or complex position, the move may count as underthought.

Raising it makes the code more likely to say the player moved too fast.

Lowering it only flags extremely fast decisions.

### `simple_overthinking_seconds`

This is the minimum thinking time that counts as overthinking in simple positions.

```yaml
simple_overthinking_seconds: 30.0
```

With `30.0`, spending 30 seconds or more on a simple position may count as overthinking.

Raising it makes overthinking harder to trigger.

Lowering it makes the code more sensitive to spending time on easy positions.

### `opponent_error_win_prob_loss`

This is used when measuring whether the player induced mistakes while defending worse positions.

```yaml
opponent_error_win_prob_loss: 0.05
```

With `0.05`, an opponent reply that loses at least 5 percentage points of win probability can count as an opponent error.

Raising it counts only larger opponent mistakes.

Lowering it counts smaller opponent inaccuracies.

### `weights.time_trouble`

This controls how much the time-management score penalizes frequently reaching low time.

Higher means time trouble frequency matters more.

### `weights.blunders_in_time_pressure`

This controls how much the time-management score penalizes blunders made while low on time.

Higher means time-pressure mistakes matter more.

### `weights.bad_time_allocation`

This controls how much the time-management score penalizes using time poorly: moving too fast in hard positions or spending too long in simple ones.

Higher means time allocation matters more.

## `game_analysis`

These settings are about repeated weaknesses and improvement over time.

The code groups mistakes by type, such as tactical mistakes, calculation mistakes, opening mistakes, endgame mistakes, time-pressure mistakes, advantage mistakes, and defensive mistakes.

### `weakness_loss_threshold`

This says how bad a recurring pattern must be before the code treats it as a weakness.

```yaml
weakness_loss_threshold: 0.08
```

With `0.08`, a bucket with average losses of 8 percentage points or more can be treated as a weakness.

Raising it means only serious recurring problems count as weaknesses.

Lowering it makes the code detect milder recurring issues.

### `improvement_delta`

This says how much better a later performance must be before it counts as improvement.

```yaml
improvement_delta: 0.02
```

With `0.02`, the player needs to reduce average loss by at least 2 percentage points for that pattern to count as improved.

Raising it requires clearer improvement.

Lowering it lets smaller improvements count.

## `advantage_capitalization`

These settings control the global score for converting good positions.

This answers questions like:

- When the player gets a winning position, do they win?
- Do they preserve the advantage?
- Do they avoid blunders while ahead?

### `winning_eval_cp`

This is the centipawn threshold for a winning position.

```yaml
winning_eval_cp: 200
```

`200` roughly means the player is about two pawns better according to evaluation.

Raising it means only clearer advantages count.

Lowering it includes smaller advantages.

### `clearly_winning_eval_cp`

This is the threshold for a clearly winning position.

```yaml
clearly_winning_eval_cp: 500
```

`500` roughly means the player is about five pawns better.

Raising it makes the clearly-winning sample stricter.

Lowering it includes more positions as clearly winning.

### `weights.conversion_rate_from_winning_positions`

This controls how much the score cares about turning winning positions into wins.

Higher means final conversion matters more.

### `weights.eval_preservation_when_ahead`

This controls how much the score cares about not letting the advantage slip.

Higher means stable technique while ahead matters more.

### `weights.low_blunder_rate_when_ahead`

This controls how much the score cares about avoiding blunders while already better.

Higher means one-move throws while ahead matter more.

## `resourcefulness`

These settings control the global score for defending bad positions.

This answers questions like:

- When the player is worse, do they save games?
- Do they improve the position?
- Do they avoid collapsing?
- Do they create chances for the opponent to go wrong?

### `worse_eval_cp`

This is the centipawn threshold for a worse position.

```yaml
worse_eval_cp: -200
```

`-200` roughly means the player is about two pawns worse.

Making it more negative, like `-300`, focuses on more serious trouble.

Making it less negative, like `-100`, includes smaller disadvantages.

### `lost_eval_cp`

This is the centipawn threshold for a lost position.

```yaml
lost_eval_cp: -500
```

`-500` roughly means the player is about five pawns worse.

Making it more negative makes the lost-position sample stricter.

Making it less negative includes more bad positions as lost.

### `weights.save_rate_from_bad_positions`

This controls how much the score rewards drawing or winning from bad positions.

Higher means the final result from bad positions matters more.

### `weights.eval_recovery_after_disadvantage`

This controls how much the score rewards improving the position after being worse.

Higher means recoveries during the game matter more.

### `weights.low_collapse_rate_when_worse`

This controls how much the score rewards avoiding blunders while worse.

Higher means defensive stability matters more.

## `result_scores`

These values convert game results into numbers.

```yaml
win: 1.0
draw: 0.5
loss: 0.0
```

With the default values:

- A win gives full credit.
- A draw gives half credit.
- A loss gives no credit.

Changing these values changes every metric that uses final results.

For example, if you set `draw: 0.4`, draws become slightly worse than half credit. If you set `draw: 0.6`, draws become slightly better than half credit.

## `player_profile`

This section controls the player style and skill profile used by `PlayerFeatureAggregator` and the opening matcher vector.

The global statistics are mostly about skill scores. The player profile is also about tendencies: whether the player chooses tactical positions, likes complexity, enters certain pawn structures, castles early, and so on.

### `complexity_scale_percentile`

This controls how raw complexity values are converted into normalized `0.0` to `1.0` style values.

```yaml
complexity_scale_percentile: 95
```

With `95`, a position around the 95th percentile of complexity is treated as near maximum complexity for the player's profile.

Raising it makes most positions look less complex after normalization.

Lowering it makes more positions look highly complex.

## `player_profile.loss_normalization`

These values say how large a mistake must be before performance gets minimum credit.

### `win_probability_loss`

```yaml
win_probability_loss: 0.25
```

With `0.25`, losing 25 percentage points of win probability is treated as a very bad move for performance scoring.

Raising it makes mistakes look less severe.

Lowering it makes mistakes look more severe.

### `centipawn_loss`

```yaml
centipawn_loss: 300
```

This is the fallback when win-probability loss is unavailable.

With `300`, losing about three pawns of evaluation is treated as a very bad move.

Raising it makes centipawn mistakes look less severe.

Lowering it makes centipawn mistakes look more severe.

## `player_profile.king_safety_performance_threshold`

This controls which positions count for king-safety performance.

```yaml
king_safety_performance_threshold: 0.65
```

With `0.65`, only positions where the player's king is considered fairly exposed or risky are included.

Raising it means only very risky king positions count.

Lowering it includes more moderate king-safety situations.

## `player_profile.material_imbalance_threshold`

This controls which positions count as material-imbalance positions.

```yaml
material_imbalance_threshold: 0.05
```

Material imbalance means the material is not just equal pieces for equal pieces. Examples include bishop pair, exchange imbalance, queenless middlegame, or different piece mixes.

Raising it counts only stronger imbalances.

Lowering it counts subtler imbalances.

## `player_profile.advantage`

This section affects the player's profile-level advantage-capitalization score.

It is similar to global `advantage_capitalization`, but it uses the player-profile sample format and can fall back to centipawn thresholds if win probability is missing.

### `win_probability_move_threshold`

This says when a move is played from an advantageous position.

```yaml
win_probability_move_threshold: 0.65
```

With `0.65`, positions where the player has at least 65% win probability count as better positions.

Raising it requires a clearer advantage.

Lowering it includes smaller advantages.

### `win_probability_game_threshold`

This says when a game counts as a conversion opportunity.

```yaml
win_probability_game_threshold: 0.70
```

With `0.70`, if the player reaches at least 70% win probability in a game, the game can count as a chance they should convert.

Raising it makes conversion chances stricter.

Lowering it counts more games as conversion chances.

### `blunder_win_probability_loss`

This says how large a win-probability drop counts as a blunder while better.

```yaml
blunder_win_probability_loss: 0.20
```

With `0.20`, losing at least 20 percentage points of win probability while better counts as a blunder.

Raising it counts only larger throws.

Lowering it makes the blunder check stricter.

### `centipawn_threshold`

This is the fallback advantage threshold when win probability is unavailable.

```yaml
centipawn_threshold: 200
```

With `200`, a position about two pawns better counts as advantageous.

Raising it requires a larger evaluation edge.

Lowering it includes smaller evaluation edges.

### `weights.accuracy_while_better`

This controls how much the profile advantage score cares about move accuracy while better.

Higher means the score rewards clean play while ahead more.

### `weights.conversion_rate`

This controls how much the score cares about winning games after getting an advantage.

Higher means final conversion matters more.

### `weights.low_blunder_rate`

This controls how much the score cares about avoiding large mistakes while ahead.

Higher means blunders from good positions hurt the score more.

## `player_profile.resourcefulness`

This section affects the player's profile-level defensive/resourcefulness score.

### `win_probability_move_threshold`

This says when a move is played from a worse position.

```yaml
win_probability_move_threshold: 0.35
```

With `0.35`, positions where the player has 35% win probability or less count as worse positions.

Raising it includes more positions as defensive situations.

Lowering it focuses only on more difficult defense.

### `win_probability_game_threshold`

This says when a game counts as a save opportunity.

```yaml
win_probability_game_threshold: 0.30
```

With `0.30`, if the player falls to 30% win probability or below, the game can count as a chance to save a bad position.

Raising it counts more games as save chances.

Lowering it requires deeper trouble before a game counts.

### `recovery_delta`

This says how much win probability must improve to count as a recovery.

```yaml
recovery_delta: 0.05
```

With `0.05`, gaining at least 5 percentage points of win probability while worse counts as a recovery.

Raising it counts only larger recoveries.

Lowering it counts smaller improvements.

### `centipawn_threshold`

This is the fallback worse-position threshold when win probability is unavailable.

```yaml
centipawn_threshold: -200
```

With `-200`, being about two pawns worse counts as a defensive position.

Making it more negative requires a worse evaluation.

Making it less negative includes milder disadvantages.

### `weights.defensive_accuracy`

This controls how much the profile resourcefulness score cares about move accuracy while worse.

Higher means clean defensive moves matter more.

### `weights.recovery_rate`

This controls how much the score cares about improving the position while worse.

Higher means practical recoveries matter more.

### `weights.save_rate`

This controls how much the score cares about drawing or winning after being worse.

Higher means final saves matter more.

## `player_profile.endgame`

This section controls endgame performance in the player profile.

The score can reward:

- accurate endgame moves,
- converting winning endgames,
- saving worse endgames,
- holding equal endgames.

### `winning_win_probability_threshold`

This says when an endgame counts as a winning endgame.

```yaml
winning_win_probability_threshold: 0.65
```

With `0.65`, endgames where the player has at least 65% win probability are treated as conversion chances.

Raising it requires clearer winning endgames.

Lowering it includes smaller advantages.

### `worse_win_probability_threshold`

This says when an endgame counts as a worse endgame.

```yaml
worse_win_probability_threshold: 0.35
```

With `0.35`, endgames where the player has 35% win probability or less are treated as save chances.

Raising it includes more endgames as defensive situations.

Lowering it focuses on worse endgames.

### `equal_win_probability_low` and `equal_win_probability_high`

These define the win-probability range for equal endgames.

```yaml
equal_win_probability_low: 0.45
equal_win_probability_high: 0.55
```

With `0.45` to `0.55`, positions around 50% win probability count as equal.

Widening the range, for example `0.40` to `0.60`, includes more endgames as equal.

Narrowing the range, for example `0.48` to `0.52`, makes equal endgames stricter.

### `weights.endgame_accuracy`

This controls how much endgame move accuracy matters.

Higher means the score cares more about individual endgame moves.

### `weights.conversion_rate`

This controls how much converting winning endgames matters.

Higher means wins from good endgames matter more.

### `weights.save_rate`

This controls how much saving worse endgames matters.

Higher means draws or wins from bad endgames matter more.

### `weights.equal_endgame_hold_rate`

This controls how much holding equal endgames matters.

Higher means not losing equal endgames matters more.

## `player_profile.diversity`

This controls how opening diversity and pawn-structure diversity are scored.

Diversity is based on two ideas:

- How many different choices appear.
- Whether one choice dominates too much.

### `entropy_weight`

This rewards balanced variety.

Higher means the score likes an even spread across many openings or structures.

### `top_share_weight`

This penalizes over-reliance on the most common opening or structure.

Higher means one dominant choice reduces diversity more.

## `player_profile.pawn_structure.weights`

These weights control `pawn_structure_sharpness`, a style feature that estimates what kinds of pawn structures the player tends to enter.

Each weight says how much that structure contributes to sharpness.

### `isolated_pawn_exposure`

Higher means isolated-pawn positions affect sharpness more.

### `doubled_pawn_exposure`

Higher means doubled-pawn positions affect sharpness more.

### `backward_pawn_exposure`

Higher means backward-pawn positions affect sharpness more when the code can detect them.

### `passed_pawn_exposure`

Higher means passed-pawn positions affect sharpness more.

### `semi_open_file_exposure`

Higher means semi-open-file structures affect sharpness more.

### `open_center_exposure`

Higher means open-center positions affect sharpness more.

Lowering any of these weights makes that structure matter less in the final pawn-structure sharpness value.
