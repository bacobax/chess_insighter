from __future__ import annotations

import hashlib
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.models import ReportBuildJobAccepted, ReportBuildJobStatus, ReportBuildRequest


TERMINAL = {"completed", "failed", "cancelled"}


class BuildJobNotFound(FileNotFoundError):
    pass


@dataclass
class BuildJob:
    id: str
    owner_id: str
    socket_digest: str
    request: ReportBuildRequest
    status: str = "queued"
    stage: str = "queued"
    progress: float = 0.0
    message: str = "Waiting to start analysis"
    revision: int = 0
    processed: int | None = None
    total: int | None = None
    report_id: str | None = None
    error: str | None = None
    subscribers: int = 0
    had_subscriber: bool = False
    cancel_event: threading.Event = field(default_factory=threading.Event)
    disconnect_timer: threading.Timer | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class InMemoryReportBuildJobStore:
    """Ephemeral single-process build state behind a replaceable store interface."""

    def __init__(self) -> None:
        self._jobs: dict[str, BuildJob] = {}
        self._lock = threading.RLock()

    def create(self, owner_id: str, request: ReportBuildRequest) -> tuple[ReportBuildJobAccepted, BuildJob]:
        token = secrets.token_urlsafe(32)
        job = BuildJob(
            id=str(uuid4()),
            owner_id=owner_id,
            socket_digest=self._digest(token),
            request=request,
        )
        with self._lock:
            self._jobs[job.id] = job
        return ReportBuildJobAccepted(build_id=job.id, socket_token=token, status="queued"), job

    def get(self, build_id: str, owner_id: str) -> BuildJob:
        with self._lock:
            job = self._jobs.get(build_id)
            if job is None or job.owner_id != owner_id:
                raise BuildJobNotFound("Build not found")
            return job

    def authorize_socket(self, build_id: str, owner_id: str, token: str) -> BuildJob:
        job = self.get(build_id, owner_id)
        if not secrets.compare_digest(job.socket_digest, self._digest(token)):
            raise BuildJobNotFound("Build not found")
        return job

    def snapshot(self, job: BuildJob) -> ReportBuildJobStatus:
        with self._lock:
            return ReportBuildJobStatus(
                build_id=job.id,
                status=job.status,
                stage=job.stage,
                progress=job.progress,
                message=job.message,
                revision=job.revision,
                processed=job.processed,
                total=job.total,
                report_id=job.report_id,
                error=job.error,
            )

    def update(self, job: BuildJob, *, status: str | None = None, stage: str | None = None,
               progress: float | None = None, message: str | None = None,
               processed: int | None = None, total: int | None = None,
               report_id: str | None = None, error: str | None = None) -> None:
        with self._lock:
            if job.status in TERMINAL:
                return
            if status is not None:
                job.status = status
            if stage is not None:
                job.stage = stage
            if progress is not None:
                job.progress = max(job.progress, min(1.0, progress))
            if message is not None:
                job.message = message
            job.processed = processed
            job.total = total
            job.report_id = report_id
            job.error = error
            job.revision += 1
            if job.status in TERMINAL:
                cleanup = threading.Timer(600, self._discard, args=(job.id,))
                cleanup.daemon = True
                cleanup.start()

    def cancel(self, job: BuildJob) -> None:
        job.cancel_event.set()
        self.update(job, status="running", stage="cancelling", message="Cancelling analysis safely")

    def subscribe(self, job: BuildJob) -> None:
        with self._lock:
            job.subscribers += 1
            job.had_subscriber = True
            if job.disconnect_timer:
                job.disconnect_timer.cancel()
                job.disconnect_timer = None

    def unsubscribe(self, job: BuildJob) -> None:
        with self._lock:
            job.subscribers = max(0, job.subscribers - 1)
            if job.subscribers == 0 and job.had_subscriber and job.status not in TERMINAL:
                job.disconnect_timer = threading.Timer(30, self._cancel_if_abandoned, args=(job.id,))
                job.disconnect_timer.daemon = True
                job.disconnect_timer.start()

    def _cancel_if_abandoned(self, build_id: str) -> None:
        with self._lock:
            job = self._jobs.get(build_id)
            if job and job.subscribers == 0 and job.status not in TERMINAL:
                job.cancel_event.set()

    def _discard(self, build_id: str) -> None:
        with self._lock:
            self._jobs.pop(build_id, None)

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()


report_build_jobs = InMemoryReportBuildJobStore()


def run_report_build_job(job: BuildJob) -> None:
    from backend.services.report_repository import ReportsRepository
    from backend.services.statistics_service import ReportBuildCancelled, build_report

    report_build_jobs.update(job, status="running", stage="cache", progress=0.01, message="Starting analysis")
    try:
        response = build_report(
            job.request,
            progress_callback=lambda stage, progress, message, processed, total: report_build_jobs.update(
                job,
                status="running",
                stage=stage,
                progress=progress,
                message=message,
                processed=processed,
                total=total,
            ),
            cancel_event=job.cancel_event,
        )
        if job.cancel_event.is_set():
            raise ReportBuildCancelled("Report build cancelled.")
        record = ReportsRepository().record_build(owner_id=job.owner_id, request=job.request, response=response)
        report_build_jobs.update(
            job,
            status="completed",
            stage="complete",
            progress=1.0,
            message="Report ready",
            report_id=record["id"],
        )
    except ReportBuildCancelled:
        report_build_jobs.update(job, status="cancelled", stage="cancelled", message="Report build cancelled")
    except Exception as exc:
        report_build_jobs.update(job, status="failed", stage="failed", message="Report build failed", error=str(exc))
