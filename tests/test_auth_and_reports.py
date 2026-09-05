from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend import main as api_main
from backend.models import ReportBuildRequest
from backend.services.auth_service import AuthRepository, InvalidSession, InvalidVerification
from backend.services.database_service import DatabaseCorruptionError, JsonDatabase
from backend.services.report_repository import ReportNotFound, ReportsRepository
from backend.services.report_build_job_service import BuildJobNotFound, InMemoryReportBuildJobStore
from backend.settings import settings


def test_json_database_is_versioned_atomic_and_fails_closed(tmp_path):
    path = tmp_path / "app_db.json"
    database = JsonDatabase(path)
    database.transaction(lambda data: data["audit_events"].append({"id": "one"}))

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["schema_version"] == 1
    assert stored["audit_events"] == [{"id": "one"}]
    assert not list(tmp_path.glob("*.tmp"))

    path.write_text("not json", encoding="utf-8")
    with pytest.raises(DatabaseCorruptionError):
        database.read()


def test_registration_verification_login_and_revocable_jwt(tmp_path):
    repository = AuthRepository(JsonDatabase(tmp_path / "app_db.json"))
    registration, verification_token, _email = repository.prepare_registration(
        "Member@Example.com",
        "correct horse battery staple",
    )

    assert repository.registration_status(registration.registration_id, registration.socket_token) == "pending"
    stored = repository.database.read()
    assert stored["users"][0]["email"] == "member@example.com"
    assert stored["users"][0]["password_hash"] != "correct horse battery staple"
    assert stored["email_verifications"][0]["token_digest"] != verification_token

    verified = repository.verify_email(verification_token)
    assert verified.email == "member@example.com"
    assert repository.verify_email(verification_token).id == verified.id
    assert [event["kind"] for event in repository.database.read()["audit_events"]].count("auth.email_verified") == 1
    assert repository.registration_status(registration.registration_id, registration.socket_token) == "verified"

    user, _stored = repository.authenticate("member@example.com", "correct horse battery staple")
    encoded, csrf = repository.create_session(user.id)
    resolved, session = repository.resolve_session(encoded)
    assert resolved.id == user.id
    repository.validate_csrf(session, csrf, csrf)
    with pytest.raises(InvalidSession, match="CSRF"):
        repository.validate_csrf(session, csrf, "wrong")

    repository.revoke_session(session["id"])
    with pytest.raises(InvalidSession):
        repository.resolve_session(encoded)


def test_superseded_pending_verification_never_activates(tmp_path):
    repository = AuthRepository(JsonDatabase(tmp_path / "app_db.json"))
    first, first_token, _ = repository.prepare_registration("member@example.com", "correct horse battery staple")
    second, second_token, _ = repository.prepare_registration("member@example.com", "a different secure password")

    with pytest.raises(InvalidVerification):
        repository.verify_email(first_token)
    assert repository.registration_status(first.registration_id, first.socket_token) == "expired"
    verified = repository.verify_email(second_token)
    assert verified.email == "member@example.com"
    assert repository.registration_status(second.registration_id, second.socket_token) == "verified"


class FakeArtifactCache:
    def __init__(self):
        self.deleted: list[str] = []

    def get(self, _cache_hash):
        return None

    def delete(self, cache_hash):
        self.deleted.append(cache_hash)


def report_request(username: str = "Hikaru") -> ReportBuildRequest:
    return ReportBuildRequest(
        username=username,
        hparams={},
        max_games=20,
        engine_depth=10,
        use_engine=True,
    )


def test_ephemeral_build_jobs_are_owner_bound_monotonic_and_cancellable():
    store = InMemoryReportBuildJobStore()
    accepted, job = store.create("owner-one", report_request())
    assert store.authorize_socket(accepted.build_id, "owner-one", accepted.socket_token) is job
    with pytest.raises(BuildJobNotFound):
        store.get(accepted.build_id, "owner-two")
    with pytest.raises(BuildJobNotFound):
        store.authorize_socket(accepted.build_id, "owner-one", "wrong")

    store.update(job, status="running", stage="enriching_games", progress=.6, message="Game 2", processed=2, total=4)
    store.update(job, progress=.4, message="Still game 2")
    assert store.snapshot(job).progress == .6
    store.cancel(job)
    assert job.cancel_event.is_set()
    assert store.snapshot(job).stage == "cancelling"


def test_reports_are_owner_bound_grouped_and_manually_saved(tmp_path):
    database = JsonDatabase(tmp_path / "app_db.json")
    auth = AuthRepository(database)
    registration, token, _email = auth.prepare_registration("one@example.com", "correct horse battery staple")
    owner = auth.verify_email(token)
    registration_two, token_two, _email_two = auth.prepare_registration("two@example.com", "correct horse battery staple")
    other = auth.verify_email(token_two)
    cache = FakeArtifactCache()
    reports = ReportsRepository(database, cache)  # type: ignore[arg-type]
    response = SimpleNamespace(cache_hash="hash-one", report=SimpleNamespace(metadata={"games_selected": 20}))

    first = reports.record_build(owner_id=owner.id, request=report_request("Hikaru"), response=response)
    repeated = reports.record_build(owner_id=owner.id, request=report_request("hikaru"), response=response)
    assert first["id"] == repeated["id"]
    assert reports.dashboard(owner.id).report_count == 0

    saved = reports.save(owner.id, first["id"], "Candidates preparation")
    assert saved.title == "Candidates preparation"
    dashboard = reports.dashboard(owner.id)
    assert dashboard.player_count == 1
    assert dashboard.players[0].username.lower() == "hikaru"
    assert reports.list_player(owner.id, "HIKARU")[0].id == first["id"]

    with pytest.raises(ReportNotFound):
        reports.get_record(other.id, first["id"])

    reports.delete(owner.id, first["id"])
    assert cache.deleted == ["hash-one"]


def test_auth_http_cookie_csrf_and_verified_websocket(monkeypatch, tmp_path):
    previous_path = settings.app_database_path
    object.__setattr__(settings, "app_database_path", tmp_path / "app_db.json")
    sent: dict[str, str] = {}

    async def fake_send(*, recipient: str, token: str):
        sent.update(recipient=recipient, token=token)

    monkeypatch.setattr(api_main, "send_verification_email", fake_send)
    client = TestClient(api_main.app)
    try:
        assert client.get("/api/dashboard").status_code == 401
        registration = client.post(
            "/api/auth/register",
            json={"email": "member@example.com", "password": "correct horse battery staple"},
        )
        assert registration.status_code == 202
        registration_body = registration.json()
        assert sent["recipient"] == "member@example.com"

        verified = client.post("/api/auth/verify-email", json={"token": sent["token"]})
        assert verified.status_code == 200
        assert client.post("/api/auth/verify-email", json={"token": sent["token"]}).status_code == 200
        with client.websocket_connect(
            f"/api/auth/registrations/{registration_body['registration_id']}/status"
            f"?token={registration_body['socket_token']}"
        ) as websocket:
            assert websocket.receive_json() == {"status": "verified"}

        signed_in = client.post(
            "/api/auth/login",
            json={"email": "member@example.com", "password": "correct horse battery staple"},
        )
        assert signed_in.status_code == 200
        set_cookie = " ".join(signed_in.headers.get_list("set-cookie")).lower()
        assert "httponly" in set_cookie
        assert "samesite=lax" in set_cookie
        assert client.cookies.get(settings.auth_cookie_name)
        csrf = client.cookies.get(settings.csrf_cookie_name)
        assert csrf
        assert client.get("/api/auth/me").status_code == 200
        assert client.get("/api/dashboard").json()["report_count"] == 0
        assert client.get("/api/reports/missing").status_code == 404
        assert client.post("/api/auth/logout").status_code == 403
        assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
        assert client.get("/api/auth/me").status_code == 401
    finally:
        client.close()
        object.__setattr__(settings, "app_database_path", previous_path)
