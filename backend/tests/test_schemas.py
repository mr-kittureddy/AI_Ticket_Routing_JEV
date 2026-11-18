from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.ticket import (
    GEMINI_HANDLER_LABEL,
    HUMAN_HANDLER_LABEL,
    JEVDecision,
    ProcessTicketResponse,
    TicketInput,
)

VALID_TICKET = {
    "ticket_id": "TCK-8821",
    "raw_text": "My GlobalProtect VPN keeps dropping every 10 minutes when connected to home Wi-Fi.",
    "submitted_by": "user@company.com",
}

PRD_RESPONSE_EXAMPLE = {
    "ticket_id": "TCK-8821",
    "routing": {
        "team": "network_team",
        "requires_action": False,
        "jev_confidence": 0.98,
        "jev_execution_time_ms": 42,
    },
    "resolution": {
        "handled_by": "Gemini 2.5 Flash",
        "status": "AUTO_RESOLVED",
        "response_text": "1. Open GlobalProtect Settings...\n2. Clear DNS Cache...",
        "gemini_execution_time_ms": 1120,
    },
}


def _response(requires_action: bool, **resolution_overrides: Any) -> dict[str, Any]:
    """Builds a §4.3 payload whose resolution matches the routing flag, with optional field overrides."""
    if requires_action:
        resolution: dict[str, Any] = {
            "handled_by": HUMAN_HANDLER_LABEL,
            "status": "ASSIGNED_TO_HUMAN",
            "response_text": "Assigned to Hardware Procurement Queue.",
            "gemini_execution_time_ms": None,
        }
        team = "hardware_team"
    else:
        resolution = dict(PRD_RESPONSE_EXAMPLE["resolution"])
        team = "network_team"
    resolution.update(resolution_overrides)
    return {
        "ticket_id": "TCK-8821",
        "routing": {
            "team": team,
            "requires_action": requires_action,
            "jev_confidence": 0.98,
            "jev_execution_time_ms": 42,
        },
        "resolution": resolution,
    }


def test_ticket_input_accepts_the_prd_example() -> None:
    ticket = TicketInput(**VALID_TICKET)
    assert ticket.ticket_id == "TCK-8821"
    assert ticket.submitted_by == "user@company.com"


def test_ticket_input_strips_surrounding_whitespace() -> None:
    ticket = TicketInput(**{**VALID_TICKET, "raw_text": "   Printer is offline   "})
    assert ticket.raw_text == "Printer is offline"


@pytest.mark.parametrize(
    "field,value",
    [
        ("ticket_id", "bad id"),
        ("ticket_id", "-leading-dash"),
        ("ticket_id", ""),
        ("ticket_id", "A" * 65),
        ("ticket_id", "TCK/1"),
        ("raw_text", "hi"),
        ("raw_text", "     "),
        ("raw_text", "x" * 5001),
        ("submitted_by", "not-an-email"),
        ("submitted_by", "a@b"),
        ("submitted_by", "a b@company.com"),
        ("submitted_by", "x" * 321 + "@company.com"),
    ],
)
def test_ticket_input_rejects_invalid_values(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        TicketInput(**{**VALID_TICKET, field: value})


@pytest.mark.parametrize("field", ["ticket_id", "raw_text", "submitted_by"])
def test_ticket_input_requires_every_field(field: str) -> None:
    payload = {key: value for key, value in VALID_TICKET.items() if key != field}
    with pytest.raises(ValidationError):
        TicketInput(**payload)


def test_ticket_input_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        TicketInput(**{**VALID_TICKET, "priority": "high"})


def test_jev_decision_matches_the_prd_example() -> None:
    decision = JEVDecision(
        target_team="network_team",
        requires_human_action=False,
        confidence_score=0.98,
        jev_latency_ms=42,
    )
    assert decision.model_dump(mode="json") == {
        "target_team": "network_team",
        "requires_human_action": False,
        "confidence_score": 0.98,
        "jev_latency_ms": 42,
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"confidence_score": 1.01},
        {"confidence_score": -0.1},
        {"jev_latency_ms": -1},
        {"target_team": "finance_team"},
    ],
)
def test_jev_decision_rejects_invalid_values(overrides: dict[str, Any]) -> None:
    payload = {
        "target_team": "network_team",
        "requires_human_action": False,
        "confidence_score": 0.9,
        "jev_latency_ms": 10,
        **overrides,
    }
    with pytest.raises(ValidationError):
        JEVDecision(**payload)


def test_process_ticket_response_serializes_exactly_as_the_prd_contract() -> None:
    response = ProcessTicketResponse(**PRD_RESPONSE_EXAMPLE)
    assert response.model_dump(mode="json") == PRD_RESPONSE_EXAMPLE


def test_human_assignment_response_is_valid() -> None:
    response = ProcessTicketResponse(**_response(True))
    assert response.resolution.status.value == "ASSIGNED_TO_HUMAN"
    assert response.resolution.gemini_execution_time_ms is None


@pytest.mark.parametrize(
    "requires_action,overrides",
    [
        pytest.param(True, {"status": "AUTO_RESOLVED"}, id="human-flag-but-auto-resolved"),
        pytest.param(True, {"gemini_execution_time_ms": 100}, id="human-flag-but-gemini-time-present"),
        pytest.param(True, {"response_text": None}, id="human-flag-without-notice"),
        pytest.param(True, {"response_text": ""}, id="human-flag-with-empty-notice"),
        pytest.param(False, {"status": "ASSIGNED_TO_HUMAN"}, id="no-flag-but-assigned-to-human"),
        pytest.param(False, {"gemini_execution_time_ms": None}, id="no-flag-without-gemini-time"),
        pytest.param(False, {"response_text": None}, id="no-flag-without-resolution-text"),
    ],
)
def test_bypass_rule_is_enforced_by_the_schema(requires_action: bool, overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ProcessTicketResponse(**_response(requires_action, **overrides))


def test_process_ticket_response_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ProcessTicketResponse(**{**PRD_RESPONSE_EXAMPLE, "extra": "field"})


def test_handler_labels_match_the_prd() -> None:
    assert GEMINI_HANDLER_LABEL == "Gemini 2.5 Flash"
    assert HUMAN_HANDLER_LABEL == "Human Representative"
