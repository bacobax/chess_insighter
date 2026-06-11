import type { GamesQueryRequest, GamesQueryResponse, Hparams, OpeningMatchRequest, OpeningMatchResponse, OpeningStudyTreeChildrenRequest, OpeningStudyTreeChildrenResponse, OpeningStudyTreeNode, ReportBuildRequest, ReportBuildResponse, SavedReportsList } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let message = `Request failed: ${response.status}`;
    try {
      const body = (await response.json()) as { message?: string; detail?: string };
      message = body.message ?? body.detail ?? message;
    } catch {
      // Use generic status message.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export async function getDefaultHparams(): Promise<Hparams> {
  const response = await apiFetch<{ hparams: Hparams }>("/api/config/default-hparams");
  return response.hparams;
}

export function queryGames(request: GamesQueryRequest) {
  return apiFetch<GamesQueryResponse>("/api/games/query", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function buildReport(request: ReportBuildRequest) {
  return apiFetch<ReportBuildResponse>("/api/report/build", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function getReportByHash(cacheHash: string) {
  return apiFetch<ReportBuildResponse>(`/api/report/cache/${encodeURIComponent(cacheHash)}`);
}

export function getSavedReports() {
  return apiFetch<SavedReportsList>("/api/reports/saved");
}

export function deleteSavedReport(cacheHash: string) {
  return apiFetch<void>(`/api/reports/saved/${encodeURIComponent(cacheHash)}`, { method: "DELETE" });
}

export function rematchOpenings(request: OpeningMatchRequest) {
  return apiFetch<OpeningMatchResponse>("/api/openings/matches", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

/**
 * Fetch the top-k child suggestion nodes for a single move prefix. The backend
 * expands lazily, one level at a time; the returned nodes carry their own
 * `prefixUci`, which the caller passes back to expand deeper.
 *
 * The backend does not assign node ids, so we derive a stable `id` from the
 * full move prefix (which is unique per node within the tree).
 */
export async function fetchOpeningStudyChildren(
  request: OpeningStudyTreeChildrenRequest,
): Promise<OpeningStudyTreeChildrenResponse> {
  const response = await apiFetch<OpeningStudyTreeChildrenResponse>("/api/opening-study-tree/children", {
    method: "POST",
    body: JSON.stringify(request),
  });
  return {
    ...response,
    children: response.children.map(
      (node): OpeningStudyTreeNode => ({ ...node, id: node.prefixUci.join("/") }),
    ),
  };
}
