from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

from backend.models import (
    DashboardPlayer,
    DashboardResponse,
    ReportBuildRequest,
    ReportBuildResponse,
    ReportSummary,
)
from backend.services.auth_service import AuthRepository, iso, now_utc, parse_iso
from backend.services.cache_service import ReportCache
from backend.services.database_service import JsonDatabase


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
    def __init__(self, database: JsonDatabase | None = None, cache: ReportCache | None = None):
        self.database = database or JsonDatabase()
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

        def operation(data: dict[str, Any]) -> dict[str, Any]:
            self._expire_drafts(data, current)
            existing = next(
                (
                    item
                    for item in data["reports"]
                    if item["owner_id"] == owner_id and item["cache_hash"] == response.cache_hash
                ),
                None,
            )
            if existing is not None:
                existing.update(
                    username=request.username,
                    username_key=user_key,
                    generated_label=generated_report_label(request),
                    request_params=request_dump,
                    games_analyzed=games_analyzed(response),
                    updated_at=iso(current),
                )
                return dict(existing)
            record = {
                "id": str(uuid4()),
                "owner_id": owner_id,
                "username": request.username,
                "username_key": user_key,
                "cache_hash": response.cache_hash,
                "request_params": request_dump,
                "generated_label": generated_report_label(request),
                "title": None,
                "games_analyzed": games_analyzed(response),
                "status": "draft",
                "created_at": iso(current),
                "updated_at": iso(current),
                "saved_at": None,
                "draft_expires_at": iso(current + timedelta(hours=24)),
            }
            data["reports"].append(record)
            return dict(record)

        return self.database.transaction(operation)

    def get_record(self, owner_id: str, report_id: str, *, saved_only: bool = False) -> dict[str, Any]:
        data = self.database.read()
        record = next(
            (
                item
                for item in data["reports"]
                if item["id"] == report_id
                and item["owner_id"] == owner_id
                and (not saved_only or item["status"] == "saved")
            ),
            None,
        )
        if record is None:
            raise ReportNotFound("Report not found")
        return record

    def get_by_cache_hash(self, owner_id: str, cache_hash: str) -> dict[str, Any]:
        data = self.database.read()
        record = next(
            (item for item in data["reports"] if item["owner_id"] == owner_id and item["cache_hash"] == cache_hash),
            None,
        )
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

        def operation(data: dict[str, Any]) -> ReportSummary:
            record = next(
                (item for item in data["reports"] if item["id"] == report_id and item["owner_id"] == owner_id),
                None,
            )
            if record is None:
                raise ReportNotFound("Report not found")
            record.update(status="saved", title=title, saved_at=record.get("saved_at") or iso(current), updated_at=iso(current))
            record["draft_expires_at"] = None
            target = next(
                (
                    item
                    for item in data["target_players"]
                    if item["owner_id"] == owner_id and item["username_key"] == record["username_key"]
                ),
                None,
            )
            if target is None:
                data["target_players"].append(
                    {
                        "id": str(uuid4()),
                        "owner_id": owner_id,
                        "username": record["username"],
                        "username_key": record["username_key"],
                        "created_at": iso(current),
                        "updated_at": iso(current),
                    }
                )
            else:
                target.update(username=record["username"], updated_at=iso(current))
            data["audit_events"].append(
                {"id": str(uuid4()), "kind": "report.saved", "user_id": owner_id, "report_id": report_id, "created_at": iso(current)}
            )
            return summary(record)

        return self.database.transaction(operation)

    def rename(self, owner_id: str, report_id: str, title: str | None) -> ReportSummary:
        current = now_utc()

        def operation(data: dict[str, Any]) -> ReportSummary:
            record = next(
                (
                    item
                    for item in data["reports"]
                    if item["id"] == report_id and item["owner_id"] == owner_id and item["status"] == "saved"
                ),
                None,
            )
            if record is None:
                raise ReportNotFound("Report not found")
            record.update(title=title, updated_at=iso(current))
            return summary(record)

        return self.database.transaction(operation)

    def delete(self, owner_id: str, report_id: str) -> None:
        cache_hash: str | None = None

        def operation(data: dict[str, Any]) -> bool:
            nonlocal cache_hash
            record = next((item for item in data["reports"] if item["id"] == report_id and item["owner_id"] == owner_id), None)
            if record is None:
                raise ReportNotFound("Report not found")
            cache_hash = record["cache_hash"]
            data["reports"].remove(record)
            has_player_reports = any(
                item["owner_id"] == owner_id
                and item["username_key"] == record["username_key"]
                and item["status"] == "saved"
                for item in data["reports"]
            )
            if not has_player_reports:
                data["target_players"][:] = [
                    item
                    for item in data["target_players"]
                    if not (item["owner_id"] == owner_id and item["username_key"] == record["username_key"])
                ]
            still_referenced = any(item["cache_hash"] == cache_hash for item in data["reports"])
            return not still_referenced

        purge_artifact = self.database.transaction(operation)
        if purge_artifact and cache_hash:
            self.cache.delete(cache_hash)

    def list_player(self, owner_id: str, username: str) -> list[ReportSummary]:
        key = username_key(username)
        data = self.database.read()
        rows = [
            summary(item)
            for item in data["reports"]
            if item["owner_id"] == owner_id and item["username_key"] == key and item["status"] == "saved"
        ]
        return sorted(rows, key=lambda item: item.saved_at, reverse=True)

    def dashboard(self, owner_id: str) -> DashboardResponse:
        database = self.database.read()
        user = next(item for item in database["users"] if item["id"] == owner_id)
        rows = [item for item in database["reports"] if item["owner_id"] == owner_id and item["status"] == "saved"]
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
            user=AuthRepository(self.database).resolve_user(owner_id),
            report_count=len(rows),
            player_count=len(players),
            latest_activity_at=latest,
            players=players,
        )

    @staticmethod
    def _expire_drafts(data: dict[str, Any], current) -> None:
        data["reports"][:] = [
            item
            for item in data["reports"]
            if item["status"] == "saved"
            or not item.get("draft_expires_at")
            or parse_iso(item["draft_expires_at"]) > current
        ]
