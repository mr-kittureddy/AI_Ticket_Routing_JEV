from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_db
from app.schemas.ticket import ProcessTicketResponse, TicketInput
from app.services.rbac import Principal, process_ticket_access
from app.services.ticket_service import DuplicateTicketError, process_ticket

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["tickets"])


@router.post(
    "/process-ticket",
    response_model=ProcessTicketResponse,
    status_code=status.HTTP_200_OK,
    summary="Classify, route and resolve a support ticket",
    description=(
        "JEV classifies the ticket into a team and decides whether human action is required. "
        "Tickets with requires_human_action=true bypass Gemini and are assigned to a human queue; "
        "all others receive a Gemini-drafted step-by-step resolution."
    ),
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "A known user is required (only when RBAC is enforced)"},
        status.HTTP_403_FORBIDDEN: {"description": "Role lacks the tickets:process permission (only when RBAC is enforced)"},
        status.HTTP_409_CONFLICT: {"description": "The ticket_id has already been processed"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "The database is unavailable"},
    },
)
async def process_ticket_endpoint(
    ticket: TicketInput,
    db: Session = Depends(get_db),
    principal: Principal = Depends(process_ticket_access),
) -> ProcessTicketResponse:
    """Runs the ticket through the LangGraph pipeline and returns the PRD §4.3 response."""
    try:
        return await process_ticket(db, ticket, principal)
    except DuplicateTicketError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception("Database error while processing ticket", extra={"ticket_id": ticket.ticket_id})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The ticket store is temporarily unavailable. Please retry.",
        ) from exc
