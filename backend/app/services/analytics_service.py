from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.settings import settings
from app.core.timeutil import ensure_utc
from app.db.models import ResolutionStatus, RoutingLog, TargetTeam, Ticket, utc_now
from app.schemas.analytics import (
    AnalyticsResponse,
    AnalyticsSummary,
    LatencyPoint,
    SavingsPoint,
    TeamBreakdownItem,
)
from app.services.audit_service import AuditAction, AuditEntity, record_audit_for_principal
from app.services.rbac import Principal

logger = get_logger(__name__)

# Aggregation is done in Python for portability across SQLite and PostgreSQL (percentiles).
# The newest MAX_ANALYTICS_ROWS routing logs inside the window are used, which bounds memory.
MAX_ANALYTICS_ROWS = 50_000
DEFAULT_SERIES_LIMIT = 50


@dataclass(frozen=True)
class _Row:
    ticket_id: str
    team: TargetTeam
    status: ResolutionStatus
    confidence: float
    jev_latency_ms: int
    gemini_ms: Optional[int]
    within_threshold: bool
    time_saved_ms: int
    cost_saved_usd: float
    created_at: datetime


def _percentile(sorted_values: Sequence[int], percent: float) -> float:
    """Nearest-rank percentile of an ascending-sorted sequence; 0.0 when empty."""
    if not sorted_values:
        return 0.0
    rank = max(1, math.ceil(percent / 100 * len(sorted_values)))
    return float(sorted_values[min(rank, len(sorted_values)) - 1])


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _fetch_rows(db: Session, window_days: Optional[int]) -> list[_Row]:
    stmt = (
        select(
            Ticket.ticket_id,
            Ticket.target_team,
            Ticket.status,
            Ticket.confidence_score,
            RoutingLog.jev_latency_ms,
            RoutingLog.gemini_execution_time_ms,
            RoutingLog.jev_within_threshold,
            RoutingLog.time_saved_ms,
            RoutingLog.cost_saved_usd,
            RoutingLog.created_at,
        )
        .select_from(RoutingLog)
        .join(Ticket, Ticket.id == RoutingLog.ticket_pk)
        .order_by(RoutingLog.created_at.desc(), RoutingLog.id.desc())
        .limit(MAX_ANALYTICS_ROWS)
    )
    if window_days is not None:
        stmt = stmt.where(RoutingLog.created_at >= utc_now() - timedelta(days=window_days))

    rows = [
        _Row(
            ticket_id=record.ticket_id,
            team=record.target_team,
            status=record.status,
            confidence=float(record.confidence_score),
            jev_latency_ms=int(record.jev_latency_ms),
            gemini_ms=None if record.gemini_execution_time_ms is None else int(record.gemini_execution_time_ms),
            within_threshold=bool(record.jev_within_threshold),
            time_saved_ms=int(record.time_saved_ms),
            cost_saved_usd=float(record.cost_saved_usd),
            created_at=ensure_utc(record.created_at),
        )
        for record in db.execute(stmt).all()
    ]
    rows.reverse()
    return rows


def _build_summary(rows: Sequence[_Row]) -> AnalyticsSummary:
    total = len(rows)
    human = sum(1 for row in rows if row.status == ResolutionStatus.ASSIGNED_TO_HUMAN)
    latencies = sorted(row.jev_latency_ms for row in rows)
    gemini_times = [row.gemini_ms for row in rows if row.gemini_ms is not None]
    within = sum(1 for row in rows if row.within_threshold)

    return AnalyticsSummary(
        total_tickets=total,
        auto_resolved_count=total - human,
        assigned_to_human_count=human,
        gemini_bypass_rate=round(human / total, 4) if total else 0.0,
        avg_jev_latency_ms=round(_mean(latencies), 2),
        p50_jev_latency_ms=_percentile(latencies, 50),
        p95_jev_latency_ms=_percentile(latencies, 95),
        jev_threshold_ms=settings.JEV_LATENCY_THRESHOLD_MS,
        jev_within_threshold_rate=round(within / total, 4) if total else 0.0,
        avg_gemini_latency_ms=round(_mean(gemini_times), 2) if gemini_times else None,
        avg_confidence=round(_mean([row.confidence for row in rows]), 4),
        total_time_saved_ms=sum(row.time_saved_ms for row in rows),
        total_cost_saved_usd=round(sum(row.cost_saved_usd for row in rows), 6),
    )


def _build_team_breakdown(rows: Sequence[_Row]) -> list[TeamBreakdownItem]:
    breakdown: list[TeamBreakdownItem] = []
    for team in TargetTeam:
        team_rows = [row for row in rows if row.team == team]
        human = sum(1 for row in team_rows if row.status == ResolutionStatus.ASSIGNED_TO_HUMAN)
        breakdown.append(
            TeamBreakdownItem(
                team=team,
                total=len(team_rows),
                auto_resolved=len(team_rows) - human,
                assigned_to_human=human,
                avg_jev_latency_ms=round(_mean([row.jev_latency_ms for row in team_rows]), 2),
            )
        )
    return breakdown


def _build_latency_series(rows: Sequence[_Row], limit: int) -> list[LatencyPoint]:
    return [
        LatencyPoint(
            ticket_id=row.ticket_id,
            created_at=row.created_at,
            jev_latency_ms=row.jev_latency_ms,
            gemini_execution_time_ms=row.gemini_ms,
            jev_within_threshold=row.within_threshold,
        )
        for row in rows[-limit:]
    ]


def _build_savings_series(rows: Sequence[_Row], limit: int) -> list[SavingsPoint]:
    """Cumulative totals run across the whole window, so the last point equals the summary totals."""
    points: list[SavingsPoint] = []
    cumulative_time = 0
    cumulative_cost = 0.0
    for row in rows:
        cumulative_time += row.time_saved_ms
        cumulative_cost += row.cost_saved_usd
        points.append(
            SavingsPoint(
                ticket_id=row.ticket_id,
                created_at=row.created_at,
                time_saved_ms=row.time_saved_ms,
                cost_saved_usd=round(row.cost_saved_usd, 6),
                cumulative_time_saved_ms=cumulative_time,
                cumulative_cost_saved_usd=round(cumulative_cost, 6),
            )
        )
    return points[-limit:]


def build_analytics(
    db: Session,
    window_days: Optional[int] = None,
    series_limit: int = DEFAULT_SERIES_LIMIT,
) -> AnalyticsResponse:
    """Computes the analytics payload without touching the audit trail (shared with report generation)."""
    rows = _fetch_rows(db, window_days)
    return AnalyticsResponse(
        generated_at=utc_now(),
        window_days=window_days,
        summary=_build_summary(rows),
        team_breakdown=_build_team_breakdown(rows),
        latency_series=_build_latency_series(rows, series_limit),
        savings_series=_build_savings_series(rows, series_limit),
    )


def get_analytics(
    db: Session,
    principal: Principal,
    window_days: Optional[int] = None,
    series_limit: int = DEFAULT_SERIES_LIMIT,
) -> AnalyticsResponse:
    """Returns the analytics payload and records the read in the audit trail."""
    response = build_analytics(db, window_days, series_limit)
    record_audit_for_principal(
        db,
        principal,
        action=AuditAction.ANALYTICS_VIEWED,
        entity_type=AuditEntity.ANALYTICS,
        details={"window_days": window_days, "total_tickets": response.summary.total_tickets},
    )
    db.commit()
    return response
