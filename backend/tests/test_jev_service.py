import json

import httpx
import pytest

from app.core.settings import Settings, settings
from app.db.models import TargetTeam
from app.services.jev_service import (
    ENGINE_OPENROUTER,
    ENGINE_SIMULATOR,
    ENGINE_SIMULATOR_FALLBACK,
    JEVService,
    RoutingRuleDef,
    _keyword_pattern,
    _parse_llm_decision,
    _parse_systemone_decision,
    default_rule_definitions,
    queue_label_for,
)

NETWORK_TEXT = "GlobalProtect VPN failing to connect on macOS."

PRD_PRESETS = [
    pytest.param(
        "Need a second 27-inch monitor and USB hub.",
        TargetTeam.HARDWARE,
        True,
        "hardware-procurement",
        "Hardware Procurement Queue",
        id="hardware-request",
    ),
    pytest.param(
        NETWORK_TEXT,
        TargetTeam.NETWORK,
        False,
        "network-troubleshooting",
        None,
        id="network-issue",
    ),
    pytest.param(
        "Grant IAM read access to S3 bucket prod-logs.",
        TargetTeam.INFRA,
        True,
        "infra-access",
        "Infrastructure Access Queue",
        id="permission-request",
    ),
    pytest.param(
        "How do I export Jira board metrics to Excel?",
        TargetTeam.SOFTWARE,
        False,
        "software-howto",
        None,
        id="software-how-to",
    ),
]


def _live_service() -> JEVService:
    return JEVService(Settings(OPENROUTER_API_KEY="sk-or-v1-test-key-123456"))


@pytest.mark.parametrize("text,team,requires_action,rule,queue", PRD_PRESETS)
async def test_prd_presets_route_exactly_as_specified(
    text: str, team: TargetTeam, requires_action: bool, rule: str, queue: str | None
) -> None:
    result = await JEVService().classify(text)

    assert result.engine == ENGINE_SIMULATOR
    assert result.decision.target_team == team
    assert result.decision.requires_human_action is requires_action
    assert result.matched_rule == rule
    assert result.queue_label == queue
    assert 0.9 <= result.decision.confidence_score <= 1.0


async def test_simulator_is_deterministic_apart_from_latency() -> None:
    service = JEVService()
    first = await service.classify(NETWORK_TEXT)
    second = await service.classify(NETWORK_TEXT)

    assert first.decision.target_team == second.decision.target_team
    assert first.decision.requires_human_action == second.decision.requires_human_action
    assert first.decision.confidence_score == second.decision.confidence_score
    assert first.criteria == second.criteria


async def test_latency_is_measured_and_threshold_flag_is_consistent() -> None:
    result = await JEVService().classify(NETWORK_TEXT)

    assert isinstance(result.decision.jev_latency_ms, int)
    assert result.decision.jev_latency_ms >= 1
    assert result.within_threshold == (result.decision.jev_latency_ms < settings.JEV_LATENCY_THRESHOLD_MS)


async def test_unmatched_text_defaults_to_self_service_software() -> None:
    result = await JEVService().classify("Zebra quantum pineapple")

    assert result.decision.target_team == TargetTeam.SOFTWARE
    assert result.decision.requires_human_action is False
    assert result.decision.confidence_score == 0.35
    assert result.matched_rule is None
    assert result.queue_label is None
    assert result.criteria[0].startswith("No routing keywords matched")


async def test_simulator_records_why_it_is_in_use() -> None:
    result = await JEVService().classify(NETWORK_TEXT)
    assert any("masked" in line for line in result.criteria)


async def test_empty_rule_list_falls_back_to_the_seed_defaults() -> None:
    with_defaults = await JEVService().classify(NETWORK_TEXT)
    with_empty_list = await JEVService().classify(NETWORK_TEXT, [])

    assert with_empty_list.matched_rule == with_defaults.matched_rule
    assert with_empty_list.decision.target_team == with_defaults.decision.target_team


async def test_custom_rules_override_the_defaults() -> None:
    rule = RoutingRuleDef(
        name="banana-rule",
        description="Banana handling",
        target_team=TargetTeam.INFRA,
        requires_human_action=True,
        priority=10,
        keywords=("banana",),
    )
    result = await JEVService().classify("I need a banana", [rule])

    assert result.matched_rule == "banana-rule"
    assert result.decision.target_team == TargetTeam.INFRA
    assert result.decision.requires_human_action is True


def test_keyword_matching_respects_word_boundaries() -> None:
    assert _keyword_pattern("fan").search("fantastic") is None
    assert _keyword_pattern("fan").search("the fan is loud") is not None
    assert _keyword_pattern("vpn").search("my vpn") is not None


def test_default_rules_cover_all_four_teams_with_both_flag_values() -> None:
    rules = default_rule_definitions()

    assert len(rules) == 8
    assert {rule.target_team for rule in rules} == set(TargetTeam)
    assert {rule.requires_human_action for rule in rules} == {True, False}


def test_queue_labels() -> None:
    assert queue_label_for(TargetTeam.HARDWARE, True) == "Hardware Procurement Queue"
    assert queue_label_for(TargetTeam.INFRA, True) == "Infrastructure Access Queue"
    assert queue_label_for(TargetTeam.SOFTWARE, True) == "Software License Queue"
    assert queue_label_for(TargetTeam.NETWORK, True) == "Network Change Request Queue"
    for team in TargetTeam:
        assert queue_label_for(team, False) is None


def test_parse_llm_decision_accepts_plain_json() -> None:
    payload = json.dumps(
        {
            "target_team": "infra_team",
            "requires_human_action": True,
            "confidence_score": 0.91,
            "criteria": ["needs admin approval", "cloud access"],
        }
    )
    team, requires_action, confidence, criteria = _parse_llm_decision(payload)

    assert team == TargetTeam.INFRA
    assert requires_action is True
    assert confidence == 0.91
    assert criteria == ["needs admin approval", "cloud access"]


def test_parse_llm_decision_accepts_fenced_json_and_string_booleans() -> None:
    content = (
        '```json\n{"target_team": "network_team", "requires_human_action": "false", '
        '"confidence_score": 0.8}\n```'
    )
    team, requires_action, confidence, criteria = _parse_llm_decision(content)

    assert team == TargetTeam.NETWORK
    assert requires_action is False
    assert confidence == 0.8
    assert criteria == []


def test_parse_llm_decision_clamps_confidence_and_limits_criteria() -> None:
    high = _parse_llm_decision(
        json.dumps(
            {
                "target_team": "software_team",
                "requires_human_action": False,
                "confidence_score": 1.7,
                "criteria": [f"reason {index}" for index in range(8)],
            }
        )
    )
    low = _parse_llm_decision(
        '{"target_team": "software_team", "requires_human_action": false, "confidence_score": -3}'
    )

    assert high[2] == 1.0
    assert len(high[3]) == 5
    assert low[2] == 0.0


@pytest.mark.parametrize(
    "content",
    [
        "no json at all",
        '{"target_team": "finance_team", "requires_human_action": false, "confidence_score": 0.5}',
        '{"target_team": "infra_team", "requires_human_action": "yes", "confidence_score": 0.5}',
        '{"target_team": "infra_team", "requires_human_action": true, "confidence_score": true}',
        '{"target_team": "infra_team", "requires_human_action": true}',
    ],
)
def test_parse_llm_decision_rejects_malformed_output(content: str) -> None:
    with pytest.raises((ValueError, KeyError)):
        _parse_llm_decision(content)


def test_service_mode_follows_the_key() -> None:
    assert JEVService().is_live is False
    assert _live_service().is_live is True


async def test_live_mode_uses_the_openrouter_decision() -> None:
    service = _live_service()

    async def fake_call(raw_text: str):
        return TargetTeam.HARDWARE, True, 0.93, ["Needs a purchase", "Peripheral request"]

    service._call_openrouter = fake_call  # type: ignore[method-assign]
    result = await service.classify("I need a new keyboard")

    assert result.engine == ENGINE_OPENROUTER
    assert result.decision.target_team == TargetTeam.HARDWARE
    assert result.decision.requires_human_action is True
    assert result.decision.confidence_score == 0.93
    assert result.queue_label == "Hardware Procurement Queue"
    assert "Needs a purchase" in result.criteria
    assert result.criteria[-1] == "Routed to hardware_team; requires_human_action=true"
    await service.aclose()


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(httpx.ConnectError("boom"), id="connect-error"),
        pytest.param(httpx.ReadTimeout("timeout"), id="timeout"),
        pytest.param(ValueError("bad json"), id="invalid-output"),
        pytest.param(KeyError("choices"), id="missing-key"),
        pytest.param(IndexError("empty"), id="empty-choices"),
    ],
)
async def test_live_failures_fall_back_to_the_simulator(error: Exception) -> None:
    service = _live_service()

    async def failing_call(raw_text: str):
        raise error

    service._call_openrouter = failing_call  # type: ignore[method-assign]
    result = await service.classify(NETWORK_TEXT)

    assert result.engine == ENGINE_SIMULATOR_FALLBACK
    assert result.decision.target_team == TargetTeam.NETWORK
    assert result.decision.requires_human_action is False
    assert any(type(error).__name__ in line for line in result.criteria)
    await service.aclose()


def test_parse_systemone_decision_valid() -> None:
    payload = {
        "model": "typesafe/jev-1.14",
        "answers": {
            "target_team": {
                "type": "choice",
                "choice": "hardware_team",
                "confidence": 0.99,
                "probabilities": {
                    "hardware_team": 0.99,
                    "infra_team": 0.01,
                    "network_team": 0.0,
                    "software_team": 0.0,
                },
            },
            "requires_human_action": {
                "type": "noul",
                "noul": 0.92,
            },
        },
    }
    team, requires_action, confidence, criteria = _parse_systemone_decision(payload)
    assert team == TargetTeam.HARDWARE
    assert requires_action is True
    assert confidence == 0.99
    assert any("TypeSafe JEV 1.14" in c for c in criteria)
    assert any("hardware_team: 0.99" in c for c in criteria)
    assert any("Human action noul probability: 0.92" in c for c in criteria)


def test_parse_systemone_decision_low_noul() -> None:
    payload = {
        "model": "typesafe/jev-1.14",
        "answers": {
            "target_team": {
                "type": "choice",
                "choice": "software_team",
                "confidence": 0.95,
                "probabilities": {
                    "software_team": 0.95,
                    "network_team": 0.05,
                },
            },
            "requires_human_action": {
                "type": "noul",
                "noul": 0.12,
            },
        },
    }
    team, requires_action, confidence, criteria = _parse_systemone_decision(payload)
    assert team == TargetTeam.SOFTWARE
    assert requires_action is False
    assert confidence == 0.95
    assert any("self-service guidance" in c for c in criteria)


def test_parse_systemone_decision_rejects_missing_answers() -> None:
    with pytest.raises(ValueError, match="missing 'target_team'"):
        _parse_systemone_decision({"answers": {"requires_human_action": {"noul": 0.5}}})

    with pytest.raises(ValueError, match="missing 'requires_human_action'"):
        _parse_systemone_decision({"answers": {"target_team": {"choice": "software_team"}}})

