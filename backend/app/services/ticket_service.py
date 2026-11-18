from __future__ import annotations

from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.agents.state import ROUTE_HUMAN, TicketState, require_jev_result
from app.agents.ticket_workflow import run_ticket_workflow
from app.core.logging import get_logger
from app.core.settings import settings
from app.core.timeutil import ensure_utc
from app.db.models import ResolutionStatus, RoutingLog, TargetTeam, Ticket
from app.schemas.ticket import (
    ProcessTicketResponse,
    TicketInput,
    TicketListResponse,
    TicketRecord,
    TicketTrace,
)
from app.services.audit_service import (
    AuditAction,
    AuditEntity,
    record_audit_best_effort,
    record_audit_for_principal,
)
from app.services.gemini_service import ENGINE_BYPASSED, ENGINE_GEMINI
from app.services.rag_service import get_rag_service
from app.services.rbac import Principal

logger = get_logger(__name__)


class TicketServiceError(Exception):
    """Base class for expected ticket-service failures."""


class DuplicateTicketError(TicketServiceError):
    """Raised when a ticket_id has already been processed."""

    def __init__(self, ticket_id: str) -> None:
        super().__init__(f"Ticket '{ticket_id}' has already been processed")
        self.ticket_id = ticket_id


class TicketNotFoundError(TicketServiceError):
    """Raised when a requested ticket (or its routing trace) does not exist."""

    def __init__(self, ticket_id: str) -> None:
        super().__init__(f"Ticket '{ticket_id}' was not found")
        self.ticket_id = ticket_id


def _ticket_exists(db: Session, ticket_id: str) -> bool:
    return db.scalar(select(Ticket.id).where(Ticket.ticket_id == ticket_id)) is not None


def _record_duplicate(principal: Principal, ticket_id: str) -> None:
    record_audit_best_effort(
        principal,
        action=AuditAction.TICKET_DUPLICATE_REJECTED,
        entity_type=AuditEntity.TICKET,
        entity_id=ticket_id,
        details={"reason": "ticket_id already processed"},
    )


def _record_failure(principal: Principal, ticket_id: str, stage: str, exc: Exception) -> None:
    record_audit_best_effort(
        principal,
        action=AuditAction.TICKET_PROCESSING_FAILED,
        entity_type=AuditEntity.TICKET,
        entity_id=ticket_id,
        details={"stage": stage, "error_type": type(exc).__name__},
    )


def _build_decision_criteria(state: TicketState) -> list[str]:
    jev = require_jev_result(state)
    criteria = list(jev.criteria)
    gemini = state.get("gemini_result")
    if gemini is not None:
        criteria.extend(gemini.notes)
    if state.get("route") == ROUTE_HUMAN:
        criteria.append(
            "Gemini bypassed because requires_human_action=true; "
            f"estimated {state.get('time_saved_ms', 0)} ms and ${state.get('cost_saved_usd', 0.0):.4f} saved"
        )
    return criteria


def _persist(db: Session, ticket_in: TicketInput, state: TicketState, principal: Principal) -> None:
    """Adds the Ticket, its RoutingLog and the audit entry to the session; the caller commits."""
    jev = require_jev_result(state)
    decision = jev.decision
    response = state.get("response")
    if response is None:
        raise RuntimeError("Cannot persist a ticket without a pipeline response")
    resolution = response.resolution
    gemini = state.get("gemini_result")
    bypassed = state.get("route") == ROUTE_HUMAN
    rag_source_ids = list(state.get("rag_source_ids") or [])

    record = Ticket(
        ticket_id=ticket_in.ticket_id,
        raw_text=ticket_in.raw_text,
        submitted_by=ticket_in.submitted_by,
        target_team=decision.target_team,
        requires_human_action=decision.requires_human_action,
        confidence_score=decision.confidence_score,
        jev_latency_ms=decision.jev_latency_ms,
        status=resolution.status,
        handled_by=resolution.handled_by,
        assigned_queue=state.get("queue_label"),
        response_text=resolution.response_text,
        gemini_execution_time_ms=resolution.gemini_execution_time_ms,
    )
    record.routing_logs.append(
        RoutingLog(
            jev_engine=jev.engine,
            gemini_engine=ENGINE_BYPASSED if gemini is None else gemini.engine,
            jev_latency_ms=decision.jev_latency_ms,
            gemini_execution_time_ms=resolution.gemini_execution_time_ms,
            jev_within_threshold=jev.within_threshold,
            gemini_bypassed=bypassed,
            time_saved_ms=int(state.get("time_saved_ms", 0)),
            cost_saved_usd=float(state.get("cost_saved_usd", 0.0)),
            decision_criteria=_build_decision_criteria(state),
            rag_sources=rag_source_ids or None,
        )
    )
    db.add(record)
    db.flush()

    record_audit_for_principal(
        db,
        principal,
        action=AuditAction.TICKET_PROCESSED,
        entity_type=AuditEntity.TICKET,
        entity_id=ticket_in.ticket_id,
        details={
            "route": state.get("route"),
            "target_team": decision.target_team,
            "status": resolution.status,
            "requires_human_action": decision.requires_human_action,
            "jev_engine": jev.engine,
            "jev_latency_ms": decision.jev_latency_ms,
            "gemini_engine": ENGINE_BYPASSED if gemini is None else gemini.engine,
            "gemini_execution_time_ms": resolution.gemini_execution_time_ms,
            "submitted_by": ticket_in.submitted_by,
        },
    )


async def _index_live_resolution(ticket_in: TicketInput, state: TicketState) -> None:
    """Adds a Gemini-written resolution to the knowledge base; simulated text is never indexed."""
    gemini = state.get("gemini_result")
    if gemini is None or gemini.engine != ENGINE_GEMINI:
        return
    team = require_jev_result(state).decision.target_team
    await get_rag_service().index_resolved_ticket(
        ticket_in.ticket_id, ticket_in.raw_text, team, gemini.response_text
    )


async def process_ticket(db: Session, ticket: TicketInput, principal: Principal) -> ProcessTicketResponse:
    """Runs the full pipeline for one ticket and persists the result.

    Raises DuplicateTicketError (HTTP 409 at the route) when the ticket_id was already processed.
    """
    if _ticket_exists(db, ticket.ticket_id):
        _record_duplicate(principal, ticket.ticket_id)
        raise DuplicateTicketError(ticket.ticket_id)
    # End the read transaction so no database connection or lock is held during the slow LLM calls.
    db.rollback()

    try:
        state = await run_ticket_workflow(ticket)
    except Exception as exc:
        logger.exception("Ticket workflow failed", extra={"ticket_id": ticket.ticket_id})
        _record_failure(principal, ticket.ticket_id, "workflow", exc)
        raise

    response = state.get("response")
    if response is None:
        raise RuntimeError("Ticket workflow finished without producing a response")

    try:
        _persist(db, ticket, state, principal)
        db.commit()
    except IntegrityError:
        db.rollback()
        if _ticket_exists(db, ticket.ticket_id):
            _record_duplicate(principal, ticket.ticket_id)
            raise DuplicateTicketError(ticket.ticket_id) from None
        logger.exception("Integrity error while persisting ticket", extra={"ticket_id": ticket.ticket_id})
        _record_failure(principal, ticket.ticket_id, "persist", IntegrityError("", None, Exception()))
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Database error while persisting ticket", extra={"ticket_id": ticket.ticket_id})
        _record_failure(principal, ticket.ticket_id, "persist", exc)
        raise

    await _index_live_resolution(ticket, state)
    return response


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _to_record(ticket: Ticket) -> TicketRecord:
    return TicketRecord(
        ticket_id=ticket.ticket_id,
        raw_text=ticket.raw_text,
        submitted_by=ticket.submitted_by,
        target_team=ticket.target_team,
        requires_human_action=ticket.requires_human_action,
        confidence_score=ticket.confidence_score,
        jev_latency_ms=ticket.jev_latency_ms,
        status=ticket.status,
        handled_by=ticket.handled_by,
        assigned_queue=ticket.assigned_queue,
        response_text=ticket.response_text,
        gemini_execution_time_ms=ticket.gemini_execution_time_ms,
        created_at=ensure_utc(ticket.created_at),
    )


def list_tickets(
    db: Session,
    principal: Principal,
    *,
    page: int = 1,
    page_size: int = 20,
    team: Optional[TargetTeam] = None,
    status: Optional[ResolutionStatus] = None,
    requires_human_action: Optional[bool] = None,
    search: Optional[str] = None,
) -> TicketListResponse:
    """Returns a newest-first page of tickets with optional filters, and records the read in the audit trail."""
    filters = []
    if team is not None:
        filters.append(Ticket.target_team == team)
    if status is not None:
        filters.append(Ticket.status == status)
    if requires_human_action is not None:
        filters.append(Ticket.requires_human_action == requires_human_action)
    term = (search or "").strip()
    if term:
        pattern = f"%{_escape_like(term)}%"
        filters.append(
            or_(
                Ticket.ticket_id.ilike(pattern, escape="\\"),
                Ticket.raw_text.ilike(pattern, escape="\\"),
            )
        )

    total = db.scalar(select(func.count()).select_from(Ticket).where(*filters)) or 0
    rows = db.scalars(
        select(Ticket)
        .where(*filters)
        .order_by(Ticket.created_at.desc(), Ticket.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [_to_record(row) for row in rows]

    record_audit_for_principal(
        db,
        principal,
        action=AuditAction.TICKETS_LISTED,
        entity_type=AuditEntity.TICKET_COLLECTION,
        details={
            "page": page,
            "page_size": page_size,
            "returned": len(items),
            "team": team,
            "status": status,
            "requires_human_action": requires_human_action,
            "has_search": bool(term),
        },
    )
    db.commit()
    return TicketListResponse(items=items, total=int(total), page=page, page_size=page_size)


def get_ticket_trace(db: Session, principal: Principal, ticket_id: str) -> TicketTrace:
    """Returns the routing trace (criteria, engines, savings) for a ticket, and records the read in the audit trail."""
    ticket = db.scalars(select(Ticket).where(Ticket.ticket_id == ticket_id)).first()
    if ticket is None:
        raise TicketNotFoundError(ticket_id)
    log = db.scalars(
        select(RoutingLog)
        .where(RoutingLog.ticket_pk == ticket.id)
        .order_by(RoutingLog.created_at.desc(), RoutingLog.id.desc())
    ).first()
    if log is None:
        raise TicketNotFoundError(ticket_id)

    trace = TicketTrace(
        ticket_id=ticket.ticket_id,
        jev_engine=log.jev_engine,
        gemini_engine=log.gemini_engine,
        jev_latency_ms=log.jev_latency_ms,
        jev_threshold_ms=settings.JEV_LATENCY_THRESHOLD_MS,
        jev_within_threshold=log.jev_within_threshold,
        gemini_bypassed=log.gemini_bypassed,
        gemini_execution_time_ms=log.gemini_execution_time_ms,
        decision_criteria=list(log.decision_criteria or []),
        assigned_queue=ticket.assigned_queue,
        time_saved_ms=log.time_saved_ms,
        cost_saved_usd=log.cost_saved_usd,
        rag_sources=list(log.rag_sources) if log.rag_sources else None,
        created_at=ensure_utc(log.created_at),
    )

    record_audit_for_principal(
        db,
        principal,
        action=AuditAction.TICKET_TRACE_VIEWED,
        entity_type=AuditEntity.TICKET,
        entity_id=ticket_id,
    )
    db.commit()
    return trace
