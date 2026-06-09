import { useMemo } from "react";

// A lightweight, non-interactive board preview rendered straight from a FEN.
// Deliberately does NOT use react-chessboard: the study tree can render dozens
// of nodes at once and many full board widgets would be heavy. This is pure
// CSS/Unicode and cheap to mount.

const PIECE_GLYPHS: Record<string, string> = {
  K: "♔",
  Q: "♕",
  R: "♖",
  B: "♗",
  N: "♘",
  P: "♙",
  k: "♚",
  q: "♛",
  r: "♜",
  b: "♝",
  n: "♞",
  p: "♟",
};

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

export function MiniChessBoard({ fen, size = 116 }: { fen: string | null; size?: number }) {
  const board = useMemo(() => (fen ? parsePlacement(fen) : null), [fen]);
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
      style={{ width: size, height: size, gridTemplateColumns: "repeat(8, 1fr)", gridTemplateRows: "repeat(8, 1fr)" }}
    >
      {board.flatMap((row, r) =>
        row.map((piece, c) => {
          const isLight = (r + c) % 2 === 0;
          const isWhitePiece = piece !== "" && piece === piece.toUpperCase();
          return (
            <div
              key={`${r}-${c}`}
              className={isLight ? "bg-[#eadbc0]" : "bg-[#b58863]"}
              style={{ display: "flex", alignItems: "center", justifyContent: "center", lineHeight: 1 }}
            >
              <span
                style={{
                  fontSize: size / 9,
                  color: isWhitePiece ? "#fafafa" : "#1a1a1a",
                  textShadow: isWhitePiece ? "0 0 1px #000" : "none",
                }}
              >
                {piece ? PIECE_GLYPHS[piece] ?? "" : ""}
              </span>
            </div>
          );
        }),
      )}
    </div>
  );
}
