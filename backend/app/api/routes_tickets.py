from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.db.models import ResolutionStatus, TargetTeam
from app.db.session import get_db
from app.schemas.ticket import TICKET_ID_PATTERN, TicketListResponse, TicketTrace
from app.services.rbac import Permission, Principal, require_permission
from app.services.ticket_service import TicketNotFoundError, get_ticket_trace, list_tickets

router = APIRouter(prefix="/api", tags=["tickets"])


@router.get(
    "/tickets",
    response_model=TicketListResponse,
    summary="List processed tickets",
    description="Newest-first, paginated ticket history with optional team, status, human-action and text filters.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "A known user is required"},
        status.HTTP_403_FORBIDDEN: {"description": "Role lacks the tickets:read permission"},
    },
)
def list_tickets_endpoint(
    page: int = Query(default=1, ge=1, description="1-based page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    team: Optional[TargetTeam] = Query(default=None, description="Filter by routed team"),
    resolution_status: Optional[ResolutionStatus] = Query(
        default=None, alias="status", description="Filter by AUTO_RESOLVED or ASSIGNED_TO_HUMAN"
    ),
    requires_human_action: Optional[bool] = Query(default=None, description="Filter by the human-action flag"),
    search: Optional[str] = Query(default=None, max_length=100, description="Match against ticket_id or ticket text"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission(Permission.TICKETS_READ)),
) -> TicketListResponse:
    """Returns one page of tickets, newest first."""
    return list_tickets(
        db,
        principal,
        page=page,
        page_size=page_size,
        team=team,
        status=resolution_status,
        requires_human_action=requires_human_action,
        search=search,
    )


@router.get(
    "/tickets/{ticket_id}/trace",
    response_model=TicketTrace,
    summary="Get the routing trace for a ticket",
    description=(
        "Returns the decision criteria, engine modes, latency threshold compliance and the time and cost "
        "saved by bypassing Gemini."
    ),
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "A known user is required"},
        status.HTTP_403_FORBIDDEN: {"description": "Role lacks the tickets:read permission"},
        status.HTTP_404_NOT_FOUND: {"description": "No ticket with that ticket_id exists"},
    },
)
def get_ticket_trace_endpoint(
    ticket_id: str = Path(..., pattern=TICKET_ID_PATTERN, max_length=64, description="Ticket identifier, e.g. TCK-8821"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission(Permission.TICKETS_READ)),
) -> TicketTrace:
    """Returns the routing trace for one ticket."""
    try:
        return get_ticket_trace(db, principal, ticket_id)
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
