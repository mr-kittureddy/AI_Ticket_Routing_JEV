import operator
from typing import Annotated, Literal, Optional, TypedDict

from app.schemas.ticket import ProcessTicketResponse, TicketInput
from app.services.gemini_service import GeminiResult
from app.services.jev_service import JEVResult

NODE_JEV_CLASSIFIER = "jev_classifier"
NODE_HUMAN_ACTION_ROUTER = "human_action_router"
NODE_HUMAN_DISPATCH = "human_dispatch"
NODE_GEMINI_RESOLUTION = "gemini_resolution"
NODE_FINALIZE = "finalize"

Route = Literal["human", "gemini"]
ROUTE_HUMAN: Route = "human"
ROUTE_GEMINI: Route = "gemini"


class TicketState(TypedDict, total=False):
    """Mutable pipeline state; each node returns only the keys it updates."""

    # Input (PRD §4.1)
    ticket_id: str
    raw_text: str
    submitted_by: str

    # JEV classification node output (PRD §4.2 plus engine metadata)
    jev_result: Optional[JEVResult]

    # Human-action router node output
    route: Optional[Route]
    requires_human_action: bool
    queue_label: Optional[str]

    # Gemini resolution node output (retrieval happens only on the Gemini branch)
    rag_snippets: list[str]
    rag_source_ids: list[str]
    gemini_result: Optional[GeminiResult]

    # Human dispatch node output
    human_notice: Optional[str]

    # Finalize node output
    time_saved_ms: int
    cost_saved_usd: float
    response: Optional[ProcessTicketResponse]

    # Diagnostics: nodes append their own name, in execution order
    executed_nodes: Annotated[list[str], operator.add]


def build_initial_state(ticket: TicketInput) -> TicketState:
    """Creates the starting state for one ticket run from the validated PRD §4.1 input."""
    return TicketState(
        ticket_id=ticket.ticket_id,
        raw_text=ticket.raw_text,
        submitted_by=ticket.submitted_by,
        jev_result=None,
        route=None,
        requires_human_action=False,
        queue_label=None,
        rag_snippets=[],
        rag_source_ids=[],
        gemini_result=None,
        human_notice=None,
        time_saved_ms=0,
        cost_saved_usd=0.0,
        response=None,
        executed_nodes=[],
    )


def require_jev_result(state: TicketState) -> JEVResult:
    """Returns the JEV result or raises when a downstream node runs before classification."""
    result = state.get("jev_result")
    if result is None:
        raise RuntimeError("Pipeline state has no JEV result; the classifier node must run first")
    return result
