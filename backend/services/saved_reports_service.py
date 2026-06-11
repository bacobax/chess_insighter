from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from backend.models import SavedReportEntry
from backend.settings import settings

_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SavedReportsIndex:
    def __init__(self, path: Path = settings.saved_reports_path):
        self.path = path

    def _load_raw(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _save_raw(self, entries: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def load(self) -> list[SavedReportEntry]:
        raw = self._load_raw()
        result = []
        for item in raw:
            try:
                result.append(SavedReportEntry.model_validate(item))
            except Exception:
                pass
        return result

    def upsert(self, entry: SavedReportEntry) -> None:
        with _lock:
            raw = self._load_raw()
            for existing in raw:
                if existing.get("cache_hash") == entry.cache_hash:
                    existing["last_refreshed_at"] = entry.last_refreshed_at
                    self._save_raw(raw)
                    return
            raw.insert(0, entry.model_dump())
            self._save_raw(raw)

    def delete(self, cache_hash: str) -> None:
        with _lock:
            raw = self._load_raw()
            raw = [item for item in raw if item.get("cache_hash") != cache_hash]
            self._save_raw(raw)


def save_report_entry(
    *,
    cache_hash: str,
    username: str,
    games_analyzed: int,
    request_params: dict,
) -> None:
    now = _now_iso()
    entry = SavedReportEntry(
        cache_hash=cache_hash,
        username=username,
        created_at=now,
        last_refreshed_at=now,
        games_analyzed=games_analyzed,
        request_params=request_params,
    )
    SavedReportsIndex().upsert(entry)
