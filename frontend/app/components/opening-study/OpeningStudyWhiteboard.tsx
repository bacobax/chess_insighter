import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { fetchOpeningStudyChildren } from "~/lib/api";
import type { OpeningStudyTreeNode } from "~/lib/types";
import type { StudyControlsState } from "./OpeningStudyControls";
import {
  EXPANDED_NODE_HEIGHT,
  EXPANDED_NODE_WIDTH,
  NODE_HEIGHT,
  NODE_WIDTH,
  OpeningStudyNode,
} from "./OpeningStudyNode";

type Entry = {
  node: OpeningStudyTreeNode;
  children: Entry[] | null; // null = not yet loaded
  loading: boolean;
};

type Positioned = {
  entry: Entry;
  x: number;
  y: number;
  depth: number;
};

type Edge = { id: string; x1: number; y1: number; x2: number; y2: number };

const COMPACT_COL = NODE_WIDTH + 100;
const COMPACT_ROW = NODE_HEIGHT + 28;
const EXPANDED_GAP_X = 36;
const EXPANDED_GAP_Y = 28;
const EXPANDED_COL = EXPANDED_NODE_WIDTH + EXPANDED_GAP_X;
const EXPANDED_ROW = EXPANDED_NODE_HEIGHT + EXPANDED_GAP_Y;

function nodeId(node: OpeningStudyTreeNode): string {
  return node.prefixUci.join("/");
}

function hasExpandedEntry(entries: Entry[]): boolean {
  return entries.some((entry) => {
    if (entry.children !== null && entry.children.length > 0) return true;
    return entry.children ? hasExpandedEntry(entry.children) : false;
  });
}

// Recursively reconcile an immutable Entry tree: replaces the entry whose node
// id matches `targetId`, leaving the rest of the tree referentially intact.
function updateEntry(entries: Entry[], targetId: string, fn: (entry: Entry) => Entry): Entry[] {
  return entries.map((entry) => {
    if (nodeId(entry.node) === targetId) return fn(entry);
    if (entry.children) {
      const nextChildren = updateEntry(entry.children, targetId, fn);
      if (nextChildren !== entry.children) return { ...entry, children: nextChildren };
    }
    return entry;
  });
}

function layout(roots: Entry[]): { positioned: Positioned[]; edges: Edge[]; width: number; height: number } {
  const positioned: Positioned[] = [];
  const edges: Edge[] = [];
  const reservesExpandedCards = hasExpandedEntry(roots);
  const col = reservesExpandedCards ? EXPANDED_COL : COMPACT_COL;
  const row = reservesExpandedCards ? EXPANDED_ROW : COMPACT_ROW;
  let leafCursor = 0;

  function place(entry: Entry, depth: number): number {
    const x = depth * col;
    let y: number;
    const visibleChildren = entry.children && entry.children.length > 0 ? entry.children : null;
    if (visibleChildren) {
      const childYs = visibleChildren.map((child) => place(child, depth + 1));
      y = (childYs[0] + childYs[childYs.length - 1]) / 2;
      for (let i = 0; i < visibleChildren.length; i += 1) {
        const childId = nodeId(visibleChildren[i].node);
        edges.push({
          id: `${nodeId(entry.node)}->${childId}`,
          x1: x + NODE_WIDTH,
          y1: y + NODE_HEIGHT / 2,
          x2: (depth + 1) * col,
          y2: childYs[i] + NODE_HEIGHT / 2,
        });
      }
    } else {
      y = leafCursor * row;
      leafCursor += 1;
    }
    positioned.push({ entry, x, y, depth });
    return y;
  }

  for (const root of roots) place(root, 0);

  const maxX = positioned.reduce((acc, p) => Math.max(acc, p.x + NODE_WIDTH), 0);
  const maxY = positioned.reduce((acc, p) => Math.max(acc, p.y + NODE_HEIGHT), 0);
  return { positioned, edges, width: maxX + 80, height: maxY + 80 };
}

type Props = {
  controls: StudyControlsState;
  generationKey: number;
  onNodeSelect?: (node: OpeningStudyTreeNode | null) => void;
  onPlayerVectorLoad?: (vector: Record<string, number>) => void;
};

export function OpeningStudyWhiteboard({ controls, generationKey, onNodeSelect, onPlayerVectorLoad }: Props) {
  const [roots, setRoots] = useState<Entry[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [rootLoading, setRootLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const playerVectorLoadedRef = useRef(false);

  const [view, setView] = useState({ tx: 40, ty: 40, scale: 1 });
  const dragRef = useRef<{ x: number; y: number; tx: number; ty: number } | null>(null);

  const requestBase = useCallback(
    () => ({
      cacheHash: controls.cacheHash.trim() || undefined,
      username: controls.username.trim() || undefined,
      targetColor: controls.targetColor,
      topK: controls.topK,
      opponentTopK: controls.opponentTopK,
      weights: controls.weights,
      similarityType: controls.similarityType,
      weightedMatching: controls.weightedMatching,
      matcherWeights: controls.weightedMatching ? controls.matcherWeights : undefined,
    }),
    [controls],
  );

  // (Re)generate the root level whenever the user hits "Generate".
  // generationKey === 0 is the initial / reset state: clear everything.
  useEffect(() => {
    setRoots([]);
    setSelectedId(null);
    setHoveredId(null);
    setError(null);
    setView({ tx: 40, ty: 40, scale: 1 });
    onNodeSelect?.(null);
    if (generationKey === 0) {
      playerVectorLoadedRef.current = false;
      setRootLoading(false);
      return;
    }
    playerVectorLoadedRef.current = false;
    let cancelled = false;
    setRootLoading(true);
    fetchOpeningStudyChildren({ ...requestBase(), prefixUci: [] })
      .then((response) => {
        if (cancelled) return;
        setRoots(response.children.map((node) => ({ node, children: null, loading: false })));
        if (!playerVectorLoadedRef.current && response.playerVector && onPlayerVectorLoad) {
          playerVectorLoadedRef.current = true;
          onPlayerVectorLoad(response.playerVector);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load suggestions.");
      })
      .finally(() => {
        if (!cancelled) setRootLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generationKey]);

  const expand = useCallback(
    async (entry: Entry) => {
      const id = nodeId(entry.node);
      setRoots((prev) => updateEntry(prev, id, (e) => ({ ...e, loading: true })));
      try {
        const response = await fetchOpeningStudyChildren({ ...requestBase(), prefixUci: entry.node.prefixUci });
        setRoots((prev) =>
          updateEntry(prev, id, (e) => ({
            ...e,
            loading: false,
            children: response.children.map((node) => ({ node, children: null, loading: false })),
          })),
        );
      } catch (err) {
        setRoots((prev) => updateEntry(prev, id, (e) => ({ ...e, loading: false })));
        setError(err instanceof Error ? err.message : "Failed to expand branch.");
      }
    },
    [requestBase],
  );

  // Select a node (updates inspector panel) and expand it if not yet expanded.
  // Re-clicking an already-expanded node no longer collapses it; use the × badge.
  const onSelect = useCallback(
    (entry: Entry) => {
      const id = nodeId(entry.node);
      setSelectedId(id);
      onNodeSelect?.(entry.node);
      if (entry.loading) return;
      if (entry.children === null) {
        void expand(entry);
      }
      // Intentionally no collapse on re-click: use the dedicated × badge.
    },
    [expand, onNodeSelect],
  );

  // Explicitly collapse a branch from its root node.
  const onCollapse = useCallback((entry: Entry) => {
    const id = nodeId(entry.node);
    setRoots((prev) => updateEntry(prev, id, (e) => ({ ...e, children: null })));
  }, []);

  const onHoverChange = useCallback((id: string, hovered: boolean) => {
    setHoveredId(hovered ? id : (prev) => (prev === id ? null : prev));
  }, []);

  const { positioned, edges, width, height } = useMemo(() => layout(roots), [roots]);

  // --- pan / zoom handlers -------------------------------------------------
  const onPointerDown = (event: React.PointerEvent) => {
    if (event.button !== 0) return;
    // Clear any hover card when the user starts a canvas drag.
    setHoveredId(null);
    dragRef.current = { x: event.clientX, y: event.clientY, tx: view.tx, ty: view.ty };
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  };
  const onPointerMove = (event: React.PointerEvent) => {
    if (!dragRef.current) return;
    const { tx: startTx, ty: startTy, x: startX, y: startY } = dragRef.current;
    const clientX = event.clientX;
    const clientY = event.clientY;
    setView((v) => ({
      ...v,
      tx: startTx + (clientX - startX),
      ty: startTy + (clientY - startY),
    }));
  };
  const onPointerUp = () => {
    dragRef.current = null;
  };
  const onWheel = (event: React.WheelEvent) => {
    event.preventDefault();
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    const cx = event.clientX - rect.left;
    const cy = event.clientY - rect.top;
    const deltaY = event.deltaY;
    setView((v) => {
      const delta = -deltaY * 0.0015;
      const nextScale = Math.min(1.6, Math.max(0.3, v.scale * (1 + delta)));
      const ratio = nextScale / v.scale;
      return { scale: nextScale, tx: cx - ratio * (cx - v.tx), ty: cy - ratio * (cy - v.ty) };
    });
  };

  const isOnPath = useCallback(
    (id: string) => selectedId !== null && (selectedId === id || selectedId.startsWith(`${id}/`)),
    [selectedId],
  );

  return (
    <div className="relative h-full w-full overflow-hidden bg-[radial-gradient(circle,#c8b99a_1px,transparent_1px)] [background-size:24px_24px]">
      {error ? (
        <div className="absolute left-1/2 top-4 z-20 -translate-x-1/2 rounded-md border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700 shadow">
          {error}
        </div>
      ) : null}

      {rootLoading ? (
        <div className="absolute left-1/2 top-1/2 z-20 flex -translate-x-1/2 -translate-y-1/2 items-center gap-2 text-slate-500">
          <Loader2 className="h-5 w-5 animate-spin" /> Loading suggestions…
        </div>
      ) : null}

      {!rootLoading && roots.length === 0 && !error ? (
        <div className="absolute left-1/2 top-1/2 z-10 -translate-x-1/2 -translate-y-1/2 text-center text-sm text-slate-400">
          Enter a username and click <span className="font-medium text-slate-600">Generate suggestions</span>.
        </div>
      ) : null}

      <div
        className="absolute inset-0 cursor-grab touch-none active:cursor-grabbing"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={onPointerUp}
        onWheel={onWheel}
      >
        <div
          className="absolute left-0 top-0 origin-top-left"
          style={{ transform: `translate(${view.tx}px, ${view.ty}px) scale(${view.scale})`, width, height }}
        >
          <svg className="pointer-events-none absolute left-0 top-0 overflow-visible" width={width} height={height}>
            {edges.map((edge) => {
              const midX = (edge.x1 + edge.x2) / 2;
              return (
                <path
                  key={edge.id}
                  d={`M ${edge.x1} ${edge.y1} C ${midX} ${edge.y1}, ${midX} ${edge.y2}, ${edge.x2} ${edge.y2}`}
                  fill="none"
                  stroke="#94a3b8"
                  strokeWidth={2}
                />
              );
            })}
          </svg>

          {positioned.map(({ entry, x, y }) => {
            const id = nodeId(entry.node);
            return (
              <div
                key={id}
                className="absolute"
                style={{ left: x, top: y, zIndex: hoveredId === id || (entry.children !== null && entry.children.length > 0) ? 50 : 0 }}
                onPointerDown={(event) => event.stopPropagation()}
              >
                <OpeningStudyNode
                  node={entry.node}
                  selected={selectedId === id}
                  onPath={isOnPath(id)}
                  expanded={entry.children !== null && entry.children.length > 0}
                  loading={entry.loading}
                  onSelect={() => onSelect(entry)}
                  onCollapse={() => onCollapse(entry)}
                  onHoverChange={(hovered) => onHoverChange(id, hovered)}
                />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
