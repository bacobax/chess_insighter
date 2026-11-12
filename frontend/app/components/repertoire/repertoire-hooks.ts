import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiRequestError,
  getRepertoire,
  getRepertoireLines,
  getRepertoirePosition,
  removeRepertoireChoice,
  seedRepertoire,
  setRepertoireChoice,
  updateRepertoireSettings,
} from "~/lib/api";
import type { Repertoire, RepertoireColor, RepertoireLines, RepertoirePosition, RepertoireSettings } from "~/lib/types";

export const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
/** Polling stops after this many "pending" answers in a row; the user can retry. */
const MAX_POLLS = 20;

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

/** The saved repertoire for one colour, with the calls that change it. */
export function useRepertoire(color: RepertoireColor) {
  const [repertoire, setRepertoire] = useState<Repertoire | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Bumped after every change so dependent views (lines, coverage) reload.
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setRepertoire(null);
    setError(null);
    getRepertoire(color)
      .then((value) => { if (!cancelled) setRepertoire(value); })
      .catch((err) => { if (!cancelled) setError(errorMessage(err, "Could not load your repertoire.")); });
    return () => { cancelled = true; };
  }, [color]);

  const apply = useCallback((value: Repertoire) => {
    setRepertoire(value);
    setVersion((current) => current + 1);
    return value;
  }, []);

  return {
    repertoire,
    error,
    version,
    setChoice: (prefixUci: string[], moveUci: string) => setRepertoireChoice(color, prefixUci, moveUci).then(apply),
    removeChoice: (prefixUci: string[]) => removeRepertoireChoice(color, prefixUci).then(apply),
    updateSettings: (patch: Partial<RepertoireSettings>) => updateRepertoireSettings(color, patch).then(apply),
    seed: (lines?: string[]) => seedRepertoire(color, lines).then(apply),
  };
}

export type RepertoireApi = ReturnType<typeof useRepertoire>;

/**
 * One repertoire position, kept per move order. A "pending" answer (Lichess
 * rate limit, engine busy) is shown as is and asked again after `retryAfter`.
 */
export function useRepertoirePosition(color: RepertoireColor, prefixUci: string[], settingsKey: string, enabled = true) {
  // `settingsKey` changes when your tolerance or eval floor does: verdicts depend on them.
  const key = `${color}|${settingsKey}|${prefixUci.join(" ")}`;
  const cache = useRef(new Map<string, RepertoirePosition>());
  const [state, setState] = useState<{ key: string; data: RepertoirePosition | null; error: string | null; loading: boolean }>({
    key: "",
    data: null,
    error: null,
    loading: false,
  });
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (!enabled) return;
    const cached = cache.current.get(key);
    if (cached && cached.status === "ready") {
      setState({ key, data: cached, error: null, loading: false });
      return;
    }
    let cancelled = false;
    let timer: number | undefined;
    let polls = 0;
    setState((current) => ({ key, data: current.key === key ? current.data : cached ?? null, error: null, loading: true }));

    const load = () => {
      getRepertoirePosition(color, prefixUci)
        .then((data) => {
          if (cancelled) return;
          cache.current.set(key, data);
          const again = data.status === "pending" && polls < MAX_POLLS;
          setState({ key, data, error: null, loading: again });
          if (again) {
            polls += 1;
            timer = window.setTimeout(load, Math.max(1, data.retryAfter ?? 3) * 1000);
          }
        })
        .catch((err) => {
          if (!cancelled) setState({ key, data: null, error: errorMessage(err, "Could not load this position."), loading: false });
        });
    };
    load();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
    // `prefixUci` is captured through `key`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled, retry]);

  const current = state.key === key ? state : { ...state, data: null, loading: enabled };
  return { ...current, retry: () => { cache.current.delete(key); setRetry((value) => value + 1); } };
}

/** Every line of the repertoire from a start position, re-asked while data is still arriving. */
export function useRepertoireLines(color: RepertoireColor, startPrefixUci: string[], version: number, enabled = true) {
  const startKey = startPrefixUci.join(" ");
  const [lines, setLines] = useState<RepertoireLines | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let timer: number | undefined;
    let polls = 0;
    setLoading(true);
    setError(null);
    const load = () => {
      getRepertoireLines(color, startPrefixUci)
        .then((data) => {
          if (cancelled) return;
          setLines(data);
          const again = data.status === "pending" && polls < MAX_POLLS;
          setLoading(again);
          if (again) {
            polls += 1;
            timer = window.setTimeout(load, Math.max(1, data.retryAfter ?? 1) * 1000);
          }
        })
        .catch((err) => {
          if (cancelled) return;
          setError(err instanceof ApiRequestError ? err.message : errorMessage(err, "Could not load your lines."));
          setLoading(false);
        });
    };
    load();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
    // `startPrefixUci` is captured through `startKey`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [color, startKey, version, enabled, retry]);

  return { lines, error, loading, retry: () => setRetry((value) => value + 1) };
}

export function formatPercent(value: number): string {
  if (value > 0 && value < 0.01) return "<1%";
  return `${Math.round(value * 100)}%`;
}

export function formatCp(cp: number | null, mate: number | null = null): string {
  if (mate !== null && mate !== undefined) return mate > 0 ? `#${mate}` : `#-${Math.abs(mate)}`;
  if (cp === null || cp === undefined) return "–";
  const pawns = cp / 100;
  return `${pawns > 0 ? "+" : ""}${pawns.toFixed(2)}`;
}

/** "1.e4 e5 2.Nf3", numbering from the first ply. */
export function numberedSan(sans: string[], from = 0): string {
  return sans
    .slice(from)
    .map((san, offset) => {
      const index = from + offset;
      const number = Math.floor(index / 2) + 1;
      if (index % 2 === 0) return `${number}.${san}`;
      return offset === 0 ? `${number}…${san}` : san;
    })
    .join(" ");
}
