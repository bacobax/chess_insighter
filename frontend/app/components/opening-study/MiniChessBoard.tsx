import { useMemo } from "react";
import { defaultPieces } from "react-chessboard";

// A lightweight, non-interactive board preview rendered straight from a FEN.
// Deliberately does NOT mount full react-chessboard widgets: the study tree can
// render dozens of nodes at once. It reuses only the report board's SVG piece
// set inside a lightweight CSS grid.

export function ThemedChessPiece({ piece, size }: { piece: string; size: number }) {
  const color = piece === piece.toUpperCase() ? "w" : "b";
  const Piece = defaultPieces[`${color}${piece.toUpperCase()}`];
  if (!Piece) return null;
  return (
    <span aria-hidden="true" style={{ display: "block", width: size, height: size }}>
      <Piece />
    </span>
  );
}

function parsePlacement(fen: string): string[][] {
  const placement = fen.split(" ")[0] ?? "";
  const ranks = placement.split("/");
  const board: string[][] = [];
  for (const rank of ranks) {
    const row: string[] = [];
    for (const ch of rank) {
      if (/\d/.test(ch)) {
        for (let i = 0; i < Number(ch); i += 1) row.push("");
      } else {
        row.push(ch);
      }
    }
    while (row.length < 8) row.push("");
    board.push(row.slice(0, 8));
  }
  while (board.length < 8) board.push(Array(8).fill(""));
  return board.slice(0, 8);
}

export type SquareHighlight = "from" | "to" | "best";

const HIGHLIGHT_SHADOW: Record<SquareHighlight, string> = {
  from: "inset 0 0 0 3px #ff6a4d",
  to: "inset 0 0 0 999px rgba(255,106,77,.45)",
  best: "inset 0 0 0 3px #21e783",
};

export function MiniChessBoard({
  fen,
  size = 116,
  highlights,
  flipped = false,
  label,
}: {
  fen: string | null;
  size?: number;
  /** Optional square marks keyed by algebraic square, e.g. { e2: "from", e4: "to" }. */
  highlights?: Record<string, SquareHighlight>;
  /** Show the board from Black's side. */
  flipped?: boolean;
  label?: string;
}) {
  const board = useMemo(() => {
    if (!fen) return null;
    const placement = parsePlacement(fen);
    return flipped ? placement.map((row) => [...row].reverse()).reverse() : placement;
  }, [fen, flipped]);
  if (!board) {
    return (
      <div
        className="flex items-center justify-center rounded-md bg-slate-100 text-[10px] text-slate-400"
        style={{ width: size, height: size }}
      >
        No FEN
      </div>
    );
  }
  return (
    <div
      className="grid overflow-hidden rounded-md border border-slate-200"
      role={label ? "img" : undefined}
      aria-label={label}
      style={{ width: size, height: size, gridTemplateColumns: "repeat(8, 1fr)", gridTemplateRows: "repeat(8, 1fr)" }}
    >
      {board.flatMap((row, r) =>
        row.map((piece, c) => {
          const isLight = (r + c) % 2 === 0;
          const square = flipped ? `${"hgfedcba"[c]}${r + 1}` : `${"abcdefgh"[c]}${8 - r}`;
          const mark = highlights?.[square];
          return (
            <div
              key={`${r}-${c}`}
              className={isLight ? "bg-[#c6e8d2]" : "bg-[#225c42]"}
              style={{ display: "flex", alignItems: "center", justifyContent: "center", lineHeight: 1, boxShadow: mark ? HIGHLIGHT_SHADOW[mark] : undefined }}
            >
              {piece ? <ThemedChessPiece piece={piece} size={size / 8} /> : null}
            </div>
          );
        }),
      )}
    </div>
  );
}
