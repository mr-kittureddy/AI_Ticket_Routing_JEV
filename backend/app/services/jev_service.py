from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional, Sequence

import httpx

from app.core.logging import get_logger
from app.core.settings import Settings, settings
from app.db.models import RoutingRule, TargetTeam
from app.db.seed import DEFAULT_ROUTING_RULES, SeedRule
from app.schemas.ticket import JEVDecision

logger = get_logger(__name__)

ENGINE_OPENROUTER = "openrouter"
ENGINE_SIMULATOR = "simulator"
ENGINE_SIMULATOR_FALLBACK = "simulator-fallback"

DEFAULT_TEAM = TargetTeam.SOFTWARE
DEFAULT_CONFIDENCE = 0.35
MAX_LLM_INPUT_CHARS = 2000
MAX_LLM_CRITERIA = 5

HUMAN_QUEUE_LABELS: dict[TargetTeam, str] = {
    TargetTeam.HARDWARE: "Hardware Procurement Queue",
    TargetTeam.INFRA: "Infrastructure Access Queue",
    TargetTeam.SOFTWARE: "Software License Queue",
    TargetTeam.NETWORK: "Network Change Request Queue",
}

SYSTEMONE_QUESTIONS = {
    "target_team": {
        "type": "choice",
        "instructions": "Which IT department team should handle this ticket?",
        "criteria": {
            "hardware_team": "Device procurement, laptop replacement, monitors, docks, keyboards, mice, cables, and peripherals",
            "infra_team": "Cloud infrastructure (AWS/GCP/Azure), servers, Kubernetes, databases, IAM permissions, access requests",
            "network_team": "VPN (GlobalProtect), Wi-Fi, DNS, network drops, latency, firewalls, ports, and network connectivity",
            "software_team": "Desktop and SaaS applications, Jira, Excel, office tools, usage questions, how-to guides",
        },
    },
    "requires_human_action": {
        "type": "noul",
        "instructions": (
            "Does this request require administrative approval, access/permission provisioning, "
            "or physical hardware action that cannot be self-served?"
        ),
        "criteria": {
            "true": "Granting IAM roles or permissions, S3 bucket access, sudo/root rights, purchase orders, or physical hardware replacement.",
            "false": "Troubleshooting errors, informational how-to steps, software guidance, or self-service configuration.",
        },
    },
}

_SYSTEM_PROMPT = (
    "You are JEV, a deterministic IT support ticket router. Classify the ticket and respond with "
    "ONE JSON object and nothing else, using exactly these keys:\n"
    '{"target_team": "infra_team|network_team|hardware_team|software_team", '
    '"requires_human_action": true|false, "confidence_score": 0.0-1.0, '
    '"criteria": ["short reason", "short reason"]}\n'
    "Team guide: infra_team = cloud, servers, IAM and access; network_team = VPN, Wi-Fi, DNS, "
    "firewall; hardware_team = devices and peripherals; software_team = applications, how-to "
    "questions, licenses.\n"
    "requires_human_action is true ONLY if a purchase, a physical installation, or an "
    "administrative privilege/approval is required (for example new hardware, IAM or permission "
    "grants, license purchases). It is false when the ticket can be resolved with informational "
    "step-by-step guidance.\n"
    "criteria must contain 2 to 4 concise strings explaining the decision."
)



@dataclass(frozen=True)
class RoutingRuleDef:
    """Immutable, database-independent view of a routing rule used by the simulator."""

    name: str
    description: str
    target_team: TargetTeam
    requires_human_action: bool
    priority: int
    keywords: tuple[str, ...]

    @classmethod
    def from_model(cls, rule: RoutingRule) -> "RoutingRuleDef":
        return cls(
            name=rule.name,
            description=rule.description or "",
            target_team=rule.target_team,
            requires_human_action=rule.requires_human_action,
            priority=rule.priority,
            keywords=tuple(str(keyword) for keyword in (rule.keywords or [])),
        )

    @classmethod
    def from_seed(cls, rule: SeedRule) -> "RoutingRuleDef":
        return cls(
            name=rule.name,
            description=rule.description,
            target_team=rule.target_team,
            requires_human_action=rule.requires_human_action,
            priority=rule.priority,
            keywords=tuple(rule.keywords),
        )


def default_rule_definitions() -> list[RoutingRuleDef]:
    """Rule definitions built from the seed defaults (used when the database has no active rules)."""
    return [RoutingRuleDef.from_seed(rule) for rule in DEFAULT_ROUTING_RULES]


def rule_definitions_from_models(models: Sequence[RoutingRule]) -> list[RoutingRuleDef]:
    """Converts active ORM rules to definitions, falling back to defaults when none are active."""
    active = [RoutingRuleDef.from_model(rule) for rule in models if rule.is_active]
    return active if active else default_rule_definitions()


def queue_label_for(team: TargetTeam, requires_human_action: bool) -> Optional[str]:
    """Human queue name for a routed ticket; None when no human action is needed."""
    if not requires_human_action:
        return None
    return HUMAN_QUEUE_LABELS[team]


@dataclass(frozen=True)
class JEVResult:
    """Full outcome of one JEV classification, including the PRD §4.2 decision."""

    decision: JEVDecision
    engine: str
    criteria: list[str]
    matched_rule: Optional[str]
    queue_label: Optional[str]
    within_threshold: bool


def _normalize(text: str) -> str:
    cleaned = text.lower().replace("\u2019", "'").replace("\u2018", "'")
    return re.sub(r"\s+", " ", cleaned).strip()


@lru_cache(maxsize=2048)
def _keyword_pattern(keyword: str) -> re.Pattern[str]:
    return re.compile(r"(?<![a-z0-9])" + re.escape(keyword.lower()) + r"(?![a-z0-9])")


def _extract_json_object(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("Model response did not contain a JSON object")
    parsed = json.loads(cleaned[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Model response JSON was not an object")
    return parsed


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    raise ValueError("requires_human_action must be a boolean")


def _parse_legacy_llm_decision(parsed: dict[str, Any]) -> tuple[TargetTeam, bool, float, list[str]]:
    team = TargetTeam(str(parsed["target_team"]).strip())
    requires_human_action = _coerce_bool(parsed["requires_human_action"])
    raw_confidence = parsed["confidence_score"]
    if isinstance(raw_confidence, bool):
        raise ValueError("confidence_score must be numeric")
    confidence = round(min(1.0, max(0.0, float(raw_confidence))), 2)
    raw_criteria = parsed.get("criteria")
    criteria: list[str] = []
    if isinstance(raw_criteria, list):
        criteria = [str(item).strip() for item in raw_criteria if str(item).strip()][:MAX_LLM_CRITERIA]
    return team, requires_human_action, confidence, criteria


def _parse_systemone_decision(content_or_obj: Any) -> tuple[TargetTeam, bool, float, list[str]]:
    """Parses TypeSafe JEV 1.14 System One decision responses, with legacy JSON fallback."""
    if isinstance(content_or_obj, str):
        parsed = _extract_json_object(content_or_obj)
    elif isinstance(content_or_obj, dict):
        parsed = content_or_obj
    else:
        raise ValueError("Invalid System One response data")

    if "answers" in parsed:
        answers = parsed["answers"]
        if not isinstance(answers, dict):
            raise ValueError("System One response 'answers' must be a dictionary")

        team_entry = answers.get("target_team")
        if not team_entry:
            raise ValueError("System One response missing 'target_team'")
        if isinstance(team_entry, dict):
            team_val = team_entry.get("choice") or team_entry.get("selection") or team_entry.get("value")
            raw_conf = team_entry.get("confidence", 0.95)
            probabilities = team_entry.get("probabilities", {})
        else:
            team_val = str(team_entry)
            raw_conf = 0.95
            probabilities = {}

        team = TargetTeam(str(team_val).strip())
        confidence = round(min(1.0, max(0.0, float(raw_conf))), 2)

        human_entry = answers.get("requires_human_action")
        if human_entry is None:
            raise ValueError("System One response missing 'requires_human_action'")
        if isinstance(human_entry, dict):
            noul_val = human_entry.get("noul", human_entry.get("probability", human_entry.get("value", 0.0)))
            noul_prob = float(noul_val)
        elif isinstance(human_entry, (int, float)):
            noul_prob = float(human_entry)
        elif isinstance(human_entry, bool):
            noul_prob = 1.0 if human_entry else 0.0
        else:
            raise ValueError("Invalid noul format for requires_human_action")

        requires_human_action = noul_prob >= 0.5

        criteria: list[str] = [
            f"TypeSafe JEV 1.14 System One choice: {team.value} ({confidence:.0%} confidence)",
        ]
        if probabilities and isinstance(probabilities, dict):
            sorted_probs = sorted(probabilities.items(), key=lambda x: x[1], reverse=True)
            prob_parts = [f"{k}: {v:.2f}" if isinstance(v, (int, float)) else f"{k}: {v}" for k, v in sorted_probs]
            criteria.append(f"Team probability distribution: {', '.join(prob_parts)}")

        criteria.append(
            f"Human action noul probability: {noul_prob:.2f} -> "
            + (
                "a purchase, physical install, or admin privilege is required"
                if requires_human_action
                else "resolvable with informational self-service guidance"
            )
        )
        return team, requires_human_action, confidence, criteria

    return _parse_legacy_llm_decision(parsed)


def _parse_llm_decision(content: str) -> tuple[TargetTeam, bool, float, list[str]]:
    """Backward-compatible entry point for tests and callers."""
    return _parse_systemone_decision(content)


class JEVService:
    """Sub-100ms-targeted ticket classifier with live OpenRouter and deterministic simulator modes."""

    def __init__(self, cfg: Settings = settings) -> None:
        self._cfg = cfg
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def is_live(self) -> bool:
        """True when a real OpenRouter key is configured."""
        return not self._cfg.is_openrouter_masked

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            origins = self._cfg.CORS_ORIGINS
            limits = httpx.Limits(
                max_keepalive_connections=20,
                max_connections=50,
                keepalive_expiry=120.0,
            )
            self._client = httpx.AsyncClient(
                base_url=self._cfg.OPENROUTER_BASE_URL.rstrip("/"),
                timeout=httpx.Timeout(self._cfg.OPENROUTER_TIMEOUT_SECONDS),
                limits=limits,
                headers={
                    "Authorization": f"Bearer {self._cfg.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": origins[0] if origins else "http://localhost:5173",
                    "X-Title": "IT Support Ticket AI Router",
                },
            )
        return self._client

    async def warmup(self) -> None:
        """Pre-warms the HTTP client connection pool on startup to eliminate cold TLS handshake latency."""
        if not self.is_live:
            return
        try:
            client = self._get_client()
            await client.get("/models", timeout=3.0)
            logger.info("JEV connection pool pre-warmed")
        except Exception:
            logger.debug("JEV client pre-warming finished")

    async def aclose(self) -> None:
        """Releases the pooled HTTP client on application shutdown."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    @staticmethod
    def _elapsed_ms(start: float) -> int:
        return max(1, int(round((time.perf_counter() - start) * 1000)))

    def _within_threshold(self, latency_ms: int) -> bool:
        return latency_ms < self._cfg.JEV_LATENCY_THRESHOLD_MS

    async def _call_openrouter(self, raw_text: str) -> tuple[TargetTeam, bool, float, list[str]]:
        payload = {
            "model": self._cfg.OPENROUTER_MODEL,
            "state": raw_text.strip()[:MAX_LLM_INPUT_CHARS],
            "questions": SYSTEMONE_QUESTIONS,
        }
        response = await self._get_client().post("/systemone", json=payload)
        response.raise_for_status()
        return _parse_systemone_decision(response.json())

    def _simulate(
        self,
        raw_text: str,
        rules: Sequence[RoutingRuleDef],
        engine: str,
        notes: Sequence[str],
    ) -> JEVResult:
        """Deterministic keyword-evidence classifier reproducing the JEV decision contract."""
        start = time.perf_counter()
        text = _normalize(raw_text)

        scored: list[tuple[int, int, RoutingRuleDef, list[str]]] = []
        for rule in rules:
            matched = [keyword for keyword in rule.keywords if _keyword_pattern(keyword).search(text)]
            if matched:
                scored.append((len(matched), rule.priority, rule, matched))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)

        matched_rule: Optional[str]
        criteria: list[str]
        if scored:
            best_score, _, best_rule, matched_keywords = scored[0]
            total_evidence = sum(item[0] for item in scored)
            share = best_score / total_evidence
            evidence = min(1.0, best_score / 4)
            confidence = round(min(0.99, 0.55 + 0.25 * share + 0.2 * evidence), 2)
            team = best_rule.target_team
            requires_human_action = best_rule.requires_human_action
            matched_rule = best_rule.name
            criteria = [
                f"Matched rule '{best_rule.name}': {best_rule.description}",
                f"Keyword evidence ({best_score}): {', '.join(matched_keywords)}",
                f"Rule routes to {team.value}; "
                + (
                    "a purchase, physical install, or admin privilege is required"
                    if requires_human_action
                    else "resolvable with informational guidance"
                ),
                f"Confidence {confidence:.2f} from {share:.0%} of total keyword evidence",
            ]
            if len(scored) > 1:
                runner_up = scored[1]
                criteria.append(f"Runner-up rule '{runner_up[2].name}' with {runner_up[0]} keyword hit(s)")
        else:
            team = DEFAULT_TEAM
            requires_human_action = False
            confidence = DEFAULT_CONFIDENCE
            matched_rule = None
            criteria = [
                f"No routing keywords matched; defaulted to {DEFAULT_TEAM.value} with self-service guidance"
            ]

        latency_ms = self._elapsed_ms(start)
        decision = JEVDecision(
            target_team=team,
            requires_human_action=requires_human_action,
            confidence_score=confidence,
            jev_latency_ms=latency_ms,
        )
        return JEVResult(
            decision=decision,
            engine=engine,
            criteria=[*criteria, *notes],
            matched_rule=matched_rule,
            queue_label=queue_label_for(team, requires_human_action),
            within_threshold=self._within_threshold(latency_ms),
        )

    async def classify(
        self,
        raw_text: str,
        rules: Optional[Sequence[RoutingRuleDef]] = None,
    ) -> JEVResult:
        """Classifies a ticket via OpenRouter, or via the simulator when keys are masked or the call fails."""
        rule_defs = list(rules) if rules else default_rule_definitions()

        if not self.is_live:
            return self._simulate(
                raw_text,
                rule_defs,
                ENGINE_SIMULATOR,
                ["OpenRouter API key is masked or missing; deterministic rule engine in use"],
            )

        start = time.perf_counter()
        try:
            team, requires_human_action, confidence, model_criteria = await self._call_openrouter(raw_text)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            logger.warning(
                "OpenRouter classification failed; using deterministic rule engine",
                extra={"error_type": type(exc).__name__},
            )
            return self._simulate(
                raw_text,
                rule_defs,
                ENGINE_SIMULATOR_FALLBACK,
                [f"OpenRouter call failed ({type(exc).__name__}); deterministic rule engine used"],
            )

        latency_ms = self._elapsed_ms(start)
        decision = JEVDecision(
            target_team=team,
            requires_human_action=requires_human_action,
            confidence_score=confidence,
            jev_latency_ms=latency_ms,
        )
        criteria = [
            f"Classified by {self._cfg.OPENROUTER_MODEL} via OpenRouter",
            *model_criteria,
            f"Routed to {team.value}; requires_human_action={str(requires_human_action).lower()}",
        ]
        return JEVResult(
            decision=decision,
            engine=ENGINE_OPENROUTER,
            criteria=criteria,
            matched_rule=None,
            queue_label=queue_label_for(team, requires_human_action),
            within_threshold=self._within_threshold(latency_ms),
        )


_jev_service: Optional[JEVService] = None


def get_jev_service() -> JEVService:
    """Returns the process-wide JEV service so the pooled HTTP client is reused across requests."""
    global _jev_service
    if _jev_service is None:
        _jev_service = JEVService()
    return _jev_service
