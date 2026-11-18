from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.models import ResolutionStatus, TargetTeam

TICKET_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$"
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

GEMINI_HANDLER_LABEL = "Gemini 2.5 Flash"
HUMAN_HANDLER_LABEL = "Human Representative"


class TicketInput(BaseModel):
    """PRD §4.1 — Ticket Input Schema."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "ticket_id": "TCK-8821",
                "raw_text": "My GlobalProtect VPN keeps dropping every 10 minutes when connected to home Wi-Fi.",
                "submitted_by": "user@company.com",
            }
        },
    )

    ticket_id: str = Field(..., pattern=TICKET_ID_PATTERN, description="Unique ticket identifier, e.g. TCK-8821")
    raw_text: str = Field(..., min_length=3, max_length=5000, description="Raw ticket text as typed by the requester")
    submitted_by: str = Field(..., max_length=320, pattern=EMAIL_PATTERN, description="Requester email address")


class JEVDecision(BaseModel):
    """PRD §4.2 — JEV Decision Output Schema."""

    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    target_team: TargetTeam
    requires_human_action: bool = Field(
        ..., description="True if purchase, physical install, or admin privilege is required"
    )
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    jev_latency_ms: int = Field(..., ge=0)


class RoutingInfo(BaseModel):
    """PRD §4.3 — the `routing` block of the pipeline final response."""

    model_config = ConfigDict(extra="forbid")

    team: TargetTeam
    requires_action: bool
    jev_confidence: float = Field(..., ge=0.0, le=1.0)
    jev_execution_time_ms: int = Field(..., ge=0)


class ResolutionInfo(BaseModel):
    """PRD §4.3 — the `resolution` block of the pipeline final response."""

    model_config = ConfigDict(extra="forbid")

    handled_by: str
    status: ResolutionStatus
    response_text: Optional[str] = Field(
        default=None,
        description="Gemini step-by-step resolution when AUTO_RESOLVED; human assignment notice when ASSIGNED_TO_HUMAN",
    )
    gemini_execution_time_ms: Optional[int] = Field(
        default=None,
        ge=0,
        description="Gemini drafting time in ms; null when Gemini was bypassed",
    )


class ProcessTicketResponse(BaseModel):
    """PRD §4.3 — Pipeline Final Response Schema returned by POST /api/process-ticket."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "ticket_id": "TCK-8821",
                "routing": {
                    "team": "network_team",
                    "requires_action": False,
                    "jev_confidence": 0.98,
                    "jev_execution_time_ms": 42,
                },
                "resolution": {
                    "handled_by": GEMINI_HANDLER_LABEL,
                    "status": "AUTO_RESOLVED",
                    "response_text": "1. Open GlobalProtect Settings...\n2. Clear DNS Cache...",
                    "gemini_execution_time_ms": 1120,
                },
            }
        },
    )

    ticket_id: str
    routing: RoutingInfo
    resolution: ResolutionInfo

    @model_validator(mode="after")
    def enforce_human_action_bypass(self) -> "ProcessTicketResponse":
        """Hardware/Admin requests requiring human action must bypass Gemini; all others must be auto-resolved."""
        status = self.resolution.status
        if self.routing.requires_action:
            if status != ResolutionStatus.ASSIGNED_TO_HUMAN:
                raise ValueError("requires_action=True must produce status ASSIGNED_TO_HUMAN")
            if self.resolution.gemini_execution_time_ms is not None:
                raise ValueError("gemini_execution_time_ms must be null when Gemini is bypassed")
            if not self.resolution.response_text:
                raise ValueError("response_text must contain the human assignment notice")
        else:
            if status != ResolutionStatus.AUTO_RESOLVED:
                raise ValueError("requires_action=False must produce status AUTO_RESOLVED")
            if self.resolution.gemini_execution_time_ms is None:
                raise ValueError("gemini_execution_time_ms is required when Gemini resolves the ticket")
            if not self.resolution.response_text:
                raise ValueError("response_text is required when Gemini resolves the ticket")
        return self


class TicketTrace(BaseModel):
    """Additive read-only metadata for GET /api/tickets/{ticket_id}/trace (PRD §1 criteria and savings badge)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    ticket_id: str
    jev_engine: str
    gemini_engine: str
    jev_latency_ms: int
    jev_threshold_ms: int
    jev_within_threshold: bool
    gemini_bypassed: bool
    gemini_execution_time_ms: Optional[int] = None
    decision_criteria: list[str]
    assigned_queue: Optional[str] = None
    time_saved_ms: int
    cost_saved_usd: float
    rag_sources: Optional[list[str]] = None
    created_at: datetime


class TicketRecord(BaseModel):
    """A persisted ticket row returned by GET /api/tickets."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    ticket_id: str
    raw_text: str
    submitted_by: str
    target_team: TargetTeam
    requires_human_action: bool
    confidence_score: float
    jev_latency_ms: int
    status: ResolutionStatus
    handled_by: str
    assigned_queue: Optional[str] = None
    response_text: Optional[str] = None
    gemini_execution_time_ms: Optional[int] = None
    created_at: datetime


class TicketListResponse(BaseModel):
    """Paginated envelope for GET /api/tickets."""

    model_config = ConfigDict(extra="forbid")

    items: list[TicketRecord]
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)
