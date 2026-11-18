from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.nodes import (
    finalize_node,
    gemini_resolution_node,
    human_action_router_node,
    human_dispatch_node,
    jev_classifier_node,
    route_after_router,
)
from app.agents.state import (
    NODE_FINALIZE,
    NODE_GEMINI_RESOLUTION,
    NODE_HUMAN_ACTION_ROUTER,
    NODE_HUMAN_DISPATCH,
    NODE_JEV_CLASSIFIER,
    ROUTE_GEMINI,
    ROUTE_HUMAN,
    TicketState,
    build_initial_state,
)
from app.core.logging import get_logger
from app.schemas.ticket import TicketInput

logger = get_logger(__name__)

WORKFLOW_EDGES: tuple[tuple[str, str], ...] = (
    (NODE_JEV_CLASSIFIER, NODE_HUMAN_ACTION_ROUTER),
    (NODE_HUMAN_ACTION_ROUTER, NODE_HUMAN_DISPATCH),
    (NODE_HUMAN_ACTION_ROUTER, NODE_GEMINI_RESOLUTION),
    (NODE_HUMAN_DISPATCH, NODE_FINALIZE),
    (NODE_GEMINI_RESOLUTION, NODE_FINALIZE),
)


def build_ticket_graph() -> StateGraph:
    """Builds the uncompiled ticket-routing StateGraph."""
    graph = StateGraph(TicketState)

    graph.add_node(NODE_JEV_CLASSIFIER, jev_classifier_node)
    graph.add_node(NODE_HUMAN_ACTION_ROUTER, human_action_router_node)
    graph.add_node(NODE_HUMAN_DISPATCH, human_dispatch_node)
    graph.add_node(NODE_GEMINI_RESOLUTION, gemini_resolution_node)
    graph.add_node(NODE_FINALIZE, finalize_node)

    graph.add_edge(START, NODE_JEV_CLASSIFIER)
    graph.add_edge(NODE_JEV_CLASSIFIER, NODE_HUMAN_ACTION_ROUTER)
    graph.add_conditional_edges(
        NODE_HUMAN_ACTION_ROUTER,
        route_after_router,
        {
            ROUTE_HUMAN: NODE_HUMAN_DISPATCH,
            ROUTE_GEMINI: NODE_GEMINI_RESOLUTION,
        },
    )
    graph.add_edge(NODE_HUMAN_DISPATCH, NODE_FINALIZE)
    graph.add_edge(NODE_GEMINI_RESOLUTION, NODE_FINALIZE)
    graph.add_edge(NODE_FINALIZE, END)
    return graph


@lru_cache(maxsize=1)
def get_ticket_workflow() -> Any:
    """Returns the compiled workflow, built once per process."""
    return build_ticket_graph().compile()


async def run_ticket_workflow(ticket: TicketInput) -> TicketState:
    """Runs one ticket through the pipeline and returns the final state, which always contains the response."""
    final_state: TicketState = await get_ticket_workflow().ainvoke(build_initial_state(ticket))
    if final_state.get("response") is None:
        raise RuntimeError("Ticket workflow finished without producing a response")
    logger.info(
        "Ticket workflow complete",
        extra={
            "ticket_id": ticket.ticket_id,
            "route": final_state.get("route"),
            "executed_nodes": final_state.get("executed_nodes"),
        },
    )
    return final_state
