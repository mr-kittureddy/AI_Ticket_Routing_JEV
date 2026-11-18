import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.agents.state import (
    NODE_FINALIZE,
    NODE_GEMINI_RESOLUTION,
    NODE_HUMAN_ACTION_ROUTER,
    NODE_HUMAN_DISPATCH,
    NODE_JEV_CLASSIFIER,
    ROUTE_GEMINI,
    ROUTE_HUMAN,
    Route,
    TicketState,
    require_jev_result,
)
from app.core.logging import get_logger
from app.core.settings import settings
from app.db.models import ResolutionStatus, RoutingRule
from app.db.session import session_scope
from app.schemas.ticket import (
    HUMAN_HANDLER_LABEL,
    ProcessTicketResponse,
    ResolutionInfo,
    RoutingInfo,
)
from app.services.gemini_service import get_gemini_service
from app.services.jev_service import (
    RoutingRuleDef,
    default_rule_definitions,
    get_jev_service,
    queue_label_for,
    rule_definitions_from_models,
)
from app.services.rag_service import get_rag_service

logger = get_logger(__name__)


def _load_rule_definitions() -> list[RoutingRuleDef]:
    """Loads active routing rules (highest priority first); falls back to the seed defaults on a database error."""
    try:
        with session_scope() as session:
            models = session.scalars(
                select(RoutingRule)
                .where(RoutingRule.is_active.is_(True))
                .order_by(RoutingRule.priority.desc())
            ).all()
            return rule_definitions_from_models(models)
    except SQLAlchemyError:
        logger.exception("Could not load routing rules; using seed defaults")
        return default_rule_definitions()


async def jev_classifier_node(state: TicketState) -> dict[str, Any]:
    """Classifies the raw ticket text into a team, a human-action flag and a confidence score."""
    rules = await asyncio.to_thread(_load_rule_definitions)
    result = await get_jev_service().classify(state["raw_text"], rules)
    logger.info(
        "JEV classification complete",
        extra={
            "ticket_id": state["ticket_id"],
            "engine": result.engine,
            "target_team": result.decision.target_team.value,
            "requires_human_action": result.decision.requires_human_action,
            "jev_latency_ms": result.decision.jev_latency_ms,
        },
    )
    return {"jev_result": result, "executed_nodes": [NODE_JEV_CLASSIFIER]}


def human_action_router_node(state: TicketState) -> dict[str, Any]:
    """Makes the single bypass decision: requires_human_action=True routes to a human queue, never to Gemini."""
    result = require_jev_result(state)
    decision = result.decision
    requires_human_action = decision.requires_human_action
    route: Route = ROUTE_HUMAN if requires_human_action else ROUTE_GEMINI

    queue_label = None
    if requires_human_action:
        queue_label = result.queue_label or queue_label_for(decision.target_team, True)

    return {
        "route": route,
        "requires_human_action": requires_human_action,
        "queue_label": queue_label,
        "executed_nodes": [NODE_HUMAN_ACTION_ROUTER],
    }


def route_after_router(state: TicketState) -> Route:
    """Conditional-edge selector reading the route chosen by the human-action router node."""
    route = state.get("route")
    if route not in (ROUTE_HUMAN, ROUTE_GEMINI):
        raise RuntimeError("Pipeline state has no route; the human-action router node must run first")
    return route


def human_dispatch_node(state: TicketState) -> dict[str, Any]:
    """Assigns the ticket to a human queue and writes the assignment notice; Gemini is never invoked."""
    result = require_jev_result(state)
    queue_label = state.get("queue_label")
    if not queue_label:
        raise RuntimeError("Human dispatch requires a queue label from the router node")

    team = result.decision.target_team
    notice = (
        f"Assigned to {queue_label}. "
        f"A human representative on the {team.value.replace('_', ' ')} will review and action this request, "
        f"because it requires a purchase, a physical installation, or an administrative approval. "
        f"Automated resolution was bypassed."
    )
    logger.info(
        "Ticket assigned to human queue; Gemini bypassed",
        extra={"ticket_id": state["ticket_id"], "queue": queue_label},
    )
    return {"human_notice": notice, "executed_nodes": [NODE_HUMAN_DISPATCH]}


async def gemini_resolution_node(state: TicketState) -> dict[str, Any]:
    """Retrieves similar resolved tickets, then drafts the step-by-step resolution with Gemini."""
    result = require_jev_result(state)
    team = result.decision.target_team

    rag_result = await get_rag_service().retrieve(state["raw_text"])
    gemini_result = await get_gemini_service().generate_resolution(
        state["raw_text"], team, rag_result.snippets, routing_notes=result.criteria
    )
    logger.info(
        "Gemini resolution complete",
        extra={
            "ticket_id": state["ticket_id"],
            "engine": gemini_result.engine,
            "gemini_execution_time_ms": gemini_result.execution_time_ms,
            "rag_sources": len(rag_result.source_ids),
        },
    )
    return {
        "rag_snippets": rag_result.snippets,
        "rag_source_ids": rag_result.source_ids,
        "gemini_result": gemini_result,
        "executed_nodes": [NODE_GEMINI_RESOLUTION],
    }


def finalize_node(state: TicketState) -> dict[str, Any]:
    """Builds the PRD §4.3 response and computes the time and cost saved by bypassing Gemini."""
    result = require_jev_result(state)
    decision = result.decision
    route = state.get("route")

    routing = RoutingInfo(
        team=decision.target_team,
        requires_action=decision.requires_human_action,
        jev_confidence=decision.confidence_score,
        jev_execution_time_ms=decision.jev_latency_ms,
    )

    if route == ROUTE_HUMAN:
        if state.get("gemini_result") is not None:
            raise RuntimeError("Gemini must not run for tickets that require human action")
        notice = state.get("human_notice")
        if not notice:
            raise RuntimeError("Human-routed ticket is missing its assignment notice")
        resolution = ResolutionInfo(
            handled_by=HUMAN_HANDLER_LABEL,
            status=ResolutionStatus.ASSIGNED_TO_HUMAN,
            response_text=notice,
            gemini_execution_time_ms=None,
        )
        time_saved_ms = settings.BASELINE_GEMINI_LATENCY_MS
        cost_saved_usd = settings.BASELINE_GEMINI_COST_USD
    elif route == ROUTE_GEMINI:
        gemini_result = state.get("gemini_result")
        if gemini_result is None:
            raise RuntimeError("Gemini-routed ticket is missing its resolution")
        resolution = ResolutionInfo(
            handled_by=gemini_result.model_label,
            status=ResolutionStatus.AUTO_RESOLVED,
            response_text=gemini_result.response_text,
            gemini_execution_time_ms=gemini_result.execution_time_ms,
        )
        time_saved_ms = 0
        cost_saved_usd = 0.0
    else:
        raise RuntimeError("Pipeline reached finalize without a route")

    response = ProcessTicketResponse(
        ticket_id=state["ticket_id"],
        routing=routing,
        resolution=resolution,
    )
    return {
        "response": response,
        "time_saved_ms": time_saved_ms,
        "cost_saved_usd": cost_saved_usd,
        "executed_nodes": [NODE_FINALIZE],
    }
