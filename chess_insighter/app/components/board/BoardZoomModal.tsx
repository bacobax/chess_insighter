import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { Chessboard } from "react-chessboard";

type ZoomableBoardProps = {
  fen: string | null;
  label?: string;
  children: ReactNode;
};

export function ZoomableBoard({ fen, label, children }: ZoomableBoardProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => fen && setOpen(true)}
        className={fen ? "cursor-zoom-in block transition-transform duration-150 hover:scale-[1.04] focus:outline-none" : "block"}
        style={{ background: "none", border: "none", padding: 0 }}
        aria-label={label ? `Zoom: ${label}` : "Zoom board"}
        tabIndex={fen ? 0 : -1}
      >
        {children}
      </button>
      {open && fen && <BoardModal fen={fen} label={label} onClose={() => setOpen(false)} />}
    </>
  );
}

function BoardModal({ fen, label, onClose }: { fen: string; label?: string; onClose: () => void }) {
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", handler);
    };
  }, [onClose]);

  return createPortal(
    <div
      className="board-zoom-backdrop fixed inset-0 flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(46,42,35,0.72)", backdropFilter: "blur(3px)", zIndex: 9999 }}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={label ?? "Board preview"}
    >
      <div
        className="board-zoom-panel relative flex flex-col items-center gap-3 rounded-md p-5 shadow-2xl"
        style={{
          backgroundColor: "var(--paper)",
          border: "1px solid var(--line)",
          maxWidth: "min(480px, 92vw)",
          width: "100%",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute right-2.5 top-2.5 flex h-7 w-7 items-center justify-center rounded-full transition-colors hover:bg-black/10"
          style={{ color: "var(--ink-soft)" }}
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>
        {label && (
          <p
            className="pr-8 text-center text-sm font-semibold leading-snug"
            style={{ color: "var(--ink)", fontFamily: "var(--font-display)" }}
          >
            {label}
          </p>
        )}
        <div className="w-full overflow-hidden rounded-md" style={{ border: "1px solid var(--line)" }}>
          <Chessboard
            options={{
              position: fen,
              allowDragging: false,
              showNotation: true,
              animationDurationInMs: 0,
              boardStyle: { width: "100%", aspectRatio: "1 / 1" },
            }}
          />
        </div>
        <p className="text-xs" style={{ color: "var(--ink-faint)" }}>
          Esc or click outside to close
        </p>
      </div>
    </div>,
    document.body,
  );
}
