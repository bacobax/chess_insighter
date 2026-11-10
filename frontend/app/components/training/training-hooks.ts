import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { replayLine, sideToMove, type PlayedMove } from "./training-board";

/** State that survives reloads in this browser only (per-viewer conveniences). */
export function usePersistentState<T>(key: string, initial: T): [T, (value: T | ((current: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const stored = window.localStorage.getItem(key);
      return stored ? (JSON.parse(stored) as T) : initial;
    } catch {
      return initial;
    }
  });
  useEffect(() => {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // Storage can be unavailable (private mode); the state still works in memory.
    }
  }, [key, value]);
  return [value, setValue];
}

/** Keyboard shortcuts that ignore keys typed into form fields. */
export function useShortcuts(handlers: Record<string, () => void>, enabled = true) {
  const ref = useRef(handlers);
  ref.current = handlers;
  useEffect(() => {
    if (!enabled) return;
    const listener = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const key = event.key === " " ? "Space" : event.key;
      const handler = ref.current[key];
      if (handler) {
        event.preventDefault();
        handler();
      }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [enabled]);
}

export type LineTrainer = {
  fen: string;
  index: number;
  total: number;
  done: boolean;
  userTurn: boolean;
  mistakes: number;
  hints: number;
  wrongSquare: string | null;
  hintSquare: string | null;
  lastMove: { from: string; to: string } | null;
  playedSan: string[];
  onMove: (move: PlayedMove) => boolean;
  hint: () => void;
  reset: () => void;
  finish: () => void;
};

/**
 * Walks through a fixed line. The user plays the moves of `userSide`; the other
 * side's moves are played automatically after a short pause. A wrong move is
 * rejected and counted, a hint lights up the piece to move.
 */
export function useLineTrainer(startFen: string, moves: string[], userSide: "white" | "black" | "both"): LineTrainer {
  const line = useMemo(() => replayLine(startFen, moves), [startFen, moves]);
  const total = line.uci.length;
  const [index, setIndex] = useState(0);
  const [mistakes, setMistakes] = useState(0);
  const [hints, setHints] = useState(0);
  const [wrongSquare, setWrongSquare] = useState<string | null>(null);
  const [hintSquare, setHintSquare] = useState<string | null>(null);

  const fen = line.fens[Math.min(index, total)];
  const done = index >= total;
  const userTurn = !done && (userSide === "both" || sideToMove(fen) === userSide);

  const reset = useCallback(() => {
    setIndex(0);
    setMistakes(0);
    setHints(0);
    setWrongSquare(null);
    setHintSquare(null);
  }, []);
  useEffect(reset, [line, reset]);

  useEffect(() => {
    if (done || userTurn) return;
    const timer = window.setTimeout(() => setIndex((current) => current + 1), 450);
    return () => window.clearTimeout(timer);
  }, [done, userTurn, index]);

  useEffect(() => {
    if (!wrongSquare) return;
    const timer = window.setTimeout(() => setWrongSquare(null), 650);
    return () => window.clearTimeout(timer);
  }, [wrongSquare]);

  const onMove = useCallback((move: PlayedMove) => {
    if (!userTurn) return false;
    const expected = line.uci[index];
    if (move.uci === expected || move.uci.slice(0, 4) === expected.slice(0, 4)) {
      setIndex((current) => current + 1);
      setHintSquare(null);
      return true;
    }
    setMistakes((current) => current + 1);
    setWrongSquare(move.to);
    return false;
  }, [index, line, userTurn]);

  const hint = useCallback(() => {
    if (!userTurn) return;
    setHints((current) => current + 1);
    setHintSquare(line.uci[index].slice(0, 2));
  }, [index, line, userTurn]);

  const finish = useCallback(() => setIndex(total), [total]);
  const last = index > 0 ? line.uci[Math.min(index, total) - 1] : null;

  return {
    fen,
    index,
    total,
    done,
    userTurn,
    mistakes,
    hints,
    wrongSquare,
    hintSquare,
    lastMove: last ? { from: last.slice(0, 2), to: last.slice(2, 4) } : null,
    playedSan: line.san.slice(0, index),
    onMove,
    hint,
    reset,
    finish,
  };
}

/** Countdown that can be paused; `remaining` is in seconds. */
export function useCountdown(seconds: number) {
  const [remaining, setRemaining] = useState(seconds);
  const [running, setRunning] = useState(false);
  useEffect(() => { setRemaining(seconds); setRunning(false); }, [seconds]);
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setRemaining((current) => Math.max(0, current - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [running]);
  useEffect(() => { if (remaining === 0) setRunning(false); }, [remaining]);
  return {
    remaining,
    running,
    toggle: () => setRunning((current) => (remaining === 0 ? false : !current)),
    reset: () => { setRemaining(seconds); setRunning(false); },
    add: (extra: number) => setRemaining((current) => current + extra),
  };
}

export function formatClock(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}
