import type { GamesQueryRequest, GamesQueryResponse, Hparams, OpeningMatchRequest, OpeningMatchResponse, ReportBuildRequest, ReportBuildResponse } from "./types";

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

export function rematchOpenings(request: OpeningMatchRequest) {
  return apiFetch<OpeningMatchResponse>("/api/openings/matches", {
    method: "POST",
    body: JSON.stringify(request),
  });
}
