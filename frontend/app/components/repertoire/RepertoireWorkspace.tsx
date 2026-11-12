import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { ExternalLink, Loader2, Settings2 } from "lucide-react";
import { Button } from "~/components/ui/button";
import { useAuth } from "~/components/auth/auth-provider";
import type { StudyControlsState } from "~/components/opening-study/OpeningStudyControls";
import type { RepertoireColor, RepertoireLines, RepertoireSettings } from "~/lib/types";
import { RepertoireBuilder } from "./RepertoireBuilder";
import { RepertoireDrill } from "./RepertoireDrill";
import { formatPercent, numberedSan, useRepertoire, useRepertoireLines, type RepertoireApi } from "./repertoire-hooks";

export type RepertoireMode = "build" | "drill";

type Props = {
  color: RepertoireColor;
  /** Where this part of the repertoire starts, e.g. ["e2e4"] for "Black vs 1.e4". */
  startPrefixUci?: string[];
  /** Opening Lab controls, for Lab study scores in Build mode. */
  studyControls?: StudyControlsState;
  /** SAN lines used to fill an empty repertoire (e.g. the training plan's openings). */
  seedLines?: string[];
  /** Fill an empty repertoire with `seedLines` (or the default short repertoire) without asking. */
  autoSeed?: boolean;
  initialMode?: RepertoireMode;
  /** Show a link that opens this repertoire in the Opening Lab. */
  labLink?: boolean;
  active?: boolean;
};

/** Your saved repertoire for one colour: build it move by move, then drill its lines. */
export function RepertoireWorkspace({
  color,
  startPrefixUci = [],
  studyControls,
  seedLines,
  autoSeed = false,
  initialMode = "build",
  labLink = false,
  active = true,
}: Props) {
  const { user } = useAuth();
  const api = useRepertoire(color);
  const [mode, setMode] = useState<RepertoireMode>(initialMode);
  const [jump, setJump] = useState<{ path: string[]; nonce: number }>({ path: startPrefixUci, nonce: 0 });
  const [seeding, setSeeding] = useState(false);
  const [seedError, setSeedError] = useState<string | null>(null);
  const seededOnce = useRef(false);
  const lines = useRepertoireLines(color, startPrefixUci, api.version, active && api.repertoire !== null);
  const empty = api.repertoire !== null && Object.keys(api.repertoire.choices).length === 0;

  async function seed() {
    setSeeding(true);
    setSeedError(null);
    try {
      await api.seed(seedLines);
    } catch (err) {
      setSeedError(err instanceof Error ? err.message : "Could not add the suggested moves.");
    } finally {
      setSeeding(false);
    }
  }

  useEffect(() => {
    if (autoSeed && empty && !seededOnce.current) {
      seededOnce.current = true;
      void seed();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSeed, empty]);

  function openInBuilder(prefixUci: string[]) {
    setMode("build");
    setJump((current) => ({ path: prefixUci, nonce: current.nonce + 1 }));
  }

  if (api.error) return <p className="text-sm" style={{ color: "var(--coral)" }}>{api.error}</p>;
  if (!api.repertoire) {
    return <p className="flex items-center gap-2 text-sm" style={{ color: "var(--ink-soft)" }}><Loader2 className="h-4 w-4 animate-spin" /> Loading your repertoire…</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="tp-seg" role="group" aria-label="Repertoire mode">
          <button type="button" aria-pressed={mode === "build"} onClick={() => setMode("build")}>Build</button>
          <button type="button" aria-pressed={mode === "drill"} onClick={() => setMode("drill")}>Drill</button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SettingsEditor api={api} />
          {labLink ? (
            <Link to={`/opening-study?color=${color}&view=repertoire`} className="inline-flex items-center gap-1.5 text-xs" style={{ color: "var(--ink-soft)" }}>
              Open in the Opening Lab <ExternalLink className="h-3.5 w-3.5" />
            </Link>
          ) : null}
        </div>
      </div>

      {empty && !seeding ? (
        <div className="rounded-xl p-4 text-sm" style={{ border: "1px dashed var(--line)", color: "var(--ink-soft)" }}>
          <p style={{ margin: 0 }}>
            Your {color} repertoire is empty. Choose your moves on the board, or start from a short suggested repertoire and change it as you go.
          </p>
          <Button className="mt-3" size="sm" variant="outline" onClick={seed}>Start from the suggested moves</Button>
          {seedError ? <p className="mt-2" style={{ color: "var(--coral)" }}>{seedError}</p> : null}
        </div>
      ) : null}
      {seeding ? <p className="flex items-center gap-2 text-sm" style={{ color: "var(--ink-soft)" }}><Loader2 className="h-4 w-4 animate-spin" /> Adding the suggested moves…</p> : null}
      {!empty && !seeding && seedLines?.length ? (
        <p className="text-xs" style={{ color: "var(--ink-soft)", margin: 0 }}>
          Missing some of your plan's openings?{" "}
          <button type="button" className="underline underline-offset-2" style={{ color: "var(--ink)" }} onClick={seed}>
            Add the plan's moves
          </button>{" "}
          where you haven't chosen a move yet. Your own choices are kept.
          {seedError ? <span style={{ color: "var(--coral)" }}> {seedError}</span> : null}
        </p>
      ) : null}

      <CoverageSummary lines={lines.lines} loading={lines.loading} error={lines.error} onRetry={lines.retry} />

      <div className={mode === "build" ? "" : "hidden"}>
        <RepertoireBuilder
          color={color}
          api={api}
          startPrefixUci={startPrefixUci}
          studyControls={studyControls}
          jump={jump}
          active={active && mode === "build"}
        />
        <GapList lines={lines.lines} startPly={startPrefixUci.length} onOpen={openInBuilder} />
      </div>
      {mode === "drill" ? (
        <RepertoireDrill
          color={color}
          lines={lines.lines?.lines ?? []}
          startPly={startPrefixUci.length}
          progressKey={`rep:drill:${user?.id ?? "anonymous"}:${color}`}
          onBuild={openInBuilder}
          active={active}
        />
      ) : null}
    </div>
  );
}

/** How much of your games the repertoire prepares you for, and what is still open. */
function CoverageSummary({ lines, loading, error, onRetry }: { lines: RepertoireLines | null; loading: boolean; error: string | null; onRetry: () => void }) {
  if (error) {
    return <p className="text-sm" style={{ color: "var(--coral)" }}>{error} <Button size="sm" variant="ghost" onClick={onRetry}>Retry</Button></p>;
  }
  if (!lines) return null;
  const c = lines.coverage;
  const parts = [
    { key: "ready", value: c.complete + c.outOfBook, color: "var(--accent)", label: "prepared" },
    { key: "open", value: c.needsChoice, color: "var(--acid)", label: "need your move" },
    { key: "unknown", value: c.pending + c.noData, color: "var(--ink-faint)", label: "no data yet" },
    { key: "rare", value: c.pruned, color: "var(--line)", label: "rare replies, not drilled" },
  ];
  return (
    <section aria-label="Repertoire coverage" className="flex flex-col gap-2">
      <p className="text-sm" style={{ color: "var(--ink-soft)", margin: 0 }}>
        Your lines prepare you for <b style={{ color: "var(--ink)" }}>{formatPercent(c.complete + c.outOfBook)}</b> of your games
        {c.needsChoice > 0 ? <>; <b style={{ color: "var(--acid)" }}>{formatPercent(c.needsChoice)}</b> still need one of your moves</> : null}.
        {loading ? <Loader2 className="ml-2 inline h-3.5 w-3.5 animate-spin" aria-label="Still loading" /> : null}
      </p>
      <div className="flex h-2.5 overflow-hidden rounded-full" style={{ background: "var(--paper-dark)" }} role="img" aria-label="Coverage">
        {parts.map((part) => (part.value > 0 ? <span key={part.key} style={{ flexGrow: part.value, background: part.color }} title={`${part.label}: ${formatPercent(part.value)}`} /> : null))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px]" style={{ color: "var(--ink-soft)" }}>
        {parts.map((part) => (
          <span key={part.key} className="inline-flex items-center gap-1.5">
            <i className="inline-block h-2 w-2 rounded-full" style={{ background: part.color }} />
            {part.label} {formatPercent(part.value)}
          </span>
        ))}
      </div>
    </section>
  );
}

/** The most common lines where you have not chosen your move yet. */
function GapList({ lines, startPly, onOpen }: { lines: RepertoireLines | null; startPly: number; onOpen: (prefixUci: string[]) => void }) {
  const gaps = useMemo(() => (lines?.lines ?? []).filter((line) => line.status === "needs_choice").slice(0, 8), [lines]);
  if (!gaps.length) return null;
  return (
    <section className="mt-6 flex flex-col gap-2" aria-labelledby="rep-gaps">
      <h3 id="rep-gaps" className="text-xs font-semibold uppercase tracking-[.12em]" style={{ color: "var(--ink-soft)" }}>
        Most common positions without your move
      </h3>
      <ul className="tp-variation-list">
        {gaps.map((line) => {
          const from = Math.max(startPly, line.san.length - 6);
          return (
            <li key={line.id} data-state="missing">
              <span className="tp-variation-icon" aria-hidden="true">·</span>
              <span className="tp-variation-main">
                <b>{line.openingName ?? "Unnamed line"}</b>
                <small>{from > 0 ? "… " : ""}{numberedSan(line.san, from)}</small>
              </span>
              <span className="tp-variation-meta"><b>{formatPercent(line.reach)}</b><small>of games</small></span>
              <Button size="sm" variant="outline" onClick={() => onOpen(line.prefixUci)}>Choose a move</Button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

const SETTING_FIELDS: { key: keyof RepertoireSettings; label: string; help: string; step: number; min: number; max: number; percent?: boolean }[] = [
  { key: "cpTolerance", label: "Max loss vs best move (cp)", help: "How much worse than the engine's best move a move of yours may be.", step: 10, min: 0, max: 300 },
  { key: "minEvalCp", label: "Lowest eval for you (cp)", help: "No move may leave you worse than this, so small losses don't add up.", step: 10, min: -500, max: 200 },
  { key: "maxOwnMoves", label: "Moves per line", help: "How many of your moves each line goes.", step: 1, min: 1, max: 30 },
  { key: "minReach", label: "Side lines from (% of games)", help: "Less common replies are drilled only while the line still comes up this often. The most common reply is always followed.", step: 0.5, min: 0.5, max: 50, percent: true },
];

function SettingsEditor({ api }: { api: RepertoireApi }) {
  const settings = api.repertoire?.settings;
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<RepertoireSettings | null>(settings ?? null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (settings) setDraft(settings); }, [settings]);
  if (!settings || !draft) return null;

  async function save() {
    if (!draft) return;
    setSaving(true);
    setError(null);
    try {
      await api.updateSettings(draft);
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the settings.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="relative">
      <Button size="sm" variant="ghost" onClick={() => setOpen((value) => !value)} aria-expanded={open}><Settings2 className="h-4 w-4" /> Rules</Button>
      {open ? (
        <div role="dialog" aria-label="Repertoire rules" className="absolute right-0 z-20 mt-2 flex w-[min(22rem,calc(100vw-2rem))] flex-col gap-3 rounded-xl p-4" style={{ border: "1px solid var(--line)", background: "var(--paper-raised)" }}>
          {SETTING_FIELDS.map((field) => {
            const raw = draft[field.key];
            const value = field.percent ? Math.round(raw * 1000) / 10 : raw;
            return (
              <label key={field.key} className="flex flex-col gap-1 text-xs" style={{ color: "var(--ink-soft)" }}>
                <span className="font-semibold" style={{ color: "var(--ink)" }}>{field.label}</span>
                <input
                  type="number"
                  className="rounded-md px-2 py-1 text-sm"
                  style={{ border: "1px solid var(--line)", background: "var(--paper)", color: "var(--ink)" }}
                  value={value}
                  step={field.step}
                  min={field.min}
                  max={field.max}
                  onChange={(event) => {
                    const number = Number(event.target.value);
                    if (Number.isNaN(number)) return;
                    setDraft({ ...draft, [field.key]: field.percent ? number / 100 : number });
                  }}
                />
                <span>{field.help}</span>
              </label>
            );
          })}
          {error ? <p className="text-xs" style={{ color: "var(--coral)" }}>{error}</p> : null}
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => { setDraft(settings); setOpen(false); }}>Cancel</Button>
            <Button size="sm" onClick={save} disabled={saving}>{saving ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save"}</Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
