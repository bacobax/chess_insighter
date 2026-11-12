import type { AuthUser, DashboardResponse, GamesQueryRequest, GamesQueryResponse, Hparams, MistakePositionRequest, OpeningStudyTreeChildrenRequest, OpeningStudyTreeChildrenResponse, OpeningStudyTreeNode, PlayerReportsResponse, PositionAnalysis, RegisterResponse, ReportBuildJobAccepted, ReportBuildJobStatus, ReportBuildRequest, ReportBuildResponse, ReportGamesCatalogRequest, ReportGamesCatalogResponse, ReportMistakeDetailResponse, ReportMistakesResponse, ReportMistakesSelectionRequest, ReportSummary, OpeningDrillCatalog, Repertoire, RepertoireColor, RepertoireLines, RepertoirePosition, RepertoireSettings, TrainingCard, TrainingCardReviewRequest, TrainingPlan, TrainingPlanBuildRequest } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiRequestError extends Error {
  constructor(message: string, readonly status: number, readonly code?: string) {
    super(message);
    this.name = "ApiRequestError";
  }
}

function cookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  const prefix = `${encodeURIComponent(name)}=`;
  return document.cookie.split("; ").find((item) => item.startsWith(prefix))?.slice(prefix.length);
}

const SERVER_UNREACHABLE = "Can't reach the Chess Insighter server. Check that the backend is running on port 8000, then try again.";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const csrf = !["GET", "HEAD", "OPTIONS"].includes(method) ? cookie("chess_insighter_csrf") : undefined;
  const request = () => fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRF-Token": decodeURIComponent(csrf) } : {}),
      ...(init?.headers ?? {}),
    },
  });
  let response: Response;
  try {
    response = await request();
  } catch {
    // The browser rejects with a bare "Failed to fetch" when the backend is down or
    // restarting (e.g. a --reload after a code change). Reads are safe to retry once.
    if (method !== "GET") throw new ApiRequestError(SERVER_UNREACHABLE, 0, "network_error");
    await new Promise((resolve) => setTimeout(resolve, 1500));
    try {
      response = await request();
    } catch {
      throw new ApiRequestError(SERVER_UNREACHABLE, 0, "network_error");
    }
  }
  if (!response.ok) {
    let message = `Request failed: ${response.status}`;
    let code: string | undefined;
    try {
      const body = (await response.json()) as { code?: string; message?: string; detail?: string };
      message = body.message ?? body.detail ?? message;
      code = body.code;
    } catch {
      // Use generic status message.
    }
    if (response.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("chess-insighter:unauthorized"));
    }
    throw new ApiRequestError(message, response.status, code);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function register(email: string, password: string) {
  return apiFetch<RegisterResponse>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function resendVerification(registrationId: string, socketToken: string) {
  return apiFetch<void>("/api/auth/resend-verification", {
    method: "POST",
    body: JSON.stringify({ registration_id: registrationId, socket_token: socketToken }),
  });
}

export function verifyEmail(token: string) {
  return apiFetch<AuthUser>("/api/auth/verify-email", { method: "POST", body: JSON.stringify({ token }) });
}

export function login(email: string, password: string) {
  return apiFetch<{ user: AuthUser }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function logout() {
  return apiFetch<void>("/api/auth/logout", { method: "POST" });
}

export function getCurrentUser() {
  return apiFetch<{ user: AuthUser }>("/api/auth/me");
}

export function registrationSocketUrl(registrationId: string, socketToken: string): string {
  const url = new URL(
    `${API_BASE}/api/auth/registrations/${encodeURIComponent(registrationId)}/status`,
    window.location.origin,
  );
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("token", socketToken);
  return url.toString();
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

export function startReportBuild(request: ReportBuildRequest) {
  return apiFetch<ReportBuildJobAccepted>("/api/report/builds", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function getReportBuildStatus(buildId: string) {
  return apiFetch<ReportBuildJobStatus>(`/api/report/builds/${encodeURIComponent(buildId)}`);
}

export function cancelReportBuild(buildId: string, keepalive = false) {
  return apiFetch<ReportBuildJobStatus>(`/api/report/builds/${encodeURIComponent(buildId)}/cancel`, {
    method: "POST",
    keepalive,
  });
}

export function reportBuildSocketUrl(buildId: string, socketToken: string): string {
  const url = new URL(`${API_BASE}/api/report/builds/${encodeURIComponent(buildId)}/status`, window.location.origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("token", socketToken);
  return url.toString();
}

export function analyzeReportMistakes(reportId: string, request: ReportMistakesSelectionRequest) {
  return apiFetch<ReportMistakesResponse>(`/api/reports/${encodeURIComponent(reportId)}/mistakes`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function getActiveReportMistakes(reportId: string) {
  return apiFetch<ReportMistakesResponse>(`/api/reports/${encodeURIComponent(reportId)}/mistakes`);
}

export function queryReportMistakeGames(reportId: string, request: ReportGamesCatalogRequest) {
  return apiFetch<ReportGamesCatalogResponse>(`/api/reports/${encodeURIComponent(reportId)}/mistakes/games/query`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function getReportMistakeDetail(reportId: string, analysisHash: string, mistakeId: string) {
  return apiFetch<ReportMistakeDetailResponse>(
    `/api/reports/${encodeURIComponent(reportId)}/mistakes/${encodeURIComponent(analysisHash)}/${encodeURIComponent(mistakeId)}`,
  );
}

export function analyzePosition(request: MistakePositionRequest) {
  return apiFetch<PositionAnalysis>("/api/mistakes/position", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function getReport(reportId: string) {
  return apiFetch<ReportBuildResponse>(`/api/reports/${encodeURIComponent(reportId)}`);
}

export function getDashboard() {
  return apiFetch<DashboardResponse>("/api/dashboard");
}

export function getPlayerReports(username: string) {
  return apiFetch<PlayerReportsResponse>(`/api/players/${encodeURIComponent(username)}/reports`);
}

export function saveReport(reportId: string, title?: string | null) {
  return apiFetch<ReportSummary>(`/api/reports/${encodeURIComponent(reportId)}/save`, {
    method: "POST",
    body: JSON.stringify({ title: title ?? null }),
  });
}

export function renameReport(reportId: string, title?: string | null) {
  return apiFetch<ReportSummary>(`/api/reports/${encodeURIComponent(reportId)}`, {
    method: "PATCH",
    body: JSON.stringify({ title: title ?? null }),
  });
}

export function deleteReport(reportId: string) {
  return apiFetch<void>(`/api/reports/${encodeURIComponent(reportId)}`, { method: "DELETE" });
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

export function startTrainingPlanBuild(request: TrainingPlanBuildRequest) {
  return apiFetch<ReportBuildJobAccepted>("/api/training-plans/builds", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function getTrainingPlanBuildStatus(buildId: string) {
  return apiFetch<ReportBuildJobStatus>(`/api/training-plans/builds/${encodeURIComponent(buildId)}`);
}

export function cancelTrainingPlanBuild(buildId: string) {
  return apiFetch<ReportBuildJobStatus>(`/api/training-plans/builds/${encodeURIComponent(buildId)}/cancel`, { method: "POST" });
}

export function trainingPlanBuildSocketUrl(buildId: string, socketToken: string): string {
  const url = new URL(`${API_BASE}/api/training-plans/builds/${encodeURIComponent(buildId)}/status`, window.location.origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("token", socketToken);
  return url.toString();
}

/** Resolves to null when no plan has been built for this player yet. */
export async function getTrainingPlan(username: string): Promise<TrainingPlan | null> {
  try {
    return await apiFetch<TrainingPlan>(`/api/players/${encodeURIComponent(username)}/training-plan`);
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 404) return null;
    throw error;
  }
}

export function reviewTrainingCard(username: string, cardId: string, request: TrainingCardReviewRequest) {
  return apiFetch<TrainingCard>(
    `/api/players/${encodeURIComponent(username)}/training-plan/cards/${encodeURIComponent(cardId)}/review`,
    { method: "POST", body: JSON.stringify(request) },
  );
}

/** Every drill line for a repertoire opening, the opponent's replies branching over popular Lichess moves. */
export function getOpeningDrillCatalog(line: string, side: "white" | "black") {
  return apiFetch<OpeningDrillCatalog>("/api/training/opening-drill", {
    method: "POST",
    body: JSON.stringify({ line, side }),
  });
}

// --- Repertoire ------------------------------------------------------------------------

/** Your playable moves (engine-checked) or the opponent's popular replies in one position. */
export function getRepertoirePosition(color: RepertoireColor, prefixUci: string[]) {
  return apiFetch<RepertoirePosition>("/api/repertoire/position", {
    method: "POST",
    body: JSON.stringify({ color, prefixUci }),
  });
}

export function getRepertoire(color: RepertoireColor) {
  return apiFetch<Repertoire>(`/api/repertoires/${color}`);
}

/** Save your move in a position; rejected (422 not_playable) when the engine says it loses too much. */
export function setRepertoireChoice(color: RepertoireColor, prefixUci: string[], moveUci: string) {
  return apiFetch<Repertoire>(`/api/repertoires/${color}/choices`, {
    method: "PUT",
    body: JSON.stringify({ prefixUci, moveUci }),
  });
}

export function removeRepertoireChoice(color: RepertoireColor, prefixUci: string[]) {
  return apiFetch<Repertoire>(`/api/repertoires/${color}/choices?prefix=${encodeURIComponent(prefixUci.join(" "))}`, {
    method: "DELETE",
  });
}

export function updateRepertoireSettings(color: RepertoireColor, patch: Partial<RepertoireSettings>) {
  return apiFetch<Repertoire>(`/api/repertoires/${color}/settings`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

/** Fill empty positions along SAN lines ("1.e4 e5 2.Nf3"); omitted = the default short repertoire. */
export function seedRepertoire(color: RepertoireColor, lines?: string[]) {
  return apiFetch<Repertoire>(`/api/repertoires/${color}/seed`, {
    method: "POST",
    body: JSON.stringify({ lines: lines ?? null }),
  });
}

export function getRepertoireLines(color: RepertoireColor, startPrefixUci: string[] = [], fetchBudget = 3) {
  return apiFetch<RepertoireLines>(`/api/repertoires/${color}/lines`, {
    method: "POST",
    body: JSON.stringify({ startPrefixUci, fetchBudget }),
  });
}
