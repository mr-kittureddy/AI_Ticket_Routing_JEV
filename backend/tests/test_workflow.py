import re

import pytest

from app.agents.nodes import finalize_node, route_after_router
from app.agents.state import (
    NODE_FINALIZE,
    NODE_GEMINI_RESOLUTION,
    NODE_HUMAN_ACTION_ROUTER,
    NODE_HUMAN_DISPATCH,
    NODE_JEV_CLASSIFIER,
    ROUTE_GEMINI,
    ROUTE_HUMAN,
)
from app.agents.ticket_workflow import WORKFLOW_EDGES, get_ticket_workflow, run_ticket_workflow
from app.core.settings import settings
from app.db.models import ResolutionStatus, TargetTeam
from app.schemas.ticket import GEMINI_HANDLER_LABEL, HUMAN_HANDLER_LABEL, TicketInput
from app.services.gemini_service import ENGINE_SIMULATOR, GeminiResult, get_gemini_service
from app.services.jev_service import JEVService
from app.services.rag_service import get_rag_service

# The workflow loads routing rules from the database, so the session client (which prepares and seeds it) is required.
pytestmark = pytest.mark.usefixtures("client")

HARDWARE_TEXT = "Need a second 27-inch monitor and USB hub."
PERMISSION_TEXT = "Grant IAM read access to S3 bucket prod-logs."
NETWORK_TEXT = "GlobalProtect VPN failing to connect on macOS."
SOFTWARE_TEXT = "How do I export Jira board metrics to Excel?"


def _ticket(text: str) -> TicketInput:
    return TicketInput(ticket_id="TCK-WORKFLOW-1", raw_text=text, submitted_by="user@company.com")


async def _must_not_run(*args: object, **kwargs: object) -> None:
    raise AssertionError("Gemini and RAG must not run for tickets that require human action")


@pytest.mark.parametrize(
    "text,team,queue",
    [
        pytest.param(HARDWARE_TEXT, TargetTeam.HARDWARE, "Hardware Procurement Queue", id="hardware-request"),
        pytest.param(PERMISSION_TEXT, TargetTeam.INFRA, "Infrastructure Access Queue", id="permission-request"),
    ],
)
async def test_human_action_tickets_bypass_gemini_and_rag(
    monkeypatch: pytest.MonkeyPatch, text: str, team: TargetTeam, queue: str
) -> None:
    monkeypatch.setattr(get_gemini_service(), "generate_resolution", _must_not_run)
    monkeypatch.setattr(get_rag_service(), "retrieve", _must_not_run)

    state = await run_ticket_workflow(_ticket(text))
    response = state["response"]

    assert state["route"] == ROUTE_HUMAN
    assert state["gemini_result"] is None
    assert state["rag_source_ids"] == []
    assert state["executed_nodes"] == [
        NODE_JEV_CLASSIFIER,
        NODE_HUMAN_ACTION_ROUTER,
        NODE_HUMAN_DISPATCH,
        NODE_FINALIZE,
    ]
    assert NODE_GEMINI_RESOLUTION not in state["executed_nodes"]

    assert response.routing.team == team
    assert response.routing.requires_action is True
    assert response.resolution.status == ResolutionStatus.ASSIGNED_TO_HUMAN
    assert response.resolution.handled_by == HUMAN_HANDLER_LABEL
    assert response.resolution.gemini_execution_time_ms is None
    assert response.resolution.response_text is not None
    assert response.resolution.response_text.startswith(f"Assigned to {queue}.")

    assert state["queue_label"] == queue
    assert state["time_saved_ms"] == settings.BASELINE_GEMINI_LATENCY_MS
    assert state["cost_saved_usd"] == settings.BASELINE_GEMINI_COST_USD


@pytest.mark.parametrize(
    "text,team,expected_fragment",
    [
        pytest.param(NETWORK_TEXT, TargetTeam.NETWORK, "Privacy & Security", id="network-issue"),
        pytest.param(SOFTWARE_TEXT, TargetTeam.SOFTWARE, "Export", id="software-how-to"),
    ],
)
async def test_self_service_tickets_get_a_gemini_resolution(
    text: str, team: TargetTeam, expected_fragment: str
) -> None:
    state = await run_ticket_workflow(_ticket(text))
    response = state["response"]
    gemini_result = state["gemini_result"]

    assert state["route"] == ROUTE_GEMINI
    assert state["executed_nodes"] == [
        NODE_JEV_CLASSIFIER,
        NODE_HUMAN_ACTION_ROUTER,
        NODE_GEMINI_RESOLUTION,
        NODE_FINALIZE,
    ]
    assert NODE_HUMAN_DISPATCH not in state["executed_nodes"]

    assert response.routing.team == team
    assert response.routing.requires_action is False
    assert response.resolution.status == ResolutionStatus.AUTO_RESOLVED
    assert response.resolution.handled_by == GEMINI_HANDLER_LABEL
    assert response.resolution.gemini_execution_time_ms is not None
    assert response.resolution.gemini_execution_time_ms >= 1

    resolution_text = response.resolution.response_text
    assert resolution_text is not None
    assert resolution_text.startswith("1. ")
    assert all(re.match(r"^\d+\. ", line) for line in resolution_text.splitlines())
    assert expected_fragment in resolution_text
    assert "reply to this ticket" in resolution_text.lower()

    assert gemini_result is not None
    assert gemini_result.engine == ENGINE_SIMULATOR
    assert state["queue_label"] is None
    assert state["time_saved_ms"] == 0
    assert state["cost_saved_usd"] == 0.0


async def test_unmatched_text_takes_the_self_service_branch() -> None:
    state = await run_ticket_workflow(_ticket("Zebra quantum pineapple"))

    assert state["route"] == ROUTE_GEMINI
    assert state["response"].routing.team == TargetTeam.SOFTWARE
    assert state["response"].resolution.status == ResolutionStatus.AUTO_RESOLVED
    assert state["jev_result"].criteria[0].startswith("No routing keywords matched")


async def test_finalize_refuses_a_gemini_result_on_the_human_branch() -> None:
    jev_result = await JEVService().classify(HARDWARE_TEXT)
    gemini_result = GeminiResult(
        response_text="1. Something",
        execution_time_ms=5,
        engine=ENGINE_SIMULATOR,
        model_label=GEMINI_HANDLER_LABEL,
    )
    state = {
        "ticket_id": "TCK-FINALIZE-1",
        "jev_result": jev_result,
        "route": ROUTE_HUMAN,
        "human_notice": "Assigned to Hardware Procurement Queue.",
        "gemini_result": gemini_result,
    }

    with pytest.raises(RuntimeError, match="must not run"):
        finalize_node(state)


async def test_finalize_requires_a_route() -> None:
    jev_result = await JEVService().classify(HARDWARE_TEXT)

    with pytest.raises(RuntimeError, match="without a route"):
        finalize_node({"ticket_id": "TCK-FINALIZE-2", "jev_result": jev_result})


def test_route_selector_reads_the_router_decision() -> None:
    assert route_after_router({"route": ROUTE_HUMAN}) == ROUTE_HUMAN
    assert route_after_router({"route": ROUTE_GEMINI}) == ROUTE_GEMINI
    with pytest.raises(RuntimeError):
        route_after_router({})


def test_graph_topology_matches_the_design() -> None:
    graph = get_ticket_workflow().get_graph()
    expected_nodes = {
        NODE_JEV_CLASSIFIER,
        NODE_HUMAN_ACTION_ROUTER,
        NODE_HUMAN_DISPATCH,
        NODE_GEMINI_RESOLUTION,
        NODE_FINALIZE,
    }

    assert expected_nodes.issubset(set(graph.nodes))
    assert len(WORKFLOW_EDGES) == 5
    assert (NODE_HUMAN_ACTION_ROUTER, NODE_HUMAN_DISPATCH) in WORKFLOW_EDGES
    assert (NODE_HUMAN_ACTION_ROUTER, NODE_GEMINI_RESOLUTION) in WORKFLOW_EDGES
