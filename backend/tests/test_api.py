import csv
import io
import re
import uuid
from datetime import datetime
from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import routes_process
from app.core.settings import settings
from app.db.models import AuditLog, TargetTeam
from app.db.session import SessionLocal
from app.main import app
from app.schemas.ticket import GEMINI_HANDLER_LABEL, HUMAN_HANDLER_LABEL
from app.services.report_service import REPORT_TITLE, TEAM_HEADERS, TICKET_HEADERS

HARDWARE_TEXT = "Need a second 27-inch monitor and USB hub."
NETWORK_TEXT = "GlobalProtect VPN failing to connect on macOS."
PERMISSION_TEXT = "Grant IAM read access to S3 bucket prod-logs."
SOFTWARE_TEXT = "How do I export Jira board metrics to Excel?"

VIEWER = {"X-User-Email": "viewer@company.com"}
AGENT = {"X-User-Email": "agent@company.com"}
ADMIN = {"X-User-Email": "admin@company.com"}

PRESETS = [
    pytest.param(HARDWARE_TEXT, "hardware_team", True, id="hardware-request"),
    pytest.param(NETWORK_TEXT, "network_team", False, id="network-issue"),
    pytest.param(PERMISSION_TEXT, "infra_team", True, id="permission-request"),
    pytest.param(SOFTWARE_TEXT, "software_team", False, id="software-how-to"),
]


def _tid() -> str:
    return f"TCK-{uuid.uuid4().hex[:12].upper()}"


def _body(text: str, ticket_id: Optional[str] = None, submitted_by: str = "user@company.com") -> dict[str, str]:
    return {"ticket_id": ticket_id or _tid(), "raw_text": text, "submitted_by": submitted_by}


def _submit(client: TestClient, text: str, ticket_id: Optional[str] = None, **kwargs: Any) -> dict[str, Any]:
    response = client.post("/api/process-ticket", json=_body(text, ticket_id), **kwargs)
    assert response.status_code == 200, response.text
    return response.json()


def _audit_rows(entity_id: str, action: str) -> list[AuditLog]:
    with SessionLocal() as session:
        return list(
            session.scalars(
                select(AuditLog).where(AuditLog.entity_id == entity_id, AuditLog.action == action)
            ).all()
        )


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None, f"timestamp {value!r} carries no timezone"
    return parsed


@pytest.fixture(scope="module")
def processed_tickets(client: TestClient) -> dict[str, str]:
    """Processes one ticket per PRD preset and returns their ticket ids keyed by label."""
    ids: dict[str, str] = {}
    for label, text in (
        ("hardware", HARDWARE_TEXT),
        ("network", NETWORK_TEXT),
        ("permission", PERMISSION_TEXT),
        ("software", SOFTWARE_TEXT),
    ):
        ticket_id = _tid()
        _submit(client, text, ticket_id)
        ids[label] = ticket_id
    return ids


# ---------------------------------------------------------------- POST /api/process-ticket


@pytest.mark.parametrize("text,team,requires_action", PRESETS)
def test_process_ticket_follows_the_prd_contract(
    client: TestClient, text: str, team: str, requires_action: bool
) -> None:
    ticket_id = _tid()
    response = client.post("/api/process-ticket", json=_body(text, ticket_id))

    assert response.status_code == 200
    assert response.headers["x-request-id"]
    data = response.json()
    assert set(data) == {"ticket_id", "routing", "resolution"}
    assert data["ticket_id"] == ticket_id

    routing = data["routing"]
    assert set(routing) == {"team", "requires_action", "jev_confidence", "jev_execution_time_ms"}
    assert routing["team"] == team
    assert routing["requires_action"] is requires_action
    assert 0.0 <= routing["jev_confidence"] <= 1.0
    assert isinstance(routing["jev_execution_time_ms"], int)
    assert routing["jev_execution_time_ms"] >= 1

    resolution = data["resolution"]
    assert set(resolution) == {"handled_by", "status", "response_text", "gemini_execution_time_ms"}
    if requires_action:
        assert resolution["status"] == "ASSIGNED_TO_HUMAN"
        assert resolution["handled_by"] == HUMAN_HANDLER_LABEL
        assert resolution["gemini_execution_time_ms"] is None
        assert resolution["response_text"].startswith("Assigned to ")
    else:
        assert resolution["status"] == "AUTO_RESOLVED"
        assert resolution["handled_by"] == GEMINI_HANDLER_LABEL
        assert isinstance(resolution["gemini_execution_time_ms"], int)
        assert resolution["gemini_execution_time_ms"] >= 1
        assert re.match(r"^1\. ", resolution["response_text"])
        assert "\n2. " in resolution["response_text"]


def test_duplicate_ticket_id_is_rejected_with_409(client: TestClient) -> None:
    ticket_id = _tid()
    _submit(client, HARDWARE_TEXT, ticket_id)

    response = client.post("/api/process-ticket", json=_body(NETWORK_TEXT, ticket_id))

    assert response.status_code == 409
    assert ticket_id in response.json()["detail"]
    assert len(_audit_rows(ticket_id, "ticket.duplicate_rejected")) == 1
    assert len(_audit_rows(ticket_id, "ticket.processed")) == 1


_BASE = _body("A valid ticket description", "TCK-VALID-1")

INVALID_BODIES = [
    pytest.param({}, id="empty-object"),
    pytest.param({key: value for key, value in _BASE.items() if key != "ticket_id"}, id="missing-ticket-id"),
    pytest.param({**_BASE, "ticket_id": "bad id"}, id="malformed-ticket-id"),
    pytest.param({**_BASE, "raw_text": "hi"}, id="text-too-short"),
    pytest.param({**_BASE, "raw_text": "   "}, id="blank-text"),
    pytest.param({**_BASE, "raw_text": "x" * 5001}, id="text-too-long"),
    pytest.param({**_BASE, "submitted_by": "not-an-email"}, id="bad-email"),
    pytest.param({**_BASE, "priority": "high"}, id="unknown-field"),
]


@pytest.mark.parametrize("payload", INVALID_BODIES)
def test_invalid_bodies_are_rejected_with_422(client: TestClient, payload: dict[str, Any]) -> None:
    response = client.post("/api/process-ticket", json=payload)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_non_json_body_is_rejected_with_422(client: TestClient) -> None:
    response = client.post(
        "/api/process-ticket", content="not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422


def test_processing_is_audited_without_the_ticket_text(client: TestClient) -> None:
    ticket_id = _tid()
    response = client.post(
        "/api/process-ticket",
        json=_body(HARDWARE_TEXT, ticket_id),
        headers={"X-Request-ID": "audit-req-0001"},
    )
    assert response.status_code == 200

    rows = _audit_rows(ticket_id, "ticket.processed")
    assert len(rows) == 1
    row = rows[0]
    assert row.actor == "anonymous"
    assert row.role == "anonymous"
    assert row.request_id == "audit-req-0001"
    assert row.details["target_team"] == "hardware_team"
    assert row.details["status"] == "ASSIGNED_TO_HUMAN"
    assert row.details["gemini_engine"] == "bypassed"
    assert row.details["jev_latency_ms"] >= 1
    assert "raw_text" not in row.details
    assert HARDWARE_TEXT not in str(row.details)


def test_rbac_can_be_enforced_on_process_ticket(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ENFORCE_RBAC_ON_PROCESS_TICKET", True)

    anonymous = client.post("/api/process-ticket", json=_body(HARDWARE_TEXT))
    viewer = client.post("/api/process-ticket", json=_body(HARDWARE_TEXT), headers=VIEWER)
    ticket_id = _tid()
    agent = client.post("/api/process-ticket", json=_body(HARDWARE_TEXT, ticket_id), headers=AGENT)

    assert anonymous.status_code == 401
    assert viewer.status_code == 403
    assert "tickets:process" in viewer.json()["detail"]
    assert agent.status_code == 200
    row = _audit_rows(ticket_id, "ticket.processed")[0]
    assert row.actor == "agent@company.com"
    assert row.role == "agent"


# ---------------------------------------------------------------- RBAC on read endpoints


@pytest.mark.parametrize("path", ["/api/tickets", "/api/analytics", "/api/reports", "/api/tickets/TCK-1/trace"])
def test_protected_endpoints_require_a_known_user(client: TestClient, path: str) -> None:
    missing = client.get(path)
    unknown = client.get(path, headers={"X-User-Email": "stranger@example.com"})

    assert missing.status_code == 401
    assert unknown.status_code == 401


def test_user_lookup_is_case_insensitive(client: TestClient) -> None:
    response = client.get("/api/tickets", headers={"X-User-Email": "VIEWER@Company.com"})
    assert response.status_code == 200


# ---------------------------------------------------------------- GET /api/tickets


def test_list_tickets_returns_the_paginated_envelope(
    client: TestClient, processed_tickets: dict[str, str]
) -> None:
    response = client.get("/api/tickets", headers=VIEWER)

    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"items", "total", "page", "page_size"}
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total"] >= 4
    assert len(data["items"]) <= 20


def test_list_tickets_orders_newest_first_with_utc_timestamps(
    client: TestClient, processed_tickets: dict[str, str]
) -> None:
    items = client.get("/api/tickets", headers=VIEWER, params={"page_size": 50}).json()["items"]

    stamps = [_parse_utc(item["created_at"]) for item in items]
    assert stamps == sorted(stamps, reverse=True)


def test_search_by_ticket_id_returns_the_persisted_ticket(
    client: TestClient, processed_tickets: dict[str, str]
) -> None:
    ticket_id = processed_tickets["hardware"]
    data = client.get("/api/tickets", headers=VIEWER, params={"search": ticket_id}).json()

    assert data["total"] == 1
    item = data["items"][0]
    assert item["ticket_id"] == ticket_id
    assert item["raw_text"] == HARDWARE_TEXT
    assert item["submitted_by"] == "user@company.com"
    assert item["target_team"] == "hardware_team"
    assert item["requires_human_action"] is True
    assert item["status"] == "ASSIGNED_TO_HUMAN"
    assert item["handled_by"] == HUMAN_HANDLER_LABEL
    assert item["assigned_queue"] == "Hardware Procurement Queue"
    assert item["gemini_execution_time_ms"] is None


def test_search_treats_like_wildcards_literally(client: TestClient, processed_tickets: dict[str, str]) -> None:
    data = client.get("/api/tickets", headers=VIEWER, params={"search": "%"}).json()
    assert data["total"] == 0


def test_filters_narrow_the_result(client: TestClient, processed_tickets: dict[str, str]) -> None:
    by_team = client.get("/api/tickets", headers=VIEWER, params={"team": "network_team", "page_size": 100}).json()
    by_status = client.get(
        "/api/tickets", headers=VIEWER, params={"status": "ASSIGNED_TO_HUMAN", "page_size": 100}
    ).json()
    by_flag = client.get(
        "/api/tickets", headers=VIEWER, params={"requires_human_action": "false", "page_size": 100}
    ).json()

    assert by_team["items"] and all(item["target_team"] == "network_team" for item in by_team["items"])
    assert by_status["items"] and all(
        item["status"] == "ASSIGNED_TO_HUMAN" and item["requires_human_action"] is True
        for item in by_status["items"]
    )
    assert by_flag["items"] and all(item["requires_human_action"] is False for item in by_flag["items"])


def test_pagination_pages_do_not_overlap(client: TestClient, processed_tickets: dict[str, str]) -> None:
    first = client.get("/api/tickets", headers=VIEWER, params={"page": 1, "page_size": 2}).json()
    second = client.get("/api/tickets", headers=VIEWER, params={"page": 2, "page_size": 2}).json()

    assert len(first["items"]) == 2
    assert len(second["items"]) == 2
    first_ids = {item["ticket_id"] for item in first["items"]}
    second_ids = {item["ticket_id"] for item in second["items"]}
    assert first_ids.isdisjoint(second_ids)
    assert first["total"] == second["total"]


@pytest.mark.parametrize(
    "param,value",
    [
        ("page", 0),
        ("page_size", 0),
        ("page_size", 101),
        ("team", "bogus_team"),
        ("status", "BOGUS"),
        ("search", "x" * 101),
    ],
)
def test_list_parameters_are_validated(client: TestClient, param: str, value: Any) -> None:
    response = client.get("/api/tickets", headers=VIEWER, params={param: value})
    assert response.status_code == 422


# ---------------------------------------------------------------- GET /api/tickets/{id}/trace


def test_trace_of_a_human_assigned_ticket_shows_the_savings(
    client: TestClient, processed_tickets: dict[str, str]
) -> None:
    response = client.get(f"/api/tickets/{processed_tickets['hardware']}/trace", headers=VIEWER)

    assert response.status_code == 200
    trace = response.json()
    assert trace["ticket_id"] == processed_tickets["hardware"]
    assert trace["jev_engine"] == "simulator"
    assert trace["gemini_engine"] == "bypassed"
    assert trace["gemini_bypassed"] is True
    assert trace["gemini_execution_time_ms"] is None
    assert trace["assigned_queue"] == "Hardware Procurement Queue"
    assert trace["time_saved_ms"] == settings.BASELINE_GEMINI_LATENCY_MS
    assert trace["cost_saved_usd"] == pytest.approx(settings.BASELINE_GEMINI_COST_USD)
    assert trace["jev_threshold_ms"] == settings.JEV_LATENCY_THRESHOLD_MS
    assert trace["jev_within_threshold"] == (trace["jev_latency_ms"] < settings.JEV_LATENCY_THRESHOLD_MS)
    assert trace["rag_sources"] is None
    assert trace["decision_criteria"]
    assert any("Gemini bypassed" in line for line in trace["decision_criteria"])
    _parse_utc(trace["created_at"])


def test_trace_of_an_auto_resolved_ticket_has_no_savings(
    client: TestClient, processed_tickets: dict[str, str]
) -> None:
    trace = client.get(f"/api/tickets/{processed_tickets['network']}/trace", headers=VIEWER).json()

    assert trace["gemini_bypassed"] is False
    assert trace["gemini_engine"] == "simulator"
    assert isinstance(trace["gemini_execution_time_ms"], int)
    assert trace["assigned_queue"] is None
    assert trace["time_saved_ms"] == 0
    assert trace["cost_saved_usd"] == 0
    assert trace["rag_sources"] is None or isinstance(trace["rag_sources"], list)
    assert any("deterministic resolution simulator" in line for line in trace["decision_criteria"])


def test_trace_of_an_unknown_ticket_is_404(client: TestClient) -> None:
    response = client.get("/api/tickets/TCK-DOESNOTEXIST/trace", headers=VIEWER)

    assert response.status_code == 404
    assert "TCK-DOESNOTEXIST" in response.json()["detail"]


def test_trace_rejects_a_malformed_ticket_id(client: TestClient) -> None:
    response = client.get("/api/tickets/-bad/trace", headers=VIEWER)
    assert response.status_code == 422


# ---------------------------------------------------------------- GET /api/analytics


def _summary(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/api/analytics", headers=VIEWER, params=params)
    assert response.status_code == 200, response.text
    return response.json()["summary"]


def test_analytics_payload_is_consistent(client: TestClient, processed_tickets: dict[str, str]) -> None:
    response = client.get("/api/analytics", headers=VIEWER)

    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"generated_at", "window_days", "summary", "team_breakdown", "latency_series", "savings_series"}
    summary = data["summary"]

    assert data["window_days"] is None
    assert summary["total_tickets"] >= 4
    assert summary["auto_resolved_count"] + summary["assigned_to_human_count"] == summary["total_tickets"]
    assert summary["gemini_bypass_rate"] == pytest.approx(
        summary["assigned_to_human_count"] / summary["total_tickets"], abs=1e-4
    )
    assert summary["jev_threshold_ms"] == settings.JEV_LATENCY_THRESHOLD_MS
    assert summary["p50_jev_latency_ms"] <= summary["p95_jev_latency_ms"]
    assert 0.0 <= summary["jev_within_threshold_rate"] <= 1.0
    assert summary["avg_gemini_latency_ms"] is not None

    assert [item["team"] for item in data["team_breakdown"]] == [team.value for team in TargetTeam]
    assert sum(item["total"] for item in data["team_breakdown"]) == summary["total_tickets"]
    for item in data["team_breakdown"]:
        assert item["total"] == item["auto_resolved"] + item["assigned_to_human"]

    assert 0 < len(data["latency_series"]) <= 50
    assert data["savings_series"][-1]["cumulative_time_saved_ms"] == summary["total_time_saved_ms"]
    assert data["savings_series"][-1]["cumulative_cost_saved_usd"] == pytest.approx(
        summary["total_cost_saved_usd"], abs=1e-6
    )


def test_analytics_reflects_new_tickets(client: TestClient, processed_tickets: dict[str, str]) -> None:
    before = _summary(client)

    _submit(client, HARDWARE_TEXT)
    _submit(client, PERMISSION_TEXT)
    _submit(client, NETWORK_TEXT)
    after = _summary(client)

    assert after["total_tickets"] - before["total_tickets"] == 3
    assert after["assigned_to_human_count"] - before["assigned_to_human_count"] == 2
    assert after["auto_resolved_count"] - before["auto_resolved_count"] == 1
    assert after["total_time_saved_ms"] - before["total_time_saved_ms"] == 2 * settings.BASELINE_GEMINI_LATENCY_MS
    assert after["total_cost_saved_usd"] - before["total_cost_saved_usd"] == pytest.approx(
        2 * settings.BASELINE_GEMINI_COST_USD, abs=1e-6
    )


def test_analytics_window_and_series_limits(client: TestClient, processed_tickets: dict[str, str]) -> None:
    windowed = client.get("/api/analytics", headers=VIEWER, params={"window_days": 1, "series_limit": 1}).json()

    assert windowed["window_days"] == 1
    assert len(windowed["latency_series"]) == 1
    assert len(windowed["savings_series"]) == 1
    assert windowed["summary"]["total_tickets"] == _summary(client)["total_tickets"]


@pytest.mark.parametrize("params", [{"window_days": 0}, {"window_days": 366}, {"series_limit": 0}, {"series_limit": 501}])
def test_analytics_parameters_are_validated(client: TestClient, params: dict[str, int]) -> None:
    response = client.get("/api/analytics", headers=VIEWER, params=params)
    assert response.status_code == 422


# ---------------------------------------------------------------- GET /api/reports


def test_viewers_cannot_export_reports(client: TestClient) -> None:
    response = client.get("/api/reports", headers=VIEWER)

    assert response.status_code == 403
    assert "reports:export" in response.json()["detail"]


def test_csv_report_contains_the_summary_and_tickets(
    client: TestClient, processed_tickets: dict[str, str]
) -> None:
    response = client.get("/api/reports", headers=AGENT, params={"format": "csv"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["cache-control"] == "no-store"
    disposition = response.headers["content-disposition"]
    match = re.fullmatch(r'attachment; filename="(ticket-routing-report-\d{8}-\d{6}\.csv)"', disposition)
    assert match is not None

    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[0] == [REPORT_TITLE]
    assert ["Metric", "Value"] in rows
    assert TEAM_HEADERS in rows
    assert TICKET_HEADERS in rows
    total_row = next(row for row in rows if row and row[0] == "Total tickets")
    assert int(total_row[1]) >= 4
    assert any(row and row[0] == processed_tickets["hardware"] for row in rows)

    audit = _audit_rows(match.group(1), "report.exported")
    assert len(audit) == 1
    assert audit[0].actor == "agent@company.com"
    assert audit[0].details["format"] == "csv"


def test_csv_report_neutralizes_spreadsheet_formulas(client: TestClient) -> None:
    ticket_id = _tid()
    response = client.post(
        "/api/process-ticket",
        json=_body(HARDWARE_TEXT, ticket_id, submitted_by="=1+1@evil.com"),
    )
    assert response.status_code == 200

    report = client.get("/api/reports", headers=ADMIN, params={"format": "csv"})
    rows = list(csv.reader(io.StringIO(report.content.decode("utf-8-sig"))))
    ticket_row = next(row for row in rows if row and row[0] == ticket_id)

    assert ticket_row[1] == "'=1+1@evil.com"


def test_pdf_report_is_a_pdf_document(client: TestClient, processed_tickets: dict[str, str]) -> None:
    response = client.get("/api/reports", headers=ADMIN, params={"format": "pdf"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert re.fullmatch(
        r'attachment; filename="ticket-routing-report-\d{8}-\d{6}\.pdf"',
        response.headers["content-disposition"],
    )
    assert response.content.startswith(b"%PDF-")


def test_unknown_report_format_is_rejected(client: TestClient) -> None:
    response = client.get("/api/reports", headers=AGENT, params={"format": "xml"})
    assert response.status_code == 422


# ---------------------------------------------------------------- GET /api/health


def test_health_reports_simulated_engines_without_authentication(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert set(data) == {
        "status",
        "environment",
        "database_ok",
        "jev_engine_mode",
        "gemini_engine_mode",
        "rag_enabled",
        "jev_threshold_ms",
    }
    assert data["status"] == "ok"
    assert data["database_ok"] is True
    assert data["jev_engine_mode"] == "simulated"
    assert data["gemini_engine_mode"] == "simulated"
    assert isinstance(data["rag_enabled"], bool)
    assert data["jev_threshold_ms"] == settings.JEV_LATENCY_THRESHOLD_MS


# ---------------------------------------------------------------- request ids, CORS and error handling


def test_valid_inbound_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/api/health", headers={"X-Request-ID": "unit-test-req-12345"})
    assert response.headers["x-request-id"] == "unit-test-req-12345"


def test_unsafe_or_missing_request_ids_are_replaced(client: TestClient) -> None:
    unsafe = client.get("/api/health", headers={"X-Request-ID": "x"})
    missing = client.get("/api/health")

    assert unsafe.headers["x-request-id"] != "x"
    assert re.fullmatch(r"[0-9a-f]{32}", unsafe.headers["x-request-id"])
    assert re.fullmatch(r"[0-9a-f]{32}", missing.headers["x-request-id"])


def test_cors_preflight_allows_the_dashboard_origin(client: TestClient) -> None:
    response = client.options(
        "/api/process-ticket",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-user-email",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "x-user-email" in allowed
    assert "content-type" in allowed


def test_cors_preflight_rejects_other_origins(client: TestClient) -> None:
    response = client.options(
        "/api/process-ticket",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_cors_exposes_the_download_headers(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Origin": "http://localhost:5173"})

    exposed = response.headers["access-control-expose-headers"].lower()
    assert "content-disposition" in exposed
    assert "x-request-id" in exposed


def test_unhandled_errors_return_a_generic_500(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("database password is hunter2")

    monkeypatch.setattr(routes_process, "process_ticket", boom)
    quiet_client = TestClient(app, raise_server_exceptions=False)

    response = quiet_client.post(
        "/api/process-ticket",
        json=_body(HARDWARE_TEXT),
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Internal server error"
    assert "hunter2" not in response.text
    assert body["request_id"] == response.headers["x-request-id"]
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
