import type { OpeningStudyTreeChildrenRequest } from "~/lib/types";
import type { StudyControlsState } from "./OpeningStudyControls";

/** Request fields shared by the tree and board views (everything but the prefix).
 *  General tree: no report or player vector is sent (style match is in development). */
export function studyRequestBase(
  controls: StudyControlsState,
): Omit<OpeningStudyTreeChildrenRequest, "prefixUci"> {
  return {
    targetColor: controls.targetColor,
    topK: controls.topK,
    opponentTopK: controls.opponentTopK,
    opponentMoveOrdering: controls.opponentMoveOrdering,
    weights: controls.weights,
    similarityType: controls.similarityType,
    weightedMatching: controls.weightedMatching,
    matcherWeights: controls.weightedMatching ? controls.matcherWeights : undefined,
    matchMode: controls.matchMode,
    evaluationMetric: controls.evaluationMetric,
    evaluationThreshold: controls.evaluationThresholds[controls.evaluationMetric],
  };
}
