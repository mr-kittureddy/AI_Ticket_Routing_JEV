from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import TargetTeam


class ReportFormat(str, Enum):
    """Export formats supported by GET /api/reports."""

    CSV = "csv"
    PDF = "pdf"


class AnalyticsSummary(BaseModel):
    """Headline JEV-vs-Gemini performance and savings figures."""

    model_config = ConfigDict(extra="forbid")

    total_tickets: int = Field(..., ge=0)
    auto_resolved_count: int = Field(..., ge=0)
    assigned_to_human_count: int = Field(..., ge=0)
    gemini_bypass_rate: float = Field(..., ge=0.0, le=1.0, description="Share of tickets that bypassed Gemini")
    avg_jev_latency_ms: float = Field(..., ge=0.0)
    p50_jev_latency_ms: float = Field(..., ge=0.0)
    p95_jev_latency_ms: float = Field(..., ge=0.0)
    jev_threshold_ms: int = Field(..., ge=0)
    jev_within_threshold_rate: float = Field(..., ge=0.0, le=1.0)
    avg_gemini_latency_ms: Optional[float] = Field(
        default=None, ge=0.0, description="Null when no ticket has been drafted by Gemini yet"
    )
    avg_confidence: float = Field(..., ge=0.0, le=1.0)
    total_time_saved_ms: int = Field(..., ge=0)
    total_cost_saved_usd: float = Field(..., ge=0.0)


class TeamBreakdownItem(BaseModel):
    """Per-team routing volume and speed."""

    model_config = ConfigDict(extra="forbid")

    team: TargetTeam
    total: int = Field(..., ge=0)
    auto_resolved: int = Field(..., ge=0)
    assigned_to_human: int = Field(..., ge=0)
    avg_jev_latency_ms: float = Field(..., ge=0.0)


class LatencyPoint(BaseModel):
    """One ticket's JEV vs Gemini timing, used by the latency chart."""

    model_config = ConfigDict(extra="forbid")

    ticket_id: str
    created_at: datetime
    jev_latency_ms: int = Field(..., ge=0)
    gemini_execution_time_ms: Optional[int] = Field(default=None, ge=0)
    jev_within_threshold: bool


class SavingsPoint(BaseModel):
    """One ticket's savings plus the running totals, used by the cost-savings chart."""

    model_config = ConfigDict(extra="forbid")

    ticket_id: str
    created_at: datetime
    time_saved_ms: int = Field(..., ge=0)
    cost_saved_usd: float = Field(..., ge=0.0)
    cumulative_time_saved_ms: int = Field(..., ge=0)
    cumulative_cost_saved_usd: float = Field(..., ge=0.0)


class AnalyticsResponse(BaseModel):
    """Payload for GET /api/analytics."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    window_days: Optional[int] = Field(default=None, ge=1, description="Null means all-time")
    summary: AnalyticsSummary
    team_breakdown: list[TeamBreakdownItem]
    latency_series: list[LatencyPoint]
    savings_series: list[SavingsPoint]


EngineMode = Literal["live", "simulated"]


class HealthResponse(BaseModel):
    """Payload for GET /api/health; tells the dashboard which engines are live or simulated."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded"]
    environment: str
    database_ok: bool
    jev_engine_mode: EngineMode
    gemini_engine_mode: EngineMode
    rag_enabled: bool
    jev_threshold_ms: int = Field(..., ge=0)
