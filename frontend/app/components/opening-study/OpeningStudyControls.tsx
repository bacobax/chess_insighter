import { RotateCcw, Sparkles } from "lucide-react";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { cn } from "~/lib/utils";
import type {
  EvaluationMetric,
  MatcherFeatureKey,
  MatchMode,
  OpeningStudyTreeNode,
  OpeningStudyWeights,
  OpponentMoveOrdering,
  StudySimilarityType,
  TargetColor,
} from "~/lib/types";
import { NodeInspectorPanel } from "./NodeInspectorPanel";

export type StudyControlsState = {
  /** Preferred vector source: hash from a built player report.
   *  Uses the vector computed from the exact games+filters of that report. */
  cacheHash: string;
  /** Fallback when no cacheHash: username lookup in the flat player_vectors.json.
   *  Ignores game filters. */
  username: string;
  targetColor: TargetColor;
  topK: number;
  opponentTopK: number;
  opponentMoveOrdering: OpponentMoveOrdering;
  weights: Required<OpeningStudyWeights>;
  similarityType: StudySimilarityType;
  weightedMatching: boolean;
  matcherWeights: Record<MatcherFeatureKey, number>;
  matchMode: MatchMode;
  evaluationMetric: EvaluationMetric;
};

export const DEFAULT_WEIGHTS: Required<OpeningStudyWeights> = {
  playerStyleMatch: 0.32,
  engineSoundness: 0.18,
  aggressiveness: 0.15,
  practicalGamble: 0.10,
  systemness: 0.13,
  memorySimplicity: 0.12,
};

export const DEFAULT_MATCHER_WEIGHTS: Record<MatcherFeatureKey, number> = {
  tactical_density: 1.00,
  quiet_position_density: 0.80,
  king_safety_risk: 0.80,
  early_castling_tendency: 0.50,
  opposite_side_castling_tendency: 0.60,
  middlegame_complexity: 0.90,
  pawn_structure_sharpness: 1.00,
  material_imbalance: 0.90,
  endgame_likelihood_proxy: 0.40,
};

type WeightKey = keyof Required<OpeningStudyWeights>;

// Which score-weight dimensions are active per mode.
// Mirrors ALLOWED_WEIGHTS_BY_MODE in utils/opening_study_tree.py (camelCase keys).
const ALLOWED_BY_MODE: Record<MatchMode, Set<WeightKey>> = {
  style: new Set(["playerStyleMatch", "engineSoundness", "practicalGamble", "systemness", "memorySimplicity"]),
  custom: new Set(["engineSoundness", "aggressiveness", "practicalGamble", "systemness", "memorySimplicity"]),
};

function allowedFor(mode: MatchMode, evaluationMetric: EvaluationMetric): Set<WeightKey> {
  const selected = evaluationMetric === "engine" ? "engineSoundness" : "practicalGamble";
  return new Set(
    [...ALLOWED_BY_MODE[mode]].filter(
      (key) => (key !== "engineSoundness" && key !== "practicalGamble") || key === selected,
    ),
  );
}

const MODE_DESCRIPTIONS: Record<MatchMode, string> = {
  style: "Finds openings that fit YOUR playing style, using your chosen evaluation signal alongside systemness and memory.",
  custom: "Ranks openings by objective and practical properties, including how human reply popularity differs from best defense. Style match is hidden.",
};

// Descriptions shown as tooltips on the score weight labels.
const WEIGHT_DESCRIPTIONS: Record<WeightKey, string> = {
  playerStyleMatch: "How closely this opening matches your playing style across all 9 dimensions.",
  engineSoundness: "Stockfish centipawn utility from your target color's perspective. Equal positions are 50%; losing positions drop toward 0%.",
  aggressiveness: "35 × tactical density + 25 × complexity + 20 × opp-side castling + 20 × material imbalance.",
  practicalGamble: "How much better the position scores against popularity-weighted Lichess replies than against Stockfish's best defense.",
  systemness: "65 × (1 − entropy) + 35 × (1 − diversity) — higher means more principled, repeatable positions.",
  memorySimplicity: "55 × fewer lines + 25 × structure consistency + 20 × position predictability.",
};

// The 9 style features in the player / opening vectors.
const STYLE_FEATURE_FIELDS: Array<{
  key: string;
  label: string;
  description: string;
  color: string;
}> = [
  { key: "tactical_density",              label: "Tactical",      description: "How often you play in tactical positions",                           color: "#dc2626" },
  { key: "quiet_position_density",        label: "Quiet",         description: "How often you prefer quiet / strategic moves",                       color: "#2563eb" },
  { key: "king_safety_risk",              label: "King risk",     description: "Your tolerance for king exposure in the middlegame",                 color: "#f59e0b" },
  { key: "early_castling_tendency",       label: "Early castle",  description: "How quickly you castle (higher = earlier on average)",               color: "#059669" },
  { key: "opposite_side_castling_tendency", label: "Opp. castle", description: "How often you and your opponent castle on opposite sides",           color: "#7c3aed" },
  { key: "middlegame_complexity",         label: "Complexity",    description: "Your preference for complex, high-tension middlegames",              color: "#0891b2" },
  { key: "pawn_structure_sharpness",      label: "Pawn sharp.",   description: "How sharp / asymmetric your pawn structures tend to be",             color: "#be185d" },
  { key: "material_imbalance",            label: "Material imb.", description: "How often you play with material imbalances (e.g. exchange sac)",   color: "#ea580c" },
  { key: "endgame_likelihood_proxy",      label: "Endgame",       description: "How often your games reach the endgame phase",                      color: "#16a34a" },
];

// Labels for the 9 matcher feature weight sliders.
const MATCHER_FEATURE_FIELDS: Array<{ key: MatcherFeatureKey; label: string; color: string }> = [
  { key: "tactical_density",                label: "Tactical",      color: "#dc2626" },
  { key: "quiet_position_density",          label: "Quiet",         color: "#2563eb" },
  { key: "king_safety_risk",                label: "King risk",     color: "#f59e0b" },
  { key: "early_castling_tendency",         label: "Early castle",  color: "#059669" },
  { key: "opposite_side_castling_tendency", label: "Opp. castle",   color: "#7c3aed" },
  { key: "middlegame_complexity",           label: "Complexity",    color: "#0891b2" },
  { key: "pawn_structure_sharpness",        label: "Pawn sharp.",   color: "#be185d" },
  { key: "material_imbalance",              label: "Material imb.", color: "#ea580c" },
  { key: "endgame_likelihood_proxy",        label: "Endgame",       color: "#16a34a" },
];

const WEIGHT_FIELDS: { key: WeightKey; label: string; color: string }[] = [
  { key: "playerStyleMatch", label: "Style",         color: "#2563eb" },
  { key: "engineSoundness",  label: "Engine",        color: "#0f766e" },
  { key: "aggressiveness",   label: "Aggro",         color: "#dc2626" },
  { key: "practicalGamble",  label: "Practical gamble", color: "#d97706" },
  { key: "systemness",       label: "System",        color: "#059669" },
  { key: "memorySimplicity", label: "Mem. simplicity", color: "#7c3aed" },
];

/**
 * Move one weight to `newValue` and redistribute the delta proportionally
 * among the other ALLOWED weights so their sum stays exactly 1.0.
 * Disallowed keys are kept at 0 and never touched.
 */
function redistributeWeights(
  weights: Required<OpeningStudyWeights>,
  changedKey: WeightKey,
  newValue: number,
  mode: MatchMode,
  evaluationMetric: EvaluationMetric,
): Required<OpeningStudyWeights> {
  const allowed = allowedFor(mode, evaluationMetric);
  const clamped = Math.max(0, Math.min(1, newValue));
  const others = WEIGHT_FIELDS.map((f) => f.key).filter((k) => k !== changedKey && allowed.has(k));
  const sumOthers = others.reduce((s, k) => s + weights[k], 0);
  const remaining = 1 - clamped;

  const next = { ...weights, [changedKey]: clamped } as Required<OpeningStudyWeights>;

  if (sumOthers <= 0) {
    const each = remaining / others.length;
    for (const k of others) next[k] = Math.max(0, each);
  } else {
    for (const k of others) {
      next[k] = Math.max(0, (weights[k] / sumOthers) * remaining);
    }
  }

  return next;
}

/**
 * When switching modes, zero disallowed keys and renormalize allowed ones
 * so they still sum to 1.0.
 */
export function applyModeToWeights(
  weights: Required<OpeningStudyWeights>,
  newMode: MatchMode,
  evaluationMetric: EvaluationMetric,
): Required<OpeningStudyWeights> {
  const allowed = allowedFor(newMode, evaluationMetric);
  const next = { ...weights } as Required<OpeningStudyWeights>;
  // Zero disallowed.
  for (const { key } of WEIGHT_FIELDS) {
    if (!allowed.has(key)) next[key] = 0;
  }
  // Renormalize allowed to sum = 1.
  const sum = WEIGHT_FIELDS.filter(({ key }) => allowed.has(key)).reduce((s, { key }) => s + next[key], 0);
  if (sum <= 0) {
    // Fallback: equal split.
    const each = 1 / allowed.size;
    for (const key of allowed) next[key] = each;
  } else {
    for (const key of allowed) {
      next[key] = next[key] / sum;
    }
  }
  return next;
}

function VectorSourceBadge({ cacheHash }: { cacheHash: string }) {
  if (cacheHash) {
    return (
      <div className="rounded-md border border-emerald-200 bg-emerald-50 p-2 text-xs text-emerald-800">
        <span className="font-medium">Report vector</span>
        <br />
        <span className="font-mono text-[10px] text-emerald-600">{cacheHash.slice(0, 16)}…</span>
        <br />
        <span className="text-emerald-600">Game filters from the report apply.</span>
      </div>
    );
  }
  return (
    <div className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
      <span className="font-medium">Flat cache fallback</span>
      <br />
      Game filters (time class, rated, dates) are <span className="font-medium">not</span> applied.
      Build a report first for accurate suggestions.
    </div>
  );
}

type Props = {
  state: StudyControlsState;
  loading: boolean;
  onChange: (patch: Partial<StudyControlsState>) => void;
  onGenerate: () => void;
  onReset: () => void;
  selectedNode?: OpeningStudyTreeNode | null;
  playerVector?: Record<string, number> | null;
};

export function OpeningStudyControls({ state, loading, onChange, onGenerate, onReset, selectedNode, playerVector }: Props) {
  const canGenerate = !loading && (state.cacheHash.trim() !== "" || state.username.trim() !== "");

  const allowedKeys = allowedFor(state.matchMode, state.evaluationMetric);

  function handleWeightChange(key: WeightKey, newValue: number) {
    onChange({ weights: redistributeWeights(state.weights, key, newValue, state.matchMode, state.evaluationMetric) });
  }

  function handleModeChange(newMode: MatchMode) {
    onChange({ matchMode: newMode, weights: applyModeToWeights(state.weights, newMode, state.evaluationMetric) });
  }

  function handleEvaluationMetricChange(evaluationMetric: EvaluationMetric) {
    const selected = evaluationMetric === "engine" ? "engineSoundness" : "practicalGamble";
    const previous = evaluationMetric === "engine" ? "practicalGamble" : "engineSoundness";
    const transferred = {
      ...state.weights,
      [selected]: state.weights[selected] + state.weights[previous],
      [previous]: 0,
    };
    onChange({
      evaluationMetric,
      weights: applyModeToWeights(transferred, state.matchMode, evaluationMetric),
    });
  }

  function handleMatcherWeightChange(key: MatcherFeatureKey, newValue: number) {
    onChange({ matcherWeights: { ...state.matcherWeights, [key]: Math.max(0, Math.min(2, newValue)) } });
  }

  return (
    <div className="flex w-72 shrink-0 flex-col gap-4 overflow-y-auto p-4" style={{ backgroundColor: "var(--paper)", borderRight: "1px solid var(--line)" }}>
      <div>
        <h2 className="text-sm font-semibold text-slate-900">Opening Study Tree</h2>
        <p className="mt-1 text-xs text-slate-500">
          Style-matched, lazily expanded opening suggestions. Click a node to expand its branch.
        </p>
      </div>

      <VectorSourceBadge cacheHash={state.cacheHash} />

      <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
        Report ID
        <Input
          value={state.cacheHash}
          placeholder="Open from a saved report"
          onChange={(event) => onChange({ cacheHash: event.target.value })}
        />
        <span className="text-[10px] text-slate-400">
          Owner-bound report reference — ensures correct game filters.
        </span>
      </label>

      <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
        Username (flat-cache fallback)
        <Input
          value={state.username}
          placeholder="chess.com username"
          onChange={(event) => onChange({ username: event.target.value })}
        />
      </label>

      <div className="flex flex-col gap-1 text-xs font-medium text-slate-600">
        Target color
        <div className="flex gap-2">
          {(["white", "black"] as TargetColor[]).map((color) => (
            <button
              key={color}
              type="button"
              onClick={() => onChange({ targetColor: color })}
              className={cn(
                "flex-1 rounded-md border px-3 py-2 text-sm capitalize transition-colors",
                state.targetColor === color
                  ? "border-slate-900 bg-slate-900 text-white"
                  : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50",
              )}
            >
              {color}
            </button>
          ))}
        </div>
      </div>

      <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
        Your moves shown: {state.topK}
        <input
          type="range"
          min={1}
          max={10}
          step={1}
          value={state.topK}
          onChange={(event) => onChange({ topK: Number(event.target.value) })}
          className="accent-slate-900"
        />
      </label>

      <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
        Opponent responses shown: {state.opponentTopK}
        <input
          type="range"
          min={1}
          max={20}
          step={1}
          value={state.opponentTopK}
          onChange={(event) => onChange({ opponentTopK: Number(event.target.value) })}
          className="accent-slate-900"
        />
      </label>

      <div className="flex flex-col gap-1 text-xs font-medium text-slate-600">
        Opponent move order
        <div className="flex gap-2">
          {(["engine", "popularity"] as OpponentMoveOrdering[]).map((ordering) => (
            <button
              key={ordering}
              type="button"
              onClick={() => onChange({ opponentMoveOrdering: ordering })}
              className={cn(
                "flex-1 rounded-md border px-2 py-1.5 text-[11px] transition-colors",
                state.opponentMoveOrdering === ordering
                  ? "border-slate-900 bg-slate-900 text-white"
                  : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50",
              )}
            >
              {ordering === "engine" ? "Engine score" : "Popularity"}
            </button>
          ))}
        </div>
        <p className="text-[10px] text-slate-400">
          Orders opponent replies by strongest engine defense or Lichess play rate.
        </p>
      </div>

      {/* Match mode toggle */}
      <div className="flex flex-col gap-1 text-xs font-medium text-slate-600">
        Scoring mode
        <div className="flex gap-2">
          {(["style", "custom"] as MatchMode[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => handleModeChange(m)}
              className={cn(
                "flex-1 rounded-md border px-2 py-1.5 text-[11px] capitalize transition-colors",
                state.matchMode === m
                  ? "border-slate-900 bg-slate-900 text-white"
                  : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50",
              )}
            >
              {m === "style" ? "Style match" : "Custom"}
            </button>
          ))}
        </div>
        <p className="text-[10px] text-slate-400">{MODE_DESCRIPTIONS[state.matchMode]}</p>
      </div>

      <div className="flex flex-col gap-1 text-xs font-medium text-slate-600">
        Evaluation signal
        <div className="flex gap-2">
          {(["engine", "practical"] as EvaluationMetric[]).map((metric) => (
            <button
              key={metric}
              type="button"
              onClick={() => handleEvaluationMetricChange(metric)}
              className={cn(
                "flex-1 rounded-md border px-2 py-1.5 text-[11px] transition-colors",
                state.evaluationMetric === metric
                  ? "border-slate-900 bg-slate-900 text-white"
                  : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50",
              )}
            >
              {metric === "engine" ? "Engine" : "Practical gamble"}
            </button>
          ))}
        </div>
        <p className="text-[10px] text-slate-400">Only the selected evaluation metric contributes to Study Score.</p>
      </div>

      {/* Score weights — simplex sliders: moving one redistributes the rest */}
      <div className="flex flex-col gap-1 rounded-md border border-slate-200 p-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-medium text-slate-600">Score weights</span>
          <button
            type="button"
            onClick={() => onChange({ weights: applyModeToWeights({ ...DEFAULT_WEIGHTS }, state.matchMode, state.evaluationMetric) })}
            className="text-[10px] text-slate-400 hover:text-slate-600"
          >
            reset
          </button>
        </div>

        {WEIGHT_FIELDS.map(({ key, label, color }) => {
          const active = allowedKeys.has(key);
          const pct = Math.round(state.weights[key] * 100);
          return (
            <div key={key} className={cn("flex flex-col gap-0.5", !active && "opacity-35")}>
              <div className="flex items-center justify-between text-[11px]">
                <span className="font-medium text-slate-600" title={active ? WEIGHT_DESCRIPTIONS[key] : "Disabled in this mode"}>{label}</span>
                <span className="tabular-nums text-slate-500">{active ? `${pct}%` : "—"}</span>
              </div>
              <div className="relative flex items-center">
                {/* Filled track behind the native slider */}
                <div className="pointer-events-none absolute left-0 top-1/2 h-1.5 w-full -translate-y-1/2 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="h-full rounded-full transition-[width] duration-75"
                    style={{ width: `${pct}%`, backgroundColor: active ? color : "#94a3b8" }}
                  />
                </div>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.01}
                  value={state.weights[key]}
                  disabled={!active}
                  onChange={(event) => handleWeightChange(key, Number(event.target.value))}
                  className={cn(
                    "weight-slider relative w-full appearance-none bg-transparent",
                    active ? "cursor-pointer" : "cursor-not-allowed",
                  )}
                  style={
                    {
                      "--thumb-color": active ? color : "#94a3b8",
                      WebkitAppearance: "none",
                    } as React.CSSProperties
                  }
                />
              </div>
            </div>
          );
        })}

        {/* Stacked bar showing the current weight distribution */}
        <div className="mt-2 flex h-2 w-full overflow-hidden rounded-full">
          {WEIGHT_FIELDS.map(({ key, color }) => {
            const active = allowedKeys.has(key);
            return (
              <div
                key={key}
                className="h-full transition-[flex] duration-75"
                style={{ flex: state.weights[key], backgroundColor: active ? color : "transparent" }}
                title={`${WEIGHT_FIELDS.find((f) => f.key === key)?.label}: ${Math.round(state.weights[key] * 100)}%`}
              />
            );
          })}
        </div>
      </div>

      {/* Matching configuration */}
      <div className="flex flex-col gap-2 rounded-md border border-slate-200 p-3">
        <span className="text-xs font-medium text-slate-600">Style matching</span>

        <div className="flex flex-col gap-1 text-xs font-medium text-slate-600">
          Similarity
          <div className="flex gap-2">
            {(["cosine", "dot_product"] as StudySimilarityType[]).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => onChange({ similarityType: mode })}
                className={cn(
                  "flex-1 rounded-md border px-2 py-1.5 text-[11px] transition-colors",
                  state.similarityType === mode
                    ? "border-slate-900 bg-slate-900 text-white"
                    : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50",
                )}
              >
                {mode === "cosine" ? "Cosine" : "Dot product"}
              </button>
            ))}
          </div>
          <p className="text-[10px] text-slate-400">
            {state.similarityType === "cosine"
              ? "Cosine: angle-based — ignores vector magnitude, measures direction only."
              : "Dot product: magnitude-sensitive — higher values for larger feature values."}
          </p>
        </div>

        <div className="flex flex-col gap-1 text-xs font-medium text-slate-600">
          Weighting
          <div className="flex gap-2">
            {([true, false] as const).map((w) => (
              <button
                key={String(w)}
                type="button"
                onClick={() => onChange({ weightedMatching: w })}
                className={cn(
                  "flex-1 rounded-md border px-2 py-1.5 text-[11px] transition-colors",
                  state.weightedMatching === w
                    ? "border-slate-900 bg-slate-900 text-white"
                    : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50",
                )}
              >
                {w ? "Weighted" : "Unweighted"}
              </button>
            ))}
          </div>
          <p className="text-[10px] text-slate-400">
            {state.weightedMatching
              ? "Custom per-feature importance weights applied."
              : "All 9 features treated equally (weight = 1)."}
          </p>
        </div>

        {state.weightedMatching && (
          <div className="flex flex-col gap-1">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-medium text-slate-500">Feature weights</span>
              <button
                type="button"
                onClick={() => onChange({ matcherWeights: { ...DEFAULT_MATCHER_WEIGHTS } })}
                className="text-[10px] text-slate-400 hover:text-slate-600"
              >
                reset
              </button>
            </div>
            {MATCHER_FEATURE_FIELDS.map(({ key, label, color }) => {
              const value = state.matcherWeights[key] ?? 1.0;
              const pct = Math.round((value / 2) * 100);
              return (
                <div key={key} className="flex flex-col gap-0.5">
                  <div className="flex items-center justify-between text-[10px]">
                    <span className="text-slate-600">{label}</span>
                    <span className="tabular-nums text-slate-500">{value.toFixed(2)}</span>
                  </div>
                  <div className="relative flex items-center">
                    <div className="pointer-events-none absolute left-0 top-1/2 h-1 w-full -translate-y-1/2 overflow-hidden rounded-full bg-slate-100">
                      <div
                        className="h-full rounded-full transition-[width] duration-75"
                        style={{ width: `${pct}%`, backgroundColor: color }}
                      />
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={2}
                      step={0.05}
                      value={value}
                      onChange={(event) => handleMatcherWeightChange(key, Number(event.target.value))}
                      className="weight-slider relative w-full cursor-pointer appearance-none bg-transparent"
                      style={{ "--thumb-color": color, WebkitAppearance: "none" } as React.CSSProperties}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Your style — read-only player vector bars */}
      {playerVector && (
        <div className="flex flex-col gap-1 rounded-md border border-slate-200 p-3">
          <div className="mb-1">
            <span className="text-xs font-medium text-slate-600">Your style</span>
            <p className="mt-0.5 text-[10px] text-slate-400">
              Derived from your analyzed games. Used to match openings.
            </p>
          </div>
          {STYLE_FEATURE_FIELDS.map(({ key, label, color, description }) => {
            const value = playerVector[key] ?? 0;
            const pct = Math.round(value * 100);
            return (
              <div key={key} className="flex flex-col gap-0.5" title={description}>
                <div className="flex items-center justify-between text-[11px]">
                  <span className="font-medium text-slate-600">{label}</span>
                  <span className="tabular-nums text-slate-500">{pct}%</span>
                </div>
                <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: color }} />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Node inspector — appears when a node is selected */}
      {selectedNode && (
        <NodeInspectorPanel node={selectedNode} playerVector={playerVector ?? null} />
      )}

      <div className="mt-auto flex flex-col gap-2">
        <Button onClick={onGenerate} disabled={!canGenerate}>
          <Sparkles className="h-4 w-4" /> {loading ? "Generating…" : "Generate suggestions"}
        </Button>
        <Button variant="outline" onClick={onReset} disabled={loading}>
          <RotateCcw className="h-4 w-4" /> Reset tree
        </Button>
      </div>
    </div>
  );
}
