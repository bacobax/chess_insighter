import { useState } from "react";
import { Loader2, X } from "lucide-react";
import type { OpeningStudyTreeNode } from "~/lib/types";
import { ZoomableBoard } from "~/components/board/BoardZoomModal";
import { MiniChessBoard, PIECE_GLYPHS } from "./MiniChessBoard";
import { StatBarChart } from "./StatBarChart";

// Compact (layout) dimensions — these drive tree spacing.
// The visual container expands beyond these bounds when isVisuallyExpanded.
export const NODE_WIDTH = 76;
export const NODE_HEIGHT = 76;

export const EXPANDED_NODE_WIDTH = 248;
export const EXPANDED_NODE_HEIGHT = 270;
// Blurred board rendered at this fixed size, centered over the container.
const BG_BOARD_SIZE = 340;

// ─── Helpers ────────────────────────────────────────────────────────────────

function getPieceGlyph(moveSan: string, sideToMove: "white" | "black"): string {
  const movedColor = sideToMove === "white" ? "black" : "white";
  let type: string;
  if (moveSan.startsWith("O")) {
    type = "K";
  } else if (/^[KQRBN]/.test(moveSan)) {
    type = moveSan[0];
  } else {
    type = "P";
  }
  const key = movedColor === "white" ? type : type.toLowerCase();
  return PIECE_GLYPHS[key] ?? "?";
}

function getDestLabel(moveSan: string, moveUci: string): string {
  if (moveSan.startsWith("O-O-O")) return "O-O-O";
  if (moveSan.startsWith("O-O")) return "O-O";
  return moveUci.slice(2, 4);
}

function moveLabel(node: OpeningStudyTreeNode): string {
  const movedColor = node.sideToMove === "white" ? "black" : "white";
  return movedColor === "black" ? `…${node.moveSan}` : node.moveSan;
}

// ─── Component ───────────────────────────────────────────────────────────────

type Props = {
  node: OpeningStudyTreeNode;
  selected: boolean;
  onPath: boolean;
  expanded: boolean;
  loading: boolean;
  onSelect: () => void;
  onCollapse: () => void;
  onHoverChange: (hovered: boolean) => void;
};

export function OpeningStudyNode({
  node,
  selected,
  onPath,
  expanded,
  loading,
  onSelect,
  onCollapse,
  onHoverChange,
}: Props) {
  const [hovered, setHovered] = useState(false);

  // Card stays large when the branch is open, even after mouse-leave.
  const isVisuallyExpanded = hovered || expanded;

  const onMouseEnter = () => {
    setHovered(true);
    onHoverChange(true);
  };
  const onMouseLeave = () => {
    setHovered(false);
    onHoverChange(false);
  };

  const pieceGlyph = getPieceGlyph(node.moveSan, node.sideToMove);
  const destLabel = getDestLabel(node.moveSan, node.moveUci);

  // Offset that keeps the expanded card centered over the compact square.
  const expandOffsetX = -(EXPANDED_NODE_WIDTH - NODE_WIDTH) / 2; // −86
  const expandOffsetY = -(EXPANDED_NODE_HEIGHT - NODE_HEIGHT) / 2; // −97

  const ring = selected
    ? `0 0 0 2px var(--ink), ${isVisuallyExpanded ? "0 24px 48px rgba(0,0,0,0.45)" : "0 2px 6px rgba(0,0,0,0.18)"}`
    : onPath
      ? `0 0 0 2px var(--accent), ${isVisuallyExpanded ? "0 24px 48px rgba(0,0,0,0.45)" : "0 2px 6px rgba(0,0,0,0.18)"}`
      : isVisuallyExpanded
        ? "0 24px 48px rgba(0,0,0,0.45)"
        : "0 2px 6px rgba(0,0,0,0.12)";

  return (
    // Layout anchor — fixed 76×76, provides position origin. No overflow:hidden
    // so the expanding child can bleed outward.
    <div style={{ width: NODE_WIDTH, height: NODE_HEIGHT, position: "relative" }}>

      {/* ── Visual expanding container ──────────────────────────────────── */}
      <div
        className="absolute cursor-pointer overflow-hidden select-none"
        style={{
          width: isVisuallyExpanded ? EXPANDED_NODE_WIDTH : NODE_WIDTH,
          height: isVisuallyExpanded ? EXPANDED_NODE_HEIGHT : NODE_HEIGHT,
          transform: isVisuallyExpanded
            ? `translate(${expandOffsetX}px, ${expandOffsetY}px)`
            : "translate(0, 0)",
          borderRadius: 14,
          // Solid base colour prevents other nodes showing through.
          backgroundColor: "#1c140e",
          border: "1px solid rgba(255,255,255,0.12)",
          boxShadow: ring,
          transition: [
            "width 0.32s cubic-bezier(0.34,1.56,0.64,1)",
            "height 0.32s cubic-bezier(0.34,1.56,0.64,1)",
            "transform 0.32s cubic-bezier(0.34,1.56,0.64,1)",
            "box-shadow 0.2s ease",
          ].join(", "),
          zIndex: isVisuallyExpanded ? 50 : 1,
        }}
        onClick={onSelect}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
      >
        {/* ── Blurred board bg — centered, covers full container ─────────── */}
        <div
          className="pointer-events-none absolute inset-0 overflow-hidden"
          style={{ filter: "blur(3px)", opacity: 0.44 }}
        >
          <div
            style={{
              position: "absolute",
              top: "50%",
              left: "50%",
              width: BG_BOARD_SIZE,
              height: BG_BOARD_SIZE,
              transform: "translate(-50%, -50%) scale(1.1)",
            }}
          >
            <MiniChessBoard fen={node.boardPreviewFen} size={BG_BOARD_SIZE} />
          </div>
        </div>

        {/* ── Dark overlay ───────────────────────────────────────────────── */}
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "linear-gradient(160deg, rgba(16,12,8,0.82) 0%, rgba(22,16,10,0.70) 100%)",
          }}
        />

        {/* ── Collapse × — top-right, shown whenever the branch is expanded */}
        {expanded && !loading && (
          <button
            type="button"
            className="absolute"
            style={{
              top: 6,
              right: 6,
              width: 18,
              height: 18,
              borderRadius: "50%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              backgroundColor: "rgba(255,255,255,0.14)",
              color: "rgba(255,255,255,0.80)",
              border: "1px solid rgba(255,255,255,0.18)",
              cursor: "pointer",
              zIndex: 30,
            }}
            onClick={(e) => {
              e.stopPropagation();
              onCollapse();
            }}
            title="Collapse branch"
          >
            <X className="h-2.5 w-2.5" />
          </button>
        )}

        {/* ── Compact content (fades out when visually expanded) ─────────── */}
        <div
          className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center"
          style={{
            opacity: isVisuallyExpanded ? 0 : 1,
            transition: "opacity 0.12s ease",
          }}
        >
          <span
            style={{
              fontSize: 30,
              lineHeight: 1,
              color: "#fafafa",
              textShadow: "0 1px 6px rgba(0,0,0,0.8)",
            }}
          >
            {pieceGlyph}
          </span>
          <span
            style={{
              fontSize: 9,
              lineHeight: 1.3,
              color: "rgba(255,255,255,0.78)",
              fontFamily: "monospace",
              letterSpacing: "0.06em",
              marginTop: 2,
            }}
          >
            {destLabel}
          </span>
        </div>

        {/* Your-move indicator dot — compact mode only */}
        <div
          className="pointer-events-none absolute"
          style={{
            left: 7,
            top: 7,
            width: 7,
            height: 7,
            borderRadius: "50%",
            backgroundColor: node.isTargetMove ? "#fafafa" : "rgba(255,255,255,0.35)",
            boxShadow: "0 1px 3px rgba(0,0,0,0.4)",
            opacity: isVisuallyExpanded ? 0 : 1,
            transition: "opacity 0.12s ease",
          }}
          title={node.isTargetMove ? "Your move" : "Opponent move"}
        />

        {/* Score badge — compact mode only, bottom-right */}
        {!loading && (
          <div
            className="pointer-events-none absolute"
            style={{
              bottom: 5,
              right: 5,
              padding: "1px 4px",
              borderRadius: 3,
              backgroundColor: "rgba(243,249,241,0.88)",
              color: "#2d5016",
              fontSize: 8,
              fontWeight: 700,
              lineHeight: 1.2,
              opacity: isVisuallyExpanded ? 0 : 1,
              transition: "opacity 0.12s ease",
            }}
          >
            {(node.studyScore * 100).toFixed(0)}
          </div>
        )}

        {/* Loading spinner */}
        {loading && (
          <div
            className="pointer-events-none absolute"
            style={{
              bottom: 5,
              right: 5,
              opacity: isVisuallyExpanded ? 0 : 1,
              transition: "opacity 0.12s ease",
            }}
          >
            <Loader2
              className="h-3.5 w-3.5 animate-spin"
              style={{ color: "rgba(255,255,255,0.8)" }}
            />
          </div>
        )}

        {/* ── Expanded content (fades in after expansion begins) ─────────── */}
        {isVisuallyExpanded && (
          <div
            className="node-expanded-content pointer-events-auto absolute inset-0 flex flex-col"
            style={{ zIndex: 10 }}
          >
            {/* Header: move label + your-move badge + score */}
            <div
              className="flex flex-shrink-0 items-center gap-1.5 px-3 py-2.5"
              style={{ paddingRight: expanded ? 30 : 12 }}
            >
              <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden">
                <span
                  className="shrink-0 text-sm font-bold leading-tight"
                  style={{
                    color: "#fafafa",
                    fontFamily: "var(--font-display)",
                    textShadow: "0 1px 4px rgba(0,0,0,0.5)",
                  }}
                >
                  {moveLabel(node)}
                </span>
                <span
                  className="shrink-0 rounded px-1.5 py-0.5 text-[9px] font-medium"
                  style={{
                    backgroundColor: node.isTargetMove
                      ? "rgba(255,255,255,0.18)"
                      : "rgba(100,90,80,0.4)",
                    color: "rgba(255,255,255,0.75)",
                    border: "1px solid rgba(255,255,255,0.18)",
                  }}
                >
                  {node.isTargetMove ? "your move" : "opponent"}
                </span>
              </div>
              <span
                className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold tabular-nums"
                style={{
                  backgroundColor: "rgba(243,249,241,0.90)",
                  color: "#2d5016",
                  lineHeight: 1.2,
                }}
              >
                {(node.studyScore * 100).toFixed(0)}
              </span>
            </div>

            {/* Board preview + opening names */}
            <div className="flex flex-shrink-0 gap-2.5 px-3 pb-2">
              {/* stopPropagation so clicking the board opens the zoom modal
                  without also triggering onSelect on the parent */}
              <div onClick={(e) => e.stopPropagation()}>
                <ZoomableBoard
                  fen={node.boardPreviewFen}
                  label={node.openingNames[0] ?? node.moveSan}
                >
                  <MiniChessBoard fen={node.boardPreviewFen} size={88} />
                </ZoomableBoard>
              </div>
              <div className="flex min-w-0 flex-1 flex-col gap-1 py-0.5">
                <div
                  className="line-clamp-4 text-[9.5px] leading-snug"
                  style={{ color: "rgba(255,255,255,0.68)" }}
                >
                  {node.openingNames.length > 0
                    ? node.openingNames.join(" · ")
                    : "—"}
                </div>
                <div
                  className="mt-auto text-[8.5px]"
                  style={{ color: "rgba(255,255,255,0.4)" }}
                >
                  {node.compatibleLineCount} lines
                </div>
              </div>
            </div>

            {/* Stat bars — on a warm paper-toned inset so existing styles read correctly */}
            <div
              className="mx-3 flex-shrink-0"
              style={{
                backgroundColor: "rgba(244,236,216,0.92)",
                borderRadius: 8,
                padding: "8px 10px",
              }}
            >
              <StatBarChart stats={node.stats} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
