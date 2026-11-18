from __future__ import annotations

from enum import Enum
from typing import Any, Optional, Union

from sqlalchemy.orm import Session

from app.core.logging import get_logger, request_id_ctx
from app.db.models import AuditLog
from app.db.session import session_scope
from app.services.rbac import Principal

logger = get_logger(__name__)

MAX_STRING_CHARS = 500
MAX_COLLECTION_ITEMS = 50
MAX_DEPTH = 4
MAX_KEY_CHARS = 100
REDACTED = "[REDACTED]"
_SENSITIVE_KEY_FRAGMENTS = ("key", "token", "password", "secret", "authorization", "credential")


class AuditAction(str, Enum):
    TICKET_PROCESSED = "ticket.processed"
    TICKET_DUPLICATE_REJECTED = "ticket.duplicate_rejected"
    TICKET_PROCESSING_FAILED = "ticket.processing_failed"
    TICKETS_LISTED = "tickets.listed"
    TICKET_TRACE_VIEWED = "ticket.trace_viewed"
    ANALYTICS_VIEWED = "analytics.viewed"
    REPORT_EXPORTED = "report.exported"


class AuditEntity(str, Enum):
    TICKET = "ticket"
    TICKET_COLLECTION = "ticket_collection"
    ANALYTICS = "analytics"
    REPORT = "report"


def _truncate(value: str) -> str:
    return value if len(value) <= MAX_STRING_CHARS else value[: MAX_STRING_CHARS - 1] + "\u2026"


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS)


def _sanitize(value: Any, depth: int = 0) -> Any:
    """Converts a value to bounded, JSON-safe data: enums unwrapped, strings truncated, secrets redacted."""
    if isinstance(value, Enum):
        return _sanitize(value.value, depth)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _truncate(value)
    if depth >= MAX_DEPTH:
        return _truncate(str(value))
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for raw_key, raw_value in list(value.items())[:MAX_COLLECTION_ITEMS]:
            key = str(raw_key)[:MAX_KEY_CHARS]
            sanitized[key] = REDACTED if _is_sensitive_key(key) else _sanitize(raw_value, depth + 1)
        return sanitized
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_sanitize(item, depth + 1) for item in list(value)[:MAX_COLLECTION_ITEMS]]
    return _truncate(str(value))


def _enum_value(value: Union[Enum, str]) -> str:
    return value.value if isinstance(value, Enum) else str(value)


def record_audit(
    db: Session,
    *,
    actor: str,
    role: str,
    action: Union[AuditAction, str],
    entity_type: Union[AuditEntity, str],
    entity_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> AuditLog:
    """Adds an audit row to the caller's session and flushes it; the caller owns the commit."""
    entry = AuditLog(
        actor=actor[:320],
        role=role[:32],
        action=_enum_value(action)[:64],
        entity_type=_enum_value(entity_type)[:64],
        entity_id=entity_id[:128] if entity_id else None,
        details=_sanitize(details or {}),
        request_id=(request_id_ctx.get() or "-")[:64],
    )
    db.add(entry)
    db.flush()
    return entry


def record_audit_for_principal(
    db: Session,
    principal: Principal,
    *,
    action: Union[AuditAction, str],
    entity_type: Union[AuditEntity, str],
    entity_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> AuditLog:
    """Convenience wrapper that takes the actor and role from the resolved request principal."""
    return record_audit(
        db,
        actor=principal.email,
        role=principal.role_name,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )


def record_audit_best_effort(
    principal: Principal,
    *,
    action: Union[AuditAction, str],
    entity_type: Union[AuditEntity, str],
    entity_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> bool:
    """Writes an audit row in its own transaction; logs and returns False instead of raising.

    Used for failure and rejection events recorded while the request's own transaction is rolled back.
    """
    try:
        with session_scope() as session:
            record_audit_for_principal(
                session,
                principal,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                details=details,
            )
        return True
    except Exception:  # noqa: BLE001 - audit failures on error paths must never mask the original error
        logger.exception("Best-effort audit write failed", extra={"audit_action": _enum_value(action)})
        return False
