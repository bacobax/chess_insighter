import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { ArrowLeft, Grid3x3, Network } from "lucide-react";
import { Button } from "~/components/ui/button";
import { cn } from "~/lib/utils";
import { OpeningStudyBoardView } from "~/components/opening-study/OpeningStudyBoardView";
import {
  OpeningStudyControls,
  type StudyControlsState,
} from "~/components/opening-study/OpeningStudyControls";
import {
  DEFAULT_ANSWERS,
  OpeningLabSetup,
  controlsFromAnswers,
  loadStoredSetup,
  saveStoredSetup,
  type SetupAnswers,
} from "~/components/opening-study/OpeningLabSetup";
import { OpeningStudyWhiteboard } from "~/components/opening-study/OpeningStudyWhiteboard";
import type { OpeningStudyTreeNode, TargetColor } from "~/lib/types";
import { RequireAuth, useAuth } from "~/components/auth/auth-provider";

export function meta() {
  return [
    { title: "Opening Lab · Chess Insighter" },
    { name: "description", content: "Interactive opening study tree ranked by your own criteria." },
  ];
}

export default function OpeningStudyPage() {
  return <RequireAuth><OpeningLab /></RequireAuth>;
}

function colorParam(value: string | null): TargetColor | null {
  return value === "white" || value === "black" ? value : null;
}

type LabView = "tree" | "board";
const VIEW_KEY = "chess-insighter:opening-lab:view";

function loadView(): LabView {
  try {
    return window.localStorage.getItem(VIEW_KEY) === "board" ? "board" : "tree";
  } catch {
    return "tree";
  }
}

function saveView(view: LabView) {
  try {
    window.localStorage.setItem(VIEW_KEY, view);
  } catch {
    // Per-viewer convenience only.
  }
}

function OpeningLab() {
  const { user } = useAuth();
  const userId = user?.id ?? "anonymous";
  const [searchParams] = useSearchParams();
  // `username` only tells Back where to return; the tree itself is general.
  const fromUsername = searchParams.get("username") ?? "";
  const urlColor = colorParam(searchParams.get("color"));

  const [stored] = useState(() => loadStoredSetup(userId));
  const [answers, setAnswers] = useState<SetupAnswers>(() => ({
    ...(stored?.answers ?? DEFAULT_ANSWERS),
    ...(urlColor ? { color: urlColor } : {}),
  }));
  const [controls, setControls] = useState<StudyControlsState>(() => {
    const base = stored?.controls ?? controlsFromAnswers(answers);
    return urlColor ? { ...base, targetColor: urlColor } : base;
  });
  // First visit: the survey covers the page until it is answered or skipped.
  const [hasSetup, setHasSetup] = useState(stored !== null);
  const [setupOpen, setSetupOpen] = useState(!hasSetup);
  // Returning users get their saved tree straight away.
  const [generationKey, setGenerationKey] = useState(stored ? 1 : 0);
  const [view, setView] = useState<LabView>(loadView);
  // Each view keeps its own selection; the inspector shows the active one.
  const [treeNode, setTreeNode] = useState<OpeningStudyTreeNode | null>(null);
  const [boardNode, setBoardNode] = useState<OpeningStudyTreeNode | null>(null);
  const selectedNode = view === "tree" ? treeNode : boardNode;
  const [boardJump, setBoardJump] = useState<{ path: string[]; nonce: number }>({ path: [], nonce: 0 });
  const [playerVector, setPlayerVector] = useState<Record<string, number> | null>(null);

  useEffect(() => {
    if (!setupOpen) saveStoredSetup(userId, answers, controls);
  }, [answers, controls, setupOpen, userId]);

  const update = (patch: Partial<StudyControlsState>) => setControls((prev) => ({ ...prev, ...patch }));

  function completeSetup(next: SetupAnswers) {
    setAnswers(next);
    setControls(controlsFromAnswers(next));
    setTreeNode(null);
    setBoardJump((prev) => ({ path: [], nonce: prev.nonce + 1 }));
    setHasSetup(true);
    setSetupOpen(false);
    setGenerationKey((key) => key + 1);
  }

  const switchView = useCallback((next: LabView) => {
    if (view === next) return;
    // Open the board at the position selected in the tree.
    if (next === "board" && treeNode) {
      setBoardJump((prev) => ({ path: treeNode.prefixUci, nonce: prev.nonce + 1 }));
    }
    saveView(next);
    setView(next);
  }, [treeNode, view]);

  const backTarget = fromUsername ? `/report/${encodeURIComponent(fromUsername)}` : "/dashboard";

  return (
    <main id="main-content" className="flex h-screen w-screen flex-col" style={{ color: "var(--ink)" }}>
      {setupOpen ? (
        <OpeningLabSetup
          initialAnswers={answers}
          canCancel={hasSetup}
          onComplete={completeSetup}
          onCancel={() => setSetupOpen(false)}
        />
      ) : null}
      <header className="flex min-h-16 items-center gap-3 px-4 py-3 sm:px-6" style={{ borderBottom: "1px solid var(--line)", background: "rgba(9,13,11,.92)", backdropFilter: "blur(16px)" }}>
        <Link to={backTarget}>
          <Button variant="ghost" size="sm">
            <ArrowLeft className="h-4 w-4" /> Back
          </Button>
        </Link>
        <div className="h-7 w-px bg-[var(--line)]" />
        <div>
          <h1 className="text-sm font-bold tracking-[-.02em]" style={{ fontFamily: "var(--font-display)", color: "var(--ink)" }}>OPENING LAB <span className="text-[var(--accent)]">/ {view === "tree" ? "TREE" : "BOARD"}</span></h1>
          <span className="hidden text-[10px] font-semibold uppercase tracking-[.12em] sm:block" style={{ color: "var(--ink-faint)" }}>
            {view === "tree"
              ? "Drag to pan · scroll to zoom · click or press Enter to expand"
              : "Drag a piece or pick a move · ← → to step through the line"}
          </span>
        </div>
        <div className="ml-auto flex rounded-lg p-0.5" role="tablist" aria-label="Opening Lab view" style={{ border: "1px solid var(--line)", background: "var(--paper-dark)" }}>
          {([
            { value: "tree", label: "Tree", Icon: Network },
            { value: "board", label: "Board", Icon: Grid3x3 },
          ] as const).map(({ value, label, Icon }) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={view === value}
              aria-controls={`opening-lab-${value}`}
              onClick={() => switchView(value)}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
                view === value ? "" : "opacity-70 hover:opacity-100",
              )}
              style={view === value ? { background: "var(--accent)", color: "#0a0e0b" } : { color: "var(--ink-soft)" }}
            >
              <Icon className="h-3.5 w-3.5" aria-hidden="true" /> {label}
            </button>
          ))}
        </div>
      </header>

      <div className="flex min-h-0 flex-1" aria-hidden={setupOpen || undefined}>
        <OpeningStudyControls
          state={controls}
          loading={false}
          onChange={update}
          onGenerate={() => setGenerationKey((key) => key + 1)}
          onReset={() => {
            setGenerationKey(0);
            setTreeNode(null);
            setBoardJump((prev) => ({ path: [], nonce: prev.nonce + 1 }));
            setPlayerVector(null);
          }}
          onRedoSetup={() => setSetupOpen(true)}
          selectedNode={selectedNode}
          playerVector={playerVector}
        />
        {/* Both views stay mounted so switching keeps the expanded tree and the board line. */}
        <div id="opening-lab-tree" role="tabpanel" className={cn("relative min-w-0 flex-1", view !== "tree" && "hidden")}>
          <OpeningStudyWhiteboard
            controls={controls}
            generationKey={generationKey}
            onNodeSelect={setTreeNode}
            onPlayerVectorLoad={setPlayerVector}
          />
        </div>
        <div id="opening-lab-board" role="tabpanel" className={cn("relative min-w-0 flex-1", view !== "board" && "hidden")}>
          <OpeningStudyBoardView
            controls={controls}
            generationKey={generationKey}
            active={view === "board"}
            jump={boardJump}
            onNodeSelect={setBoardNode}
          />
        </div>
      </div>
    </main>
  );
}
