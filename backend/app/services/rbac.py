from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.db.models import User, UserRole
from app.db.session import get_db

ANONYMOUS_EMAIL = "anonymous"
ANONYMOUS_ROLE_NAME = "anonymous"


class Permission(str, Enum):
    TICKETS_PROCESS = "tickets:process"
    TICKETS_READ = "tickets:read"
    ANALYTICS_READ = "analytics:read"
    REPORTS_EXPORT = "reports:export"


ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.VIEWER: frozenset({Permission.TICKETS_READ, Permission.ANALYTICS_READ}),
    UserRole.AGENT: frozenset(
        {
            Permission.TICKETS_READ,
            Permission.ANALYTICS_READ,
            Permission.TICKETS_PROCESS,
            Permission.REPORTS_EXPORT,
        }
    ),
    UserRole.ADMIN: frozenset(Permission),
}


@dataclass(frozen=True)
class Principal:
    """The resolved caller of a request; anonymous when no known user was identified."""

    email: str
    role: Optional[UserRole]
    user_id: Optional[int]

    @property
    def is_anonymous(self) -> bool:
        return self.role is None

    @property
    def role_name(self) -> str:
        return self.role.value if self.role is not None else ANONYMOUS_ROLE_NAME

    def has(self, permission: Permission) -> bool:
        """True when the principal's role grants the permission; anonymous principals never do."""
        if self.role is None:
            return False
        return permission in ROLE_PERMISSIONS[self.role]


ANONYMOUS_PRINCIPAL = Principal(email=ANONYMOUS_EMAIL, role=None, user_id=None)


def _lookup_principal(db: Session, raw_email: Optional[str]) -> Optional[Principal]:
    """Resolves an active user by email; returns None when the header is blank or the user is unknown/inactive."""
    if raw_email is None:
        return None
    email = raw_email.strip().lower()
    if not email:
        return None
    user = db.scalars(select(User).where(User.email == email, User.is_active.is_(True))).first()
    if user is None:
        return None
    return Principal(email=user.email, role=user.role, user_id=user.id)


def get_optional_principal(
    x_user_email: Optional[str] = Header(default=None, alias="X-User-Email"),
    db: Session = Depends(get_db),
) -> Principal:
    """Resolves the caller from X-User-Email, falling back to the anonymous principal.

    This is prototype-grade identification (the PRD specifies no authentication); the header is not
    cryptographically verified. Production deployments must replace it with verified tokens (OIDC/JWT).
    """
    principal = _lookup_principal(db, x_user_email)
    return principal if principal is not None else ANONYMOUS_PRINCIPAL


def get_authenticated_principal(principal: Principal = Depends(get_optional_principal)) -> Principal:
    """Requires a known, active user; raises 401 otherwise."""
    if principal.is_anonymous:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A known user is required. Send the X-User-Email header of an active user.",
        )
    return principal


def require_permission(permission: Permission) -> Callable[..., Principal]:
    """Builds a dependency that requires an authenticated user holding the given permission."""

    def dependency(principal: Principal = Depends(get_authenticated_principal)) -> Principal:
        if not principal.has(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{principal.role_name}' lacks the '{permission.value}' permission.",
            )
        return principal

    return dependency


def process_ticket_access(principal: Principal = Depends(get_optional_principal)) -> Principal:
    """Access check for POST /api/process-ticket.

    Open by default, matching the PRD's no-auth prototype flow. When ENFORCE_RBAC_ON_PROCESS_TICKET
    is true, a known user holding the tickets:process permission is required.
    """
    if not settings.ENFORCE_RBAC_ON_PROCESS_TICKET:
        return principal
    if principal.is_anonymous:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A known user is required. Send the X-User-Email header of an active user.",
        )
    if not principal.has(Permission.TICKETS_PROCESS):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{principal.role_name}' lacks the '{Permission.TICKETS_PROCESS.value}' permission.",
        )
    return principal
