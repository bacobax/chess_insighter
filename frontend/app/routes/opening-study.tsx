import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { ArrowLeft } from "lucide-react";
import { Button } from "~/components/ui/button";
import {
  DEFAULT_MATCHER_WEIGHTS,
  DEFAULT_WEIGHTS,
  OpeningStudyControls,
  applyModeToWeights,
  type StudyControlsState,
} from "~/components/opening-study/OpeningStudyControls";
import { OpeningStudyWhiteboard } from "~/components/opening-study/OpeningStudyWhiteboard";
import type { OpeningStudyTreeNode, TargetColor } from "~/lib/types";
import { RequireAuth } from "~/components/auth/auth-provider";

export function meta() {
  return [
    { title: "Opening Study Tree · Chess Insighter" },
    { name: "description", content: "Interactive, style-matched opening study suggestions." },
  ];
}

export default function OpeningStudyPage() {
  const [searchParams] = useSearchParams();
  const initialUsername = searchParams.get("username") ?? "";
  const initialReportId = searchParams.get("reportId") ?? "";
  const initialColor = (searchParams.get("color") as TargetColor | null) ?? "white";

  const [controls, setControls] = useState<StudyControlsState>({
    cacheHash: initialReportId,
    username: initialUsername,
    targetColor: initialColor === "black" ? "black" : "white",
    topK: 4,
    opponentTopK: 8,
    opponentMoveOrdering: "popularity",
    weights: applyModeToWeights({ ...DEFAULT_WEIGHTS }, "style", "practical"),
    similarityType: "cosine",
    weightedMatching: true,
    matcherWeights: { ...DEFAULT_MATCHER_WEIGHTS },
    matchMode: "style",
    evaluationMetric: "practical",
  });
  const [generationKey, setGenerationKey] = useState(0);
  const [selectedNode, setSelectedNode] = useState<OpeningStudyTreeNode | null>(null);
  const [playerVector, setPlayerVector] = useState<Record<string, number> | null>(null);

  const update = (patch: Partial<StudyControlsState>) => setControls((prev) => ({ ...prev, ...patch }));

  const backTarget = initialUsername
    ? `/report/${encodeURIComponent(initialUsername)}`
    : "/";

  return <RequireAuth>{(
    <main id="main-content" className="flex h-screen w-screen flex-col" style={{ color: "var(--ink)" }}>
      <header className="flex min-h-16 items-center gap-3 px-4 py-3 sm:px-6" style={{ borderBottom: "1px solid var(--line)", background: "rgba(9,13,11,.92)", backdropFilter: "blur(16px)" }}>
        <Link to={backTarget}>
          <Button variant="ghost" size="sm">
            <ArrowLeft className="h-4 w-4" /> Back
          </Button>
        </Link>
        <div className="h-7 w-px bg-[var(--line)]" />
        <div>
          <h1 className="text-sm font-bold tracking-[-.02em]" style={{ fontFamily: "var(--font-display)", color: "var(--ink)" }}>OPENING LAB <span className="text-[var(--accent)]">/ TREE</span></h1>
          <span className="hidden text-[10px] font-semibold uppercase tracking-[.12em] sm:block" style={{ color: "var(--ink-faint)" }}>Drag to pan · scroll to zoom · click or press Enter to expand</span>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <OpeningStudyControls
          state={controls}
          loading={false}
          onChange={update}
          onGenerate={() => setGenerationKey((key) => key + 1)}
          onReset={() => {
            setGenerationKey(0);
            setSelectedNode(null);
            setPlayerVector(null);
          }}
          selectedNode={selectedNode}
          playerVector={playerVector}
        />
        <div className="relative min-w-0 flex-1">
          <OpeningStudyWhiteboard
            controls={controls}
            generationKey={generationKey}
            onNodeSelect={setSelectedNode}
            onPlayerVectorLoad={setPlayerVector}
          />
        </div>
      </div>
    </main>
  )}</RequireAuth>;
}
