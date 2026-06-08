import { Chessboard } from "react-chessboard";

export function OpeningBoardPreview({ fen }: { fen: string | null }) {
  if (!fen) {
    return <div className="flex aspect-square items-center justify-center rounded-md bg-slate-100 text-xs text-slate-500">No FEN</div>;
  }
  return (
    <div className="overflow-hidden rounded-md border border-slate-200">
      <Chessboard
        options={{
          position: fen,
          allowDragging: false,
          showNotation: false,
          animationDurationInMs: 0,
          boardStyle: { width: "100%", aspectRatio: "1 / 1" },
        }}
      />
    </div>
  );
}
