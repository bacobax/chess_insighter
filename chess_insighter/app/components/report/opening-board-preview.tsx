import { Chessboard } from "react-chessboard";
import { ZoomableBoard } from "~/components/board/BoardZoomModal";

export function OpeningBoardPreview({ fen, label }: { fen: string | null; label?: string }) {
  if (!fen) {
    return (
      <div
        className="flex aspect-square items-center justify-center rounded-md text-xs"
        style={{ backgroundColor: "var(--line-faint)", color: "var(--ink-soft)" }}
      >
        No FEN
      </div>
    );
  }
  return (
    <ZoomableBoard fen={fen} label={label}>
      <div className="overflow-hidden rounded-md" style={{ border: "1px solid var(--line)" }}>
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
    </ZoomableBoard>
  );
}
