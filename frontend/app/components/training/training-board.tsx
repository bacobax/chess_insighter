import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { Chessboard } from "react-chessboard";
import { Chess, type Square } from "chess.js";

export type BoardArrow = { startSquare: string; endSquare: string; color: string };

export type PlayedMove = { from: string; to: string; san: string; uci: string; fenAfter: string };

export const ARROW_BEST = "rgba(33,231,131,.85)";
export const ARROW_PLAYED = "rgba(255,106,77,.85)";
export const ARROW_HINT = "rgba(220,255,66,.85)";

const SELECTED: CSSProperties = { boxShadow: "inset 0 0 0 3px #dcff42" };
const TARGET: CSSProperties = { background: "radial-gradient(circle, rgba(10,14,11,.45) 22%, transparent 24%)" };
const CAPTURE: CSSProperties = { background: "radial-gradient(circle, transparent 58%, rgba(10,14,11,.45) 60%)" };
const WRONG: CSSProperties = { boxShadow: "inset 0 0 0 999px rgba(255,106,77,.45)" };

/**
 * Interactive board for the training tools: drag a piece or click it and then
 * a target square. Only legal moves for the side to move are offered, and the
 * parent decides whether a move is accepted (return false to snap it back).
 */
export function TrainingBoard({
  fen,
  orientation,
  movable = false,
  onMove,
  arrows = [],
  squareStyles,
  wrongSquare,
  label,
  className = "tp-board",
  animate = true,
}: {
  fen: string;
  orientation: "white" | "black";
  movable?: boolean;
  onMove?: (move: PlayedMove) => boolean;
  arrows?: BoardArrow[];
  squareStyles?: Record<string, CSSProperties>;
  /** Flash this square red, e.g. after a wrong attempt. */
  wrongSquare?: string | null;
  label: string;
  /** Wrapper class; defaults to the training layout's 440px board. */
  className?: string;
  /** Animate piece moves. react-chessboard measures the board to animate and
   *  throws when it has no width (e.g. inside a `display: none` panel). */
  animate?: boolean;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => setSelected(null), [fen]);
  const wrapperRef = useRef<HTMLDivElement>(null);
  // Re-checked on every render: only animate when the board is actually laid out.
  const canAnimate = animate && (wrapperRef.current?.getBoundingClientRect().width ?? 0) > 0;

  const targets = useMemo(() => {
    if (!movable || !selected) return [];
    try {
      return new Chess(fen).moves({ square: selected as Square, verbose: true });
    } catch {
      return [];
    }
  }, [fen, movable, selected]);

  function attempt(from: string, to: string): boolean {
    let chess: Chess;
    try {
      chess = new Chess(fen);
      const move = chess.move({ from, to, promotion: "q" });
      setSelected(null);
      return onMove?.({ from, to, san: move.san, uci: `${move.from}${move.to}${move.promotion ?? ""}`, fenAfter: chess.fen() }) ?? false;
    } catch {
      return false;
    }
  }

  function ownPiece(square: string): boolean {
    try {
      const chess = new Chess(fen);
      const piece = chess.get(square as Square);
      return Boolean(piece && piece.color === chess.turn());
    } catch {
      return false;
    }
  }

  const styles: Record<string, CSSProperties> = { ...(squareStyles ?? {}) };
  if (selected) styles[selected] = { ...styles[selected], ...SELECTED };
  for (const target of targets) styles[target.to] = { ...styles[target.to], ...(target.captured ? CAPTURE : TARGET) };
  if (wrongSquare) styles[wrongSquare] = { ...styles[wrongSquare], ...WRONG };

  return (
    <div ref={wrapperRef} className={className} role="group" aria-label={label}>
      <Chessboard
        options={{
          position: fen,
          boardOrientation: orientation,
          allowDragging: movable,
          canDragPiece: ({ square }) => movable && square !== null && ownPiece(square),
          onPieceDrop: ({ sourceSquare, targetSquare }) => (targetSquare ? attempt(sourceSquare, targetSquare) : false),
          onSquareClick: ({ square }) => {
            if (!movable) return;
            if (selected && targets.some((target) => target.to === square)) {
              attempt(selected, square);
            } else {
              setSelected(ownPiece(square) && square !== selected ? square : null);
            }
          },
          arrows,
          clearArrowsOnPositionChange: false,
          allowDrawingArrows: true,
          squareStyles: styles,
          darkSquareStyle: { backgroundColor: "#225c42" },
          lightSquareStyle: { backgroundColor: "#c6e8d2" },
          showNotation: true,
          showAnimations: canAnimate,
          animationDurationInMs: 200,
          boardStyle: { width: "100%", aspectRatio: "1 / 1", borderRadius: 10, overflow: "hidden" },
        }}
      />
    </div>
  );
}

/** Plays a SAN or UCI move list from a FEN; stops at the first illegal move. */
export function replayLine(startFen: string, moves: string[]): { fens: string[]; uci: string[]; san: string[] } {
  const chess = new Chess(startFen);
  const fens = [chess.fen()];
  const uci: string[] = [];
  const san: string[] = [];
  for (const raw of moves) {
    try {
      const move = /^[a-h][1-8][a-h][1-8][qrbn]?$/.test(raw)
        ? chess.move({ from: raw.slice(0, 2), to: raw.slice(2, 4), promotion: raw[4] ?? "q" })
        : chess.move(raw);
      fens.push(chess.fen());
      uci.push(`${move.from}${move.to}${move.promotion ?? ""}`);
      san.push(move.san);
    } catch {
      break;
    }
  }
  return { fens, uci, san };
}

/** "1.e4 e5 2.Nf3 Nc6" → ["e4", "e5", "Nf3", "Nc6"]. */
export function parseSanLine(line: string): string[] {
  return line
    .split(/\s+/)
    .map((token) => token.replace(/^\d+\.(\.\.)?/, "").replace(/^…/, ""))
    .filter((token) => token && !/^\d+\.*$/.test(token));
}

export function sideToMove(fen: string): "white" | "black" {
  return fen.split(" ")[1] === "b" ? "black" : "white";
}
