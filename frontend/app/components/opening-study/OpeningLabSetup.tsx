import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Check, Sparkles } from "lucide-react";
import { Button } from "~/components/ui/button";
import { cn } from "~/lib/utils";
import type { EvaluationMetric, OpponentMoveOrdering, TargetColor } from "~/lib/types";
import {
  DEFAULT_EVALUATION_THRESHOLDS,
  DEFAULT_MATCHER_WEIGHTS,
  DEFAULT_WEIGHTS,
  type StudyControlsState,
} from "./OpeningStudyControls";

// ---------------------------------------------------------------------------
// Answers → controls. Every question maps to concrete control values, so the
// side panel shows exactly what the survey chose and the user can fine-tune it.
// ---------------------------------------------------------------------------

type Strictness = "open" | "balanced" | "strict" | "best";
type Level = "high" | "some" | "low";
type Breadth = "focused" | "balanced" | "broad";

export type SetupAnswers = {
  color: TargetColor;
  opponentOrdering: OpponentMoveOrdering;
  metric: EvaluationMetric;
  strictness: Strictness;
  sharpness: Level;
  systems: Level;
  memory: Level;
  breadth: Breadth;
};

// Both thresholds are percentiles among your candidate moves at each
// position, so the best alternative always survives and no node is emptied.
const THRESHOLDS: Record<EvaluationMetric, Record<Strictness, number>> = {
  engine: { open: 0, balanced: 0.4, strict: 0.7, best: 1 },
  practical: { open: 0, balanced: 0.4, strict: 0.7, best: 1 },
};

const LEVEL_VALUE: Record<Level, number> = { high: 1, some: 0.5, low: 0.1 };

const BREADTH: Record<Breadth, { topK: number; opponentTopK: number }> = {
  focused: { topK: 3, opponentTopK: 4 },
  balanced: { topK: 4, opponentTopK: 6 },
  broad: { topK: 6, opponentTopK: 10 },
};

export function controlsFromAnswers(answers: SetupAnswers): StudyControlsState {
  const threshold = THRESHOLDS[answers.metric][answers.strictness];
  return {
    targetColor: answers.color,
    ...BREADTH[answers.breadth],
    opponentMoveOrdering: answers.opponentOrdering,
    weights: {
      ...DEFAULT_WEIGHTS,
      aggressiveness: LEVEL_VALUE[answers.sharpness],
      systemness: LEVEL_VALUE[answers.systems],
      memorySimplicity: LEVEL_VALUE[answers.memory],
    },
    similarityType: "cosine",
    weightedMatching: true,
    matcherWeights: { ...DEFAULT_MATCHER_WEIGHTS },
    matchMode: "custom",
    evaluationMetric: answers.metric,
    evaluationThresholds: { ...DEFAULT_EVALUATION_THRESHOLDS, [answers.metric]: threshold },
  };
}

export const DEFAULT_ANSWERS: SetupAnswers = {
  color: "white",
  opponentOrdering: "popularity",
  metric: "engine",
  strictness: "balanced",
  sharpness: "some",
  systems: "some",
  memory: "some",
  breadth: "balanced",
};

// ---------------------------------------------------------------------------
// Questions
// ---------------------------------------------------------------------------

type Option<V extends string> = { value: V; label: string; description: string };

type Question = {
  [K in keyof SetupAnswers]: {
    key: K;
    title: string;
    help: string;
    options: (answers: SetupAnswers) => Option<SetupAnswers[K]>[];
  };
}[keyof SetupAnswers];

const QUESTIONS: Question[] = [
  {
    key: "color",
    title: "Which side do you want to build a repertoire for?",
    help: "You can switch colour at any time from the side panel.",
    options: () => [
      { value: "white", label: "White", description: "Choose your first move and your answers to Black's replies." },
      { value: "black", label: "Black", description: "Start from White's common first moves and pick your responses." },
    ],
  },
  {
    key: "opponentOrdering",
    title: "Which opponent moves should the tree prepare you for first?",
    help: "This decides which replies appear under each of your moves.",
    options: () => [
      { value: "popularity", label: "The ones people actually play", description: "Ordered by how often Lichess players choose them. Best for preparing real games." },
      { value: "engine", label: "The strongest replies", description: "Ordered by Stockfish's best defence. Best for a repertoire that holds up against anything." },
    ],
  },
  {
    key: "metric",
    title: "What makes one of your moves worth studying?",
    help: "Your moves must pass this check before they are ranked. Moves that fail it are hidden.",
    options: () => [
      { value: "engine", label: "It is objectively sound", description: "Judged by Stockfish against the other moves available in the same position." },
      { value: "practical", label: "It sets practical problems", description: "Positions that score better against real Lichess replies than against perfect defence." },
    ],
  },
  {
    key: "strictness",
    title: "How strict should that check be?",
    help: "You can move this slider later. Stricter settings give a smaller tree.",
    options: (answers) => answers.metric === "engine"
      ? [
          { value: "open", label: "Keep everything", description: "No engine filter, every catalogued move is ranked." },
          { value: "balanced", label: "Drop the weaker moves", description: "Keeps moves in the top 60% of the alternatives." },
          { value: "strict", label: "Only strong moves", description: "Keeps moves in the top 30% of the alternatives." },
          { value: "best", label: "Only the engine's top choices", description: "Keeps the best move and any move within a few centipawns of it." },
        ]
      : [
          { value: "open", label: "Keep everything", description: "No filter, every catalogued move is ranked." },
          { value: "balanced", label: "Drop the least tricky moves", description: "Keeps moves in the top 60% of the alternatives by practical edge." },
          { value: "strict", label: "Only clearly tricky moves", description: "Keeps moves in the top 30% of the alternatives by practical edge." },
          { value: "best", label: "Only the trickiest choice", description: "Keeps the move with the biggest practical edge in each position, plus near ties." },
        ],
  },
  {
    key: "sharpness",
    title: "How much do you want sharp, tactical openings?",
    help: "Sharp means tactics, complex middlegames, opposite-side castling and material imbalances.",
    options: () => [
      { value: "high", label: "A lot, I want to attack", description: "Sharp openings are ranked much higher." },
      { value: "some", label: "Some, if it fits", description: "Sharpness counts, but no more than the other factors." },
      { value: "low", label: "It doesn't matter to me", description: "Sharpness barely affects the ranking." },
    ],
  },
  {
    key: "systems",
    title: "Do you prefer playing the same setup against everything?",
    help: "Systematic openings lead to similar, repeatable pawn structures.",
    options: () => [
      { value: "high", label: "Yes, one setup I can rely on", description: "Repeatable structures are ranked much higher." },
      { value: "some", label: "A bit of both", description: "Repeatable structures count moderately." },
      { value: "low", label: "No, I like variety", description: "Repeatability barely affects the ranking." },
    ],
  },
  {
    key: "memory",
    title: "How much theory are you willing to memorise?",
    help: "Based on how many lines branch off an opening and how predictable its positions are.",
    options: () => [
      { value: "high", label: "As little as possible", description: "Openings with fewer lines to learn are ranked much higher." },
      { value: "some", label: "A reasonable amount", description: "Memory load counts moderately." },
      { value: "low", label: "I'm happy to study deep theory", description: "Memory load barely affects the ranking." },
    ],
  },
  {
    key: "breadth",
    title: "How wide should each level of the tree be?",
    help: "How many of your moves and opponent replies appear when you expand a node.",
    options: () => [
      { value: "focused", label: "Focused", description: "3 of your moves, 4 opponent replies. Easy to follow." },
      { value: "balanced", label: "Balanced", description: "4 of your moves, 6 opponent replies." },
      { value: "broad", label: "Broad", description: "6 of your moves, 10 opponent replies. Good for exploring." },
    ],
  },
];

function summaryRows(answers: SetupAnswers): { label: string; value: string }[] {
  return QUESTIONS.map((question) => {
    const option = question.options(answers).find((item) => item.value === answers[question.key]);
    return { label: question.title, value: option?.label ?? String(answers[question.key]) };
  });
}

// ---------------------------------------------------------------------------
// Persistence: per-viewer convenience in localStorage, keyed by account id.
// ---------------------------------------------------------------------------

type StoredSetup = { version: 1; answers: SetupAnswers; controls: StudyControlsState };

function storageKey(userId: string) {
  return `chess-insighter:opening-lab:v1:${userId}`;
}

export function loadStoredSetup(userId: string): StoredSetup | null {
  try {
    const raw = window.localStorage.getItem(storageKey(userId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredSetup;
    if (parsed?.version !== 1 || !parsed.controls || !parsed.answers) return null;
    return {
      ...parsed,
      answers: { ...DEFAULT_ANSWERS, ...parsed.answers },
      // Style match is in development: never restore it from older state.
      controls: { ...controlsFromAnswers({ ...DEFAULT_ANSWERS, ...parsed.answers }), ...parsed.controls, matchMode: "custom" },
    };
  } catch {
    return null;
  }
}

export function saveStoredSetup(userId: string, answers: SetupAnswers, controls: StudyControlsState) {
  try {
    const value: StoredSetup = { version: 1, answers, controls };
    window.localStorage.setItem(storageKey(userId), JSON.stringify(value));
  } catch {
    // Storage can be unavailable (private mode, blocked site data): the lab still works.
  }
}

// ---------------------------------------------------------------------------
// Full-page survey
// ---------------------------------------------------------------------------

type Props = {
  initialAnswers: SetupAnswers;
  /** True when re-running the setup: cancelling keeps the current settings. */
  canCancel: boolean;
  onComplete: (answers: SetupAnswers) => void;
  onCancel: () => void;
};

export function OpeningLabSetup({ initialAnswers, canCancel, onComplete, onCancel }: Props) {
  const [answers, setAnswers] = useState<SetupAnswers>(initialAnswers);
  const [step, setStep] = useState(0);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const total = QUESTIONS.length;
  const onSummary = step >= total;
  const question = onSummary ? null : QUESTIONS[step];
  const options = question ? question.options(answers) : [];

  useEffect(() => {
    headingRef.current?.focus();
  }, [step]);

  const choose = useCallback(
    (value: string) => {
      if (!question) return;
      setAnswers((prev) => ({ ...prev, [question.key]: value }) as SetupAnswers);
      setStep((current) => current + 1);
    },
    [question],
  );

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
      if (event.key === "Escape" && canCancel) {
        onCancel();
        return;
      }
      if (onSummary) {
        if (event.key === "Enter" && !(event.target instanceof HTMLButtonElement)) onComplete(answers);
        return;
      }
      const index = Number(event.key) - 1;
      if (Number.isInteger(index) && index >= 0 && index < options.length) {
        event.preventDefault();
        choose(options[index].value);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [answers, canCancel, choose, onCancel, onComplete, onSummary, options]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="opening-lab-setup-title"
      className="fixed inset-0 z-[100] flex flex-col overflow-y-auto"
      style={{ background: "var(--paper-dark)", color: "var(--ink)" }}
    >
      <header className="flex items-center justify-between gap-4 px-4 py-4 sm:px-8" style={{ borderBottom: "1px solid var(--line)" }}>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[.14em]" style={{ color: "var(--ink-faint)" }}>Opening lab setup</p>
          <p className="text-sm font-bold tracking-[-.02em]" style={{ fontFamily: "var(--font-display)" }}>
            OPENING LAB <span style={{ color: "var(--accent)" }}>/ TREE</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          {canCancel ? (
            <Button variant="ghost" size="sm" onClick={onCancel}>Keep current settings</Button>
          ) : (
            <Button variant="ghost" size="sm" onClick={() => onComplete({ ...DEFAULT_ANSWERS, color: initialAnswers.color })}>Skip, use defaults</Button>
          )}
        </div>
      </header>

      <div className="h-1 w-full" style={{ background: "var(--line-faint)" }} aria-hidden="true">
        <div
          className="h-full transition-[width] duration-300"
          style={{ width: `${(Math.min(step, total) / total) * 100}%`, background: "var(--accent)" }}
        />
      </div>

      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center px-4 py-10 sm:px-6">
        {question ? (
          <>
            <p className="text-xs font-semibold uppercase tracking-[.14em]" style={{ color: "var(--accent)" }}>
              Question {step + 1} of {total}
            </p>
            <h1
              id="opening-lab-setup-title"
              ref={headingRef}
              tabIndex={-1}
              className="mt-3 text-2xl font-bold leading-tight tracking-[-.02em] outline-none sm:text-3xl"
              style={{ fontFamily: "var(--font-display)" }}
            >
              {question.title}
            </h1>
            <p className="mt-2 text-sm" style={{ color: "var(--ink-soft)" }}>{question.help}</p>

            <div className="mt-8 flex flex-col gap-3" role="radiogroup" aria-labelledby="opening-lab-setup-title">
              {options.map((option, index) => {
                const selected = answers[question.key] === option.value;
                return (
                  <button
                    key={option.value}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => choose(option.value)}
                    className={cn(
                      "group flex w-full items-start gap-4 rounded-lg p-4 text-left transition-colors",
                      "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
                    )}
                    style={{
                      border: `1px solid ${selected ? "var(--accent)" : "var(--line)"}`,
                      background: selected ? "var(--glow)" : "var(--paper)",
                    }}
                  >
                    <span
                      className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded text-xs font-semibold tabular-nums"
                      style={{
                        border: "1px solid var(--line)",
                        color: selected ? "var(--accent)" : "var(--ink-faint)",
                        fontFamily: "var(--font-mono)",
                      }}
                      aria-hidden="true"
                    >
                      {index + 1}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-base font-semibold">{option.label}</span>
                      <span className="mt-0.5 block text-sm" style={{ color: "var(--ink-soft)" }}>{option.description}</span>
                    </span>
                    {selected ? <Check className="mt-1 h-4 w-4 shrink-0" style={{ color: "var(--accent)" }} aria-hidden="true" /> : null}
                  </button>
                );
              })}
            </div>
          </>
        ) : (
          <>
            <p className="text-xs font-semibold uppercase tracking-[.14em]" style={{ color: "var(--accent)" }}>Your setup</p>
            <h1
              id="opening-lab-setup-title"
              ref={headingRef}
              tabIndex={-1}
              className="mt-3 text-2xl font-bold leading-tight tracking-[-.02em] outline-none sm:text-3xl"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Ready to build your tree.
            </h1>
            <p className="mt-2 text-sm" style={{ color: "var(--ink-soft)" }}>
              These answers set the side panel. You can fine-tune every value there, or run this setup again.
            </p>
            <dl className="mt-8 flex flex-col" style={{ borderTop: "1px solid var(--line)" }}>
              {summaryRows(answers).map((row, index) => (
                <div key={row.label} className="flex flex-col gap-1 py-3 sm:flex-row sm:items-baseline sm:justify-between sm:gap-6" style={{ borderBottom: "1px solid var(--line)" }}>
                  <dt className="text-sm" style={{ color: "var(--ink-soft)" }}>{row.label}</dt>
                  <dd className="flex items-center gap-3 sm:shrink-0">
                    <span className="text-sm font-semibold">{row.value}</span>
                    <button
                      type="button"
                      onClick={() => setStep(index)}
                      className="text-xs underline-offset-2 hover:underline"
                      style={{ color: "var(--accent)" }}
                    >
                      Change
                    </button>
                  </dd>
                </div>
              ))}
            </dl>
          </>
        )}

        <div className="mt-8 flex items-center justify-between gap-3">
          <Button variant="ghost" onClick={() => setStep((current) => Math.max(0, current - 1))} disabled={step === 0}>
            <ArrowLeft className="h-4 w-4" /> Back
          </Button>
          {onSummary ? (
            <Button onClick={() => onComplete(answers)} style={{ background: "var(--accent)", color: "#0a0e0b" }}>
              <Sparkles className="h-4 w-4" /> Build my tree
            </Button>
          ) : (
            <Button variant="outline" onClick={() => setStep((current) => current + 1)}>
              Keep this answer <ArrowRight className="h-4 w-4" />
            </Button>
          )}
        </div>
        {question ? (
          <p className="mt-4 text-center text-[11px]" style={{ color: "var(--ink-faint)" }}>
            Press {options.map((_, index) => index + 1).join(", ")} to answer
          </p>
        ) : null}
      </main>
    </div>
  );
}
