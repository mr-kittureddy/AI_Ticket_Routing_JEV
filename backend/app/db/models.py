from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    """Timezone-aware current UTC time used for all timestamp defaults."""
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    AGENT = "agent"
    VIEWER = "viewer"


class TargetTeam(str, enum.Enum):
    INFRA = "infra_team"
    NETWORK = "network_team"
    HARDWARE = "hardware_team"
    SOFTWARE = "software_team"


class ResolutionStatus(str, enum.Enum):
    AUTO_RESOLVED = "AUTO_RESOLVED"
    ASSIGNED_TO_HUMAN = "ASSIGNED_TO_HUMAN"


def _string_enum(enum_cls: type[enum.Enum], length: int) -> SAEnum:
    """Stores enum values as plain VARCHAR so SQLite and PostgreSQL behave identically."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=length,
        create_constraint=False,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[UserRole] = mapped_column(_string_enum(UserRole, 16), nullable=False, default=UserRole.VIEWER)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class RoutingRule(Base):
    __tablename__ = "routing_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    target_team: Mapped[TargetTeam] = mapped_column(_string_enum(TargetTeam, 32), nullable=False)
    requires_human_action: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_by: Mapped[str] = mapped_column(String(320), index=True, nullable=False)

    target_team: Mapped[TargetTeam] = mapped_column(_string_enum(TargetTeam, 32), index=True, nullable=False)
    requires_human_action: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    jev_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[ResolutionStatus] = mapped_column(_string_enum(ResolutionStatus, 32), index=True, nullable=False)
    handled_by: Mapped[str] = mapped_column(String(64), nullable=False)
    assigned_queue: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    response_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gemini_execution_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    routing_logs: Mapped[list["RoutingLog"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="RoutingLog.created_at",
    )


class RoutingLog(Base):
    __tablename__ = "routing_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_pk: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), index=True, nullable=False
    )

    jev_engine: Mapped[str] = mapped_column(String(32), nullable=False)
    gemini_engine: Mapped[str] = mapped_column(String(32), nullable=False)
    jev_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    gemini_execution_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    jev_within_threshold: Mapped[bool] = mapped_column(Boolean, nullable=False)
    gemini_bypassed: Mapped[bool] = mapped_column(Boolean, nullable=False)

    time_saved_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_saved_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    decision_criteria: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    rag_sources: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False, default=utc_now)

    ticket: Mapped["Ticket"] = relationship(back_populates="routing_logs")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, default="-")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False, default=utc_now)
