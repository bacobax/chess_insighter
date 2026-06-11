import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { Clock, RefreshCw, Trash2 } from "lucide-react";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { deleteSavedReport, getSavedReports } from "~/lib/api";
import type { SavedReportEntry } from "~/lib/types";

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function filterSummary(entry: SavedReportEntry): string {
  const parts: string[] = [];
  const p = entry.request_params;
  if (p.max_games) parts.push(`${p.max_games} games`);
  if (p.time_classes && Array.isArray(p.time_classes) && p.time_classes.length > 0) {
    parts.push((p.time_classes as string[]).join(", "));
  }
  if (p.since_year) parts.push(`from ${p.since_year}`);
  if (!p.use_engine) parts.push("no engine");
  return parts.join(" · ") || "default settings";
}

export function SavedReportsList() {
  const [entries, setEntries] = useState<SavedReportEntry[]>([]);
  const [deleting, setDeleting] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    getSavedReports()
      .then((data) => setEntries(data.entries))
      .catch(() => {});
  }, []);

  if (entries.length === 0) return null;

  async function handleDelete(cacheHash: string) {
    setDeleting(cacheHash);
    try {
      await deleteSavedReport(cacheHash);
      setEntries((prev) => prev.filter((e) => e.cache_hash !== cacheHash));
    } finally {
      setDeleting(null);
    }
  }

  function handleOpen(entry: SavedReportEntry) {
    navigate(`/report/${encodeURIComponent(entry.username)}?restore=${encodeURIComponent(entry.cache_hash)}`);
  }

  function handleRebuild(entry: SavedReportEntry) {
    navigate(`/report/${encodeURIComponent(entry.username)}`, {
      state: { rebuildParams: entry.request_params },
    });
  }

  return (
    <Card className="w-full">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Clock className="h-4 w-4" style={{ color: "var(--ink-soft)" }} />
          Recent Reports
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <ul className="divide-y" style={{ borderColor: "var(--line)" }}>
          {entries.map((entry) => (
            <li key={entry.cache_hash} className="flex flex-col gap-2 px-6 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <div className="font-medium" style={{ color: "var(--ink)" }}>{entry.username}</div>
                <div className="text-xs" style={{ color: "var(--ink-faint)" }}>
                  {entry.games_analyzed} games · {filterSummary(entry)}
                </div>
                <div className="text-xs" style={{ color: "var(--ink-faint)" }}>
                  {formatDate(entry.last_refreshed_at)}
                </div>
              </div>
              <div className="flex shrink-0 gap-2">
                <Button size="sm" variant="outline" onClick={() => handleOpen(entry)}>
                  Open
                </Button>
                <Button size="sm" variant="outline" onClick={() => handleRebuild(entry)}>
                  <RefreshCw className="h-3.5 w-3.5" />
                  Rebuild
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={deleting === entry.cache_hash}
                  onClick={() => handleDelete(entry.cache_hash)}
                  aria-label="Delete"
                >
                  <Trash2 className="h-3.5 w-3.5" style={{ color: "var(--ink-faint)" }} />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
