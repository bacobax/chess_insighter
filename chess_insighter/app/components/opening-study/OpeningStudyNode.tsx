import { Loader2 } from "lucide-react";
import { cn } from "~/lib/utils";
import type { OpeningStudyTreeNode } from "~/lib/types";
import { MiniChessBoard } from "./MiniChessBoard";
import { StatBarChart } from "./StatBarChart";

export const NODE_WIDTH = 248;
export const NODE_HEIGHT = 286;

type Props = {
  node: OpeningStudyTreeNode;
  // Node is the currently selected (active) node.
  selected: boolean;
  // Node sits on the path between root and the selected node.
  onPath: boolean;
  expanded: boolean;
  loading: boolean;
  onSelect: () => void;
};

function moveLabel(node: OpeningStudyTreeNode): string {
  // The move that produced this node was made by the side that is NOT to move.
  const movedColor = node.sideToMove === "white" ? "black" : "white";
  return movedColor === "black" ? `…${node.moveSan}` : node.moveSan;
}

export function OpeningStudyNode({ node, selected, onPath, expanded, loading, onSelect }: Props) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex flex-col gap-2 rounded-xl border bg-white p-3 text-left shadow-sm transition-all",
        "hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400",
        selected ? "border-slate-900 ring-2 ring-slate-900" : onPath ? "border-blue-400" : "border-slate-200",
      )}
      style={{ width: NODE_WIDTH, height: NODE_HEIGHT }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-lg font-semibold text-slate-900">{moveLabel(node)}</span>
          <span
            className={cn(
              "rounded px-1.5 py-0.5 text-[10px] font-medium",
              node.isTargetMove ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-500",
            )}
          >
            {node.isTargetMove ? "your move" : "opponent"}
          </span>
        </div>
        <span
          className="rounded-md bg-emerald-50 px-2 py-1 text-xs font-bold tabular-nums text-emerald-700"
          title="Overall study score"
        >
          {(node.studyScore * 100).toFixed(0)}
        </span>
      </div>

      <div className="flex gap-2">
        <MiniChessBoard fen={node.boardPreviewFen} size={116} />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="line-clamp-3 text-[11px] leading-tight text-slate-600">
            {node.openingNames.length > 0 ? node.openingNames.join(" · ") : "—"}
          </div>
          <div className="mt-auto text-[10px] text-slate-400">{node.compatibleLineCount} lines</div>
        </div>
      </div>

      <StatBarChart stats={node.stats} />

      <div className="mt-auto flex items-center justify-between text-[10px] text-slate-400">
        <span>{expanded ? "Expanded" : "Click to expand"}</span>
        {loading ? <Loader2 className="h-3 w-3 animate-spin text-slate-500" /> : null}
      </div>
    </button>
  );
}
