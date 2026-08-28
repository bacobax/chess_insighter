import type { GamesQueryRequest, GamesQueryResponse, Hparams, MistakePositionRequest, OpeningStudyTreeChildrenRequest, OpeningStudyTreeChildrenResponse, OpeningStudyTreeNode, PositionAnalysis, ReportBuildRequest, ReportBuildResponse, ReportGamesCatalogRequest, ReportGamesCatalogResponse, ReportMistakeDetailResponse, ReportMistakesResponse, ReportMistakesSelectionRequest, SavedReportsList, SaveReportRequest } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiRequestError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiRequestError";
  }
}

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
    throw new ApiRequestError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
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

export function analyzeReportMistakes(cacheHash: string, request: ReportMistakesSelectionRequest) {
  return apiFetch<ReportMistakesResponse>(`/api/report/${encodeURIComponent(cacheHash)}/mistakes`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function getActiveReportMistakes(cacheHash: string) {
  return apiFetch<ReportMistakesResponse>(`/api/report/${encodeURIComponent(cacheHash)}/mistakes`);
}

export function queryReportMistakeGames(cacheHash: string, request: ReportGamesCatalogRequest) {
  return apiFetch<ReportGamesCatalogResponse>(`/api/report/${encodeURIComponent(cacheHash)}/mistakes/games/query`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function getReportMistakeDetail(cacheHash: string, analysisHash: string, mistakeId: string) {
  return apiFetch<ReportMistakeDetailResponse>(
    `/api/report/${encodeURIComponent(cacheHash)}/mistakes/${encodeURIComponent(analysisHash)}/${encodeURIComponent(mistakeId)}`,
  );
}

export function analyzePosition(request: MistakePositionRequest) {
  return apiFetch<PositionAnalysis>("/api/mistakes/position", {
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

export function saveReport(request: SaveReportRequest) {
  return apiFetch<void>("/api/reports/saved", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function deleteSavedReport(cacheHash: string) {
  return apiFetch<void>(`/api/reports/saved/${encodeURIComponent(cacheHash)}`, { method: "DELETE" });
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
