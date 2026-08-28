import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LocateFixed, Loader2, Minus, Plus, X } from "lucide-react";
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
  order: number;
  siblingIndex: number;
  siblingCount: number;
};

type Edge = { id: string; x1: number; y1: number; x2: number; y2: number };

const COMPACT_GAP_Y = 18;
const EXPANDED_GAP_X = 40;
const TREE_PADDING = 24;
const EXPANDED_OVERFLOW_X = (EXPANDED_NODE_WIDTH - NODE_WIDTH) / 2;
const EXPANDED_OVERFLOW_Y = (EXPANDED_NODE_HEIGHT - NODE_HEIGHT) / 2;

function nodeId(node: OpeningStudyTreeNode): string {
  return node.prefixUci.join("/");
}

function nodeLabel(node: OpeningStudyTreeNode): string {
  const opening = node.openingNames[0] ? `, ${node.openingNames[0]}` : "";
  const turn = node.isTargetMove ? "your move" : "opponent move";
  return `${node.moveSan}${opening}, ${turn}, score ${Math.round(node.studyScore * 100)} out of 100, ${node.compatibleLineCount} compatible lines`;
}

function isExpanded(entry: Entry): boolean {
  return entry.children !== null && entry.children.length > 0;
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

type SubtreeLayout = {
  positioned: Positioned[];
  edges: Edge[];
  rootY: number;
  minY: number;
  maxY: number;
};

/**
 * Packs each visible subtree independently. An expanded card only changes the
 * space occupied by its own branch; unopened siblings keep the compact rhythm.
 */
function layout(roots: Entry[]): { positioned: Positioned[]; edges: Edge[]; width: number; height: number } {
  let order = 0;

  function cardLeft(entry: Entry, x: number): number {
    return x - (isExpanded(entry) ? EXPANDED_OVERFLOW_X : 0);
  }

  function cardRight(entry: Entry, x: number): number {
    return cardLeft(entry, x) + (isExpanded(entry) ? EXPANDED_NODE_WIDTH : NODE_WIDTH);
  }

  function build(
    entry: Entry,
    depth: number,
    x: number,
    siblingIndex: number,
    siblingCount: number,
  ): SubtreeLayout {
    const entryOrder = order;
    order += 1;
    const visibleChildren = isExpanded(entry) ? entry.children! : [];

    if (visibleChildren.length === 0) {
      return {
        positioned: [{ entry, x, y: 0, depth, order: entryOrder, siblingIndex, siblingCount }],
        edges: [],
        rootY: 0,
        minY: 0,
        maxY: NODE_HEIGHT,
      };
    }

    const childLayouts: Array<SubtreeLayout & { shiftY: number }> = [];
    let cursorY = 0;
    for (let index = 0; index < visibleChildren.length; index += 1) {
      const child = visibleChildren[index];
      const childExpanded = isExpanded(child);
      const childX =
        cardRight(entry, x) + EXPANDED_GAP_X + (childExpanded ? EXPANDED_OVERFLOW_X : 0);
      const childLayout = build(child, depth + 1, childX, index, visibleChildren.length);
      const shiftY = cursorY - childLayout.minY;
      childLayouts.push({ ...childLayout, shiftY });
      cursorY = childLayout.maxY + shiftY + COMPACT_GAP_Y;
    }

    const firstChildY = childLayouts[0].rootY + childLayouts[0].shiftY;
    const lastChild = childLayouts[childLayouts.length - 1];
    const lastChildY = lastChild.rootY + lastChild.shiftY;
    const rootY = (firstChildY + lastChildY) / 2;
    const positioned: Positioned[] = [
      { entry, x, y: rootY, depth, order: entryOrder, siblingIndex, siblingCount },
    ];
    const edges: Edge[] = [];

    for (const childLayout of childLayouts) {
      const childRoot = childLayout.positioned.find((item) => item.depth === depth + 1)!;
      const childRootY = childLayout.rootY + childLayout.shiftY;
      positioned.push(
        ...childLayout.positioned.map((item) => ({ ...item, y: item.y + childLayout.shiftY })),
      );
      edges.push(
        ...childLayout.edges.map((edge) => ({
          ...edge,
          y1: edge.y1 + childLayout.shiftY,
          y2: edge.y2 + childLayout.shiftY,
        })),
        {
          id: `${nodeId(entry.node)}->${nodeId(childRoot.entry.node)}`,
          x1: cardRight(entry, x),
          y1: rootY + NODE_HEIGHT / 2,
          x2: cardLeft(childRoot.entry, childRoot.x),
          y2: childRootY + NODE_HEIGHT / 2,
        },
      );
    }

    return {
      positioned,
      edges,
      rootY,
      minY: Math.min(rootY - EXPANDED_OVERFLOW_Y, ...childLayouts.map((child) => child.minY + child.shiftY)),
      maxY: Math.max(
        rootY - EXPANDED_OVERFLOW_Y + EXPANDED_NODE_HEIGHT,
        ...childLayouts.map((child) => child.maxY + child.shiftY),
      ),
    };
  }

  const positioned: Positioned[] = [];
  const edges: Edge[] = [];
  let cursorY = TREE_PADDING;
  const rootX = TREE_PADDING + EXPANDED_OVERFLOW_X;

  roots.forEach((root, index) => {
    const subtree = build(root, 0, rootX, index, roots.length);
    const shiftY = cursorY - subtree.minY;
    positioned.push(...subtree.positioned.map((item) => ({ ...item, y: item.y + shiftY })));
    edges.push(
      ...subtree.edges.map((edge) => ({ ...edge, y1: edge.y1 + shiftY, y2: edge.y2 + shiftY })),
    );
    cursorY = subtree.maxY + shiftY + COMPACT_GAP_Y;
  });

  positioned.sort((a, b) => a.order - b.order);
  const maxX = positioned.reduce((acc, item) => Math.max(acc, cardRight(item.entry, item.x)), 0);
  const maxY = positioned.reduce((acc, item) => {
    const bottom = isExpanded(item.entry)
      ? item.y - EXPANDED_OVERFLOW_Y + EXPANDED_NODE_HEIGHT
      : item.y + NODE_HEIGHT;
    return Math.max(acc, bottom);
  }, 0);
  return { positioned, edges, width: maxX + TREE_PADDING, height: maxY + TREE_PADDING };
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
  const [activeId, setActiveId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [rootLoading, setRootLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const playerVectorLoadedRef = useRef(false);
  const nodeRefs = useRef(new Map<string, HTMLDivElement>());
  const canvasRef = useRef<HTMLDivElement>(null);

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
      matchMode: controls.matchMode,
    }),
    [controls],
  );

  // (Re)generate the root level whenever the user hits "Generate".
  // generationKey === 0 is the initial / reset state: clear everything.
  useEffect(() => {
    setRoots([]);
    setSelectedId(null);
    setActiveId(null);
    setHoveredId(null);
    setError(null);
    setAnnouncement("");
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
        setActiveId(response.children[0] ? nodeId(response.children[0]) : null);
        setAnnouncement(
          response.children.length > 0
            ? `${response.children.length} opening moves loaded. Use the arrow keys to explore.`
            : "No opening moves were found.",
        );
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
      setAnnouncement(`Loading continuations after ${entry.node.moveSan}.`);
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
        setAnnouncement(
          response.children.length > 0
            ? `${entry.node.moveSan} expanded with ${response.children.length} continuations.`
            : `${entry.node.moveSan} has no further continuations.`,
        );
      } catch (err) {
        setRoots((prev) => updateEntry(prev, id, (e) => ({ ...e, loading: false })));
        setError(err instanceof Error ? err.message : "Failed to expand branch.");
        setAnnouncement(`Could not expand ${entry.node.moveSan}.`);
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
      setActiveId(id);
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
    setActiveId(id);
    setAnnouncement(`${entry.node.moveSan} collapsed.`);
  }, []);

  const onHoverChange = useCallback((id: string, hovered: boolean) => {
    setHoveredId(hovered ? id : (prev) => (prev === id ? null : prev));
  }, []);

  const { positioned, edges, width, height } = useMemo(() => layout(roots), [roots]);
  const visibleIds = useMemo(() => positioned.map(({ entry }) => nodeId(entry.node)), [positioned]);

  useEffect(() => {
    if (activeId && visibleIds.includes(activeId)) return;
    setActiveId(visibleIds[0] ?? null);
  }, [activeId, visibleIds]);

  const focusNode = useCallback((id: string | undefined) => {
    if (!id) return;
    setActiveId(id);
    requestAnimationFrame(() => {
      const element = nodeRefs.current.get(id);
      const canvas = canvasRef.current;
      element?.focus({ preventScroll: true });
      if (!element || !canvas) return;

      const nodeRect = element.getBoundingClientRect();
      const canvasRect = canvas.getBoundingClientRect();
      const margin = 32;
      let dx = 0;
      let dy = 0;
      if (nodeRect.left < canvasRect.left + margin) dx = canvasRect.left + margin - nodeRect.left;
      else if (nodeRect.right > canvasRect.right - margin) dx = canvasRect.right - margin - nodeRect.right;
      if (nodeRect.top < canvasRect.top + margin) dy = canvasRect.top + margin - nodeRect.top;
      else if (nodeRect.bottom > canvasRect.bottom - margin) dy = canvasRect.bottom - margin - nodeRect.bottom;
      if (dx !== 0 || dy !== 0) {
        setView((current) => ({ ...current, tx: current.tx + dx, ty: current.ty + dy }));
      }
    });
  }, []);

  const onNodeKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>, entry: Entry) => {
      if (event.target !== event.currentTarget) return;
      const id = nodeId(entry.node);
      const index = visibleIds.indexOf(id);
      let destination: string | undefined;

      switch (event.key) {
        case "Enter":
        case " ":
          event.preventDefault();
          onSelect(entry);
          return;
        case "ArrowDown":
          destination = visibleIds[index + 1];
          break;
        case "ArrowUp":
          destination = visibleIds[index - 1];
          break;
        case "Home":
          destination = visibleIds[0];
          break;
        case "End":
          destination = visibleIds[visibleIds.length - 1];
          break;
        case "ArrowRight":
          if (isExpanded(entry)) destination = nodeId(entry.children![0].node);
          else if (entry.children === null && !entry.loading) onSelect(entry);
          break;
        case "ArrowLeft": {
          if (isExpanded(entry)) {
            onCollapse(entry);
            destination = id;
          } else {
            const parentId = entry.node.prefixUci.slice(0, -1).join("/");
            destination = visibleIds.includes(parentId) ? parentId : undefined;
          }
          break;
        }
        default:
          return;
      }

      event.preventDefault();
      focusNode(destination);
    },
    [focusNode, onCollapse, onSelect, visibleIds],
  );

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

  const zoomBy = useCallback((factor: number) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    setView((current) => {
      const nextScale = Math.min(1.6, Math.max(0.3, current.scale * factor));
      if (!rect) return { ...current, scale: nextScale };
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      const ratio = nextScale / current.scale;
      return {
        scale: nextScale,
        tx: cx - ratio * (cx - current.tx),
        ty: cy - ratio * (cy - current.ty),
      };
    });
  }, []);

  const isOnPath = useCallback(
    (id: string) => selectedId !== null && (selectedId === id || selectedId.startsWith(`${id}/`)),
    [selectedId],
  );

  return (
    <div
      ref={canvasRef}
      className="relative h-full w-full overflow-hidden bg-[radial-gradient(circle,rgba(33,231,131,.17)_1px,transparent_1px)] [background-color:#090d0b] [background-size:24px_24px]"
      aria-busy={rootLoading}
    >
      <p id="opening-tree-help" className="sr-only">
        Opening move tree. Use Up and Down to move through visible nodes, Right to expand or enter a branch,
        Left to collapse or return to a parent, and Enter or Space to select a move.
      </p>
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {announcement}
      </div>

      {error ? (
        <div
          role="alert"
          className="absolute left-1/2 top-4 z-30 flex -translate-x-1/2 items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700 shadow"
        >
          <span>{error}</span>
          <button
            type="button"
            className="grid h-7 w-7 place-items-center rounded-md text-current hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]"
            onClick={() => setError(null)}
            aria-label="Dismiss error"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      ) : null}

      {rootLoading ? (
        <div role="status" className="absolute left-1/2 top-1/2 z-20 flex -translate-x-1/2 -translate-y-1/2 items-center gap-2 text-slate-500">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" /> Loading suggestions…
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
          role="tree"
          aria-label="Opening move suggestions"
          aria-describedby="opening-tree-help"
        >
          <svg aria-hidden="true" className="pointer-events-none absolute left-0 top-0 overflow-visible" width={width} height={height}>
            {edges.map((edge) => {
              const midX = (edge.x1 + edge.x2) / 2;
              return (
                <path
                  key={edge.id}
                  d={`M ${edge.x1} ${edge.y1} C ${midX} ${edge.y1}, ${midX} ${edge.y2}, ${edge.x2} ${edge.y2}`}
                  fill="none"
                  stroke="#314139"
                  strokeWidth={2}
                />
              );
            })}
          </svg>

          {positioned.map(({ entry, x, y, depth, siblingIndex, siblingCount }) => {
            const id = nodeId(entry.node);
            const expanded = isExpanded(entry);
            return (
              <div
                key={id}
                ref={(element) => {
                  if (element) nodeRefs.current.set(id, element);
                  else nodeRefs.current.delete(id);
                }}
                className="opening-tree-item absolute rounded-[14px] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--acid)]"
                style={{ left: x, top: y, zIndex: hoveredId === id || expanded ? 50 : 0 }}
                role="treeitem"
                aria-label={nodeLabel(entry.node)}
                aria-level={depth + 1}
                aria-posinset={siblingIndex + 1}
                aria-setsize={siblingCount}
                aria-selected={selectedId === id}
                aria-expanded={entry.children === null || expanded ? expanded : undefined}
                aria-busy={entry.loading || undefined}
                tabIndex={activeId === id ? 0 : -1}
                onFocus={() => setActiveId(id)}
                onKeyDown={(event) => onNodeKeyDown(event, entry)}
                onPointerDown={(event) => {
                  event.stopPropagation();
                  setActiveId(id);
                  event.currentTarget.focus({ preventScroll: true });
                }}
              >
                <OpeningStudyNode
                  node={entry.node}
                  selected={selectedId === id}
                  onPath={isOnPath(id)}
                  expanded={expanded}
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

      <div
        role="toolbar"
        aria-label="Tree view controls"
        className="absolute bottom-4 right-4 z-30 flex items-center gap-1 rounded-xl border border-[var(--line)] bg-[#101713]/95 p-1.5 shadow-xl backdrop-blur"
      >
        <button
          type="button"
          className="grid h-9 w-9 place-items-center rounded-lg text-[var(--ink-soft)] hover:bg-white/10 hover:text-[var(--ink)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]"
          onClick={() => zoomBy(1 / 1.18)}
          aria-label="Zoom out"
        >
          <Minus className="h-4 w-4" aria-hidden="true" />
        </button>
        <output className="min-w-12 text-center text-[10px] font-bold tabular-nums text-[var(--ink-soft)]" aria-label={`Zoom ${Math.round(view.scale * 100)} percent`}>
          {Math.round(view.scale * 100)}%
        </output>
        <button
          type="button"
          className="grid h-9 w-9 place-items-center rounded-lg text-[var(--ink-soft)] hover:bg-white/10 hover:text-[var(--ink)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]"
          onClick={() => zoomBy(1.18)}
          aria-label="Zoom in"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
        </button>
        <div className="mx-0.5 h-5 w-px bg-[var(--line)]" aria-hidden="true" />
        <button
          type="button"
          className="grid h-9 w-9 place-items-center rounded-lg text-[var(--ink-soft)] hover:bg-white/10 hover:text-[var(--ink)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]"
          onClick={() => setView({ tx: 40, ty: 40, scale: 1 })}
          aria-label="Reset tree view"
        >
          <LocateFixed className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
