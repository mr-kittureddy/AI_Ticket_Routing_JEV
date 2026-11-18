from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import RoutingRule, TargetTeam, User, UserRole
from app.db.session import engine, session_scope

logger = get_logger(__name__)


@dataclass(frozen=True)
class SeedRule:
    """Immutable definition of a routing rule used for seeding and simulator fallback."""

    name: str
    description: str
    target_team: TargetTeam
    requires_human_action: bool
    priority: int
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class SeedUser:
    """Immutable definition of a default RBAC user."""

    email: str
    full_name: str
    role: UserRole


DEFAULT_ROUTING_RULES: tuple[SeedRule, ...] = (
    SeedRule(
        name="infra-access",
        description="Cloud/infrastructure access, IAM and privilege requests that need admin approval.",
        target_team=TargetTeam.INFRA,
        requires_human_action=True,
        priority=90,
        keywords=(
            "grant", "iam", "iam role", "assume role", "read access", "write access",
            "admin access", "access to", "root access", "permission", "permissions",
            "privilege", "privileges", "elevated", "sudo", "s3", "bucket",
            "service account", "ssh key", "revoke",
        ),
    ),
    SeedRule(
        name="hardware-procurement",
        description="Requests to purchase, replace or physically install hardware and peripherals.",
        target_team=TargetTeam.HARDWARE,
        requires_human_action=True,
        priority=80,
        keywords=(
            "need a", "need an", "second", "order", "request a", "upgrade", "replacement",
            "purchase", "buy", "monitor", "usb hub", "docking station", "keyboard", "mouse",
            "headset", "webcam", "laptop", "hdmi", "adapter", "charger", "dongle",
            "external drive", "desk phone",
        ),
    ),
    SeedRule(
        name="software-license",
        description="Software installs, licenses, subscriptions and local admin rights requiring approval.",
        target_team=TargetTeam.SOFTWARE,
        requires_human_action=True,
        priority=70,
        keywords=(
            "license", "licence", "subscription", "purchase software", "install",
            "installation", "admin rights", "local admin", "software request",
            "new software", "upgrade license", "seat", "adobe", "figma", "tableau",
            "visual studio", "intellij", "approve",
        ),
    ),
    SeedRule(
        name="network-change-request",
        description="Network configuration changes that need a network engineer to act or approve.",
        target_team=TargetTeam.NETWORK,
        requires_human_action=True,
        priority=60,
        keywords=(
            "firewall", "whitelist", "allowlist", "open port", "port forwarding", "vlan",
            "static ip", "new vpn account", "vpn access", "vpn account", "ip range",
            "dns record", "subnet", "proxy exception", "new ssid",
        ),
    ),
    SeedRule(
        name="network-troubleshooting",
        description="Connectivity and VPN problems that can be resolved with guided self-service steps.",
        target_team=TargetTeam.NETWORK,
        requires_human_action=False,
        priority=40,
        keywords=(
            "vpn", "globalprotect", "wifi", "wi-fi", "dns", "network", "internet", "connect",
            "connection", "dropping", "disconnect", "latency", "slow internet", "proxy",
            "ping", "timeout", "timed out", "ssid", "ethernet", "packet loss",
        ),
    ),
    SeedRule(
        name="software-howto",
        description="Application how-to and usage questions answerable with step-by-step guidance.",
        target_team=TargetTeam.SOFTWARE,
        requires_human_action=False,
        priority=40,
        keywords=(
            "how do i", "how to", "how can i", "where do i", "where can i", "tutorial",
            "export", "import", "excel", "word", "powerpoint", "outlook", "teams", "slack",
            "zoom", "jira", "confluence", "sharepoint", "onedrive", "chrome", "browser",
            "shortcut", "spreadsheet",
        ),
    ),
    SeedRule(
        name="hardware-troubleshooting",
        description="Peripheral and device faults that can be diagnosed with guided self-service steps.",
        target_team=TargetTeam.HARDWARE,
        requires_human_action=False,
        priority=30,
        keywords=(
            "not working", "won't turn on", "wont turn on", "won't boot", "flicker",
            "flickering", "no display", "black screen", "blue screen", "overheating",
            "battery", "frozen", "broken", "cracked", "noisy", "fan", "monitor", "keyboard",
            "mouse", "laptop", "headset", "webcam", "printer", "scanner", "not detected",
            "not charging",
        ),
    ),
    SeedRule(
        name="infra-diagnostics",
        description="Infrastructure and cloud diagnostics questions answerable with guided steps.",
        target_team=TargetTeam.INFRA,
        requires_human_action=False,
        priority=20,
        keywords=(
            "server", "kubernetes", "k8s", "pod", "docker", "container", "pipeline", "ci/cd",
            "build failing", "deployment", "deploy", "aws", "gcp", "azure", "cloud",
            "database", "disk space", "cpu", "memory", "logs", "monitoring", "outage",
        ),
    ),
)

DEFAULT_USERS: tuple[SeedUser, ...] = (
    SeedUser(email="admin@company.com", full_name="Platform Admin", role=UserRole.ADMIN),
    SeedUser(email="agent@company.com", full_name="Support Agent", role=UserRole.AGENT),
    SeedUser(email="viewer@company.com", full_name="Dashboard Viewer", role=UserRole.VIEWER),
    SeedUser(email="user@company.com", full_name="Sample Requester", role=UserRole.VIEWER),
)


def seed_routing_rules(session: Session) -> int:
    """Inserts any missing default routing rules; existing rows are never overwritten."""
    existing_names = set(session.scalars(select(RoutingRule.name)).all())
    created = 0
    for rule in DEFAULT_ROUTING_RULES:
        if rule.name in existing_names:
            continue
        session.add(
            RoutingRule(
                name=rule.name,
                description=rule.description,
                target_team=rule.target_team,
                requires_human_action=rule.requires_human_action,
                keywords=list(rule.keywords),
                priority=rule.priority,
                is_active=True,
            )
        )
        created += 1
    session.flush()
    return created


def seed_users(session: Session) -> int:
    """Inserts any missing default users; existing rows are never overwritten."""
    existing_emails = set(session.scalars(select(User.email)).all())
    created = 0
    for user in DEFAULT_USERS:
        if user.email in existing_emails:
            continue
        session.add(User(email=user.email, full_name=user.full_name, role=user.role, is_active=True))
        created += 1
    session.flush()
    return created


def seed_database(session: Session) -> dict[str, int]:
    """Seeds rules and users within the caller's session and returns insert counts."""
    return {
        "routing_rules_created": seed_routing_rules(session),
        "users_created": seed_users(session),
    }


def ensure_tables_exist() -> None:
    """Raises a clear error when migrations have not been applied yet."""
    existing_tables = set(inspect(engine).get_table_names())
    required_tables = {"routing_rules", "users"}
    missing = required_tables - existing_tables
    if missing:
        raise RuntimeError(
            f"Database is missing tables {sorted(missing)}. Run 'alembic upgrade head' from the backend directory first."
        )


def run_seed() -> dict[str, int]:
    """Opens its own transactional session, seeds the database and returns insert counts."""
    ensure_tables_exist()
    with session_scope() as session:
        result = seed_database(session)
    logger.info("Database seed completed", extra=result)
    return result


def main() -> None:
    """CLI entry point: python -m app.db.seed"""
    result = run_seed()
    print(
        f"Seed complete: {result['routing_rules_created']} routing rules and "
        f"{result['users_created']} users created."
    )


if __name__ == "__main__":
    main()
