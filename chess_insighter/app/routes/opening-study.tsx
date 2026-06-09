import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { ArrowLeft } from "lucide-react";
import { Button } from "~/components/ui/button";
import {
  DEFAULT_MATCHER_WEIGHTS,
  DEFAULT_WEIGHTS,
  OpeningStudyControls,
  type StudyControlsState,
} from "~/components/opening-study/OpeningStudyControls";
import { OpeningStudyWhiteboard } from "~/components/opening-study/OpeningStudyWhiteboard";
import type { OpeningStudyTreeNode, TargetColor } from "~/lib/types";

export function meta() {
  return [
    { title: "Opening Study Tree · Chess Insighter" },
    { name: "description", content: "Interactive, style-matched opening study suggestions." },
  ];
}

export default function OpeningStudyPage() {
  const [searchParams] = useSearchParams();
  const initialUsername = searchParams.get("username") ?? "";
  const initialCacheHash = searchParams.get("cacheHash") ?? "";
  const initialColor = (searchParams.get("color") as TargetColor | null) ?? "white";

  const [controls, setControls] = useState<StudyControlsState>({
    cacheHash: initialCacheHash,
    username: initialUsername,
    targetColor: initialColor === "black" ? "black" : "white",
    topK: 4,
    opponentTopK: 8,
    weights: { ...DEFAULT_WEIGHTS },
    similarityType: "cosine",
    weightedMatching: true,
    matcherWeights: { ...DEFAULT_MATCHER_WEIGHTS },
  });
  const [generationKey, setGenerationKey] = useState(0);
  const [selectedNode, setSelectedNode] = useState<OpeningStudyTreeNode | null>(null);
  const [playerVector, setPlayerVector] = useState<Record<string, number> | null>(null);

  const update = (patch: Partial<StudyControlsState>) => setControls((prev) => ({ ...prev, ...patch }));

  const backTarget = initialUsername
    ? `/report/${encodeURIComponent(initialUsername)}`
    : "/";

  return (
    <main className="flex h-screen w-screen flex-col" style={{ color: "var(--ink)" }}>
      <header className="flex items-center gap-3 px-4 py-2" style={{ borderBottom: "1px solid var(--line)", backgroundColor: "var(--paper-dark)" }}>
        <Link to={backTarget}>
          <Button variant="ghost" size="sm">
            <ArrowLeft className="h-4 w-4" /> Back
          </Button>
        </Link>
        <h1 className="text-sm font-semibold" style={{ fontFamily: "var(--font-display)", color: "var(--ink)" }}>Opening Study Tree</h1>
        <span className="text-xs" style={{ color: "var(--ink-faint)" }}>Drag to pan · scroll to zoom · click a node to expand</span>
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
  );
}
