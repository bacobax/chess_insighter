from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

from pymongo import ReturnDocument
from pymongo.database import Database

from backend.models import (
    DashboardPlayer,
    DashboardResponse,
    ReportBuildRequest,
    ReportBuildResponse,
    ReportSummary,
)
from backend.services.auth_service import AuthRepository, iso, now_utc, parse_iso
from backend.services.cache_service import ReportCache
from backend.services.mongo_service import get_database

NO_ID = {"_id": 0}


class ReportNotFound(FileNotFoundError):
    pass


def username_key(username: str) -> str:
    return username.strip().lower()


def generated_report_label(request: ReportBuildRequest) -> str:
    parts: list[str] = []
    if request.time_classes:
        parts.append(" / ".join(item.title() for item in request.time_classes))
    else:
        parts.append("All time controls")
    parts.append(f"{request.max_games} games")
    if request.rated_filter is True:
        parts.append("Rated")
    elif request.rated_filter is False:
        parts.append("Unrated")
    if request.since_year:
        since = str(request.since_year)
        if request.since_month:
            since = f"{request.since_year}-{request.since_month:02d}"
        parts.append(f"since {since}")
    parts.append("Engine" if request.use_engine else "No engine")
    return " · ".join(parts)


def games_analyzed(response: ReportBuildResponse) -> int:
    value = response.report.metadata.get("games_selected", 0)
    return int(value) if isinstance(value, (int, float)) else 0


def summary(record: dict[str, Any]) -> ReportSummary:
    return ReportSummary(
        id=record["id"],
        username=record["username"],
        generated_label=record["generated_label"],
        title=record.get("title"),
        cache_hash=record["cache_hash"],
        games_analyzed=record["games_analyzed"],
        request_params=record["request_params"],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        saved_at=record["saved_at"],
    )


class ReportsRepository:
    def __init__(self, database: Database | None = None, cache: ReportCache | None = None):
        self.db = database if database is not None else get_database()
        self.cache = cache or ReportCache()

    def record_build(
        self,
        *,
        owner_id: str,
        request: ReportBuildRequest,
        response: ReportBuildResponse,
    ) -> dict[str, Any]:
        current = now_utc()
        user_key = username_key(request.username)
        request_dump = request.model_dump()
        self._expire_drafts(current)
        refreshed = {
            "username": request.username,
            "username_key": user_key,
            "generated_label": generated_report_label(request),
            "request_params": request_dump,
            "games_analyzed": games_analyzed(response),
            "updated_at": iso(current),
        }
        report_id = str(uuid4())
        record = self.db.reports.find_one_and_update(
            {"owner_id": owner_id, "cache_hash": response.cache_hash},
            {
                "$set": refreshed,
                "$setOnInsert": {
                    "_id": report_id,
                    "id": report_id,
                    "owner_id": owner_id,
                    "cache_hash": response.cache_hash,
                    "title": None,
                    "status": "draft",
                    "created_at": iso(current),
                    "saved_at": None,
                    "draft_expires_at": iso(current + timedelta(hours=24)),
                },
            },
            projection=NO_ID,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return dict(record)

    def get_record(self, owner_id: str, report_id: str, *, saved_only: bool = False) -> dict[str, Any]:
        query: dict[str, Any] = {"_id": report_id, "owner_id": owner_id}
        if saved_only:
            query["status"] = "saved"
        record = self.db.reports.find_one(query, NO_ID)
        if record is None:
            raise ReportNotFound("Report not found")
        return record

    def get_by_cache_hash(self, owner_id: str, cache_hash: str) -> dict[str, Any]:
        record = self.db.reports.find_one({"owner_id": owner_id, "cache_hash": cache_hash}, NO_ID)
        if record is None:
            raise ReportNotFound("Report not found")
        return record

    def load_report(self, owner_id: str, report_id: str) -> ReportBuildResponse:
        record = self.get_record(owner_id, report_id)
        payload = self.cache.get(record["cache_hash"])
        if payload is None:
            raise ReportNotFound("Report artifact not found")
        payload.update(
            report_id=record["id"],
            saved=record["status"] == "saved",
            title=record.get("title"),
            request_params=record["request_params"],
        )
        return ReportBuildResponse.model_validate(payload)

    def save(self, owner_id: str, report_id: str, title: str | None) -> ReportSummary:
        current = now_utc()
        existing = self.get_record(owner_id, report_id)
        record = self.db.reports.find_one_and_update(
            {"_id": report_id, "owner_id": owner_id},
            {
                "$set": {
                    "status": "saved",
                    "title": title,
                    "saved_at": existing.get("saved_at") or iso(current),
                    "updated_at": iso(current),
                    "draft_expires_at": None,
                }
            },
            projection=NO_ID,
            return_document=ReturnDocument.AFTER,
        )
        if record is None:
            raise ReportNotFound("Report not found")
        target_id = str(uuid4())
        self.db.target_players.update_one(
            {"owner_id": owner_id, "username_key": record["username_key"]},
            {
                "$set": {"username": record["username"], "updated_at": iso(current)},
                "$setOnInsert": {
                    "_id": target_id,
                    "id": target_id,
                    "owner_id": owner_id,
                    "username_key": record["username_key"],
                    "created_at": iso(current),
                },
            },
            upsert=True,
        )
        self.db.audit_events.insert_one(
            {
                "_id": (event_id := str(uuid4())),
                "id": event_id,
                "kind": "report.saved",
                "user_id": owner_id,
                "report_id": report_id,
                "created_at": iso(current),
            }
        )
        return summary(record)

    def rename(self, owner_id: str, report_id: str, title: str | None) -> ReportSummary:
        record = self.db.reports.find_one_and_update(
            {"_id": report_id, "owner_id": owner_id, "status": "saved"},
            {"$set": {"title": title, "updated_at": iso(now_utc())}},
            projection=NO_ID,
            return_document=ReturnDocument.AFTER,
        )
        if record is None:
            raise ReportNotFound("Report not found")
        return summary(record)

    def delete(self, owner_id: str, report_id: str) -> None:
        record = self.db.reports.find_one_and_delete({"_id": report_id, "owner_id": owner_id}, projection=NO_ID)
        if record is None:
            raise ReportNotFound("Report not found")
        has_player_reports = self.db.reports.count_documents(
            {"owner_id": owner_id, "username_key": record["username_key"], "status": "saved"}, limit=1
        )
        if not has_player_reports:
            self.db.target_players.delete_many({"owner_id": owner_id, "username_key": record["username_key"]})
        cache_hash = record["cache_hash"]
        if cache_hash and not self.db.reports.count_documents({"cache_hash": cache_hash}, limit=1):
            self.cache.delete(cache_hash)

    def list_player(self, owner_id: str, username: str) -> list[ReportSummary]:
        rows = self.db.reports.find(
            {"owner_id": owner_id, "username_key": username_key(username), "status": "saved"}, NO_ID
        )
        return sorted((summary(item) for item in rows), key=lambda item: item.saved_at, reverse=True)

    def dashboard(self, owner_id: str) -> DashboardResponse:
        rows = list(self.db.reports.find({"owner_id": owner_id, "status": "saved"}, NO_ID))
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row["username_key"], []).append(row)
        players: list[DashboardPlayer] = []
        for player_rows in grouped.values():
            ordered = sorted(player_rows, key=lambda item: item["saved_at"], reverse=True)
            players.append(
                DashboardPlayer(
                    username=ordered[0]["username"],
                    report_count=len(ordered),
                    latest_report_at=ordered[0]["saved_at"],
                    reports=[summary(item) for item in ordered],
                )
            )
        players.sort(key=lambda item: item.latest_report_at, reverse=True)
        latest = max((item["saved_at"] for item in rows), default=None)
        return DashboardResponse(
            user=AuthRepository(self.db).resolve_user(owner_id),
            report_count=len(rows),
            player_count=len(players),
            latest_activity_at=latest,
            players=players,
        )

    def _expire_drafts(self, current) -> None:
        stale = [
            item["_id"]
            for item in self.db.reports.find(
                {"status": {"$ne": "saved"}, "draft_expires_at": {"$nin": [None, ""]}},
                {"_id": 1, "draft_expires_at": 1},
            )
            if parse_iso(item["draft_expires_at"]) <= current
        ]
        if stale:
            self.db.reports.delete_many({"_id": {"$in": stale}, "status": {"$ne": "saved"}})
