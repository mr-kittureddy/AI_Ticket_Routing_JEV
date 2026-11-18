"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-07 00:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "routing_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("target_team", sa.String(length=32), nullable=False),
        sa.Column("requires_human_action", sa.Boolean(), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_routing_rules")),
    )
    op.create_index(op.f("ix_routing_rules_name"), "routing_rules", ["name"], unique=True)

    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.String(length=64), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("submitted_by", sa.String(length=320), nullable=False),
        sa.Column("target_team", sa.String(length=32), nullable=False),
        sa.Column("requires_human_action", sa.Boolean(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("jev_latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("handled_by", sa.String(length=64), nullable=False),
        sa.Column("assigned_queue", sa.String(length=128), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("gemini_execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tickets")),
    )
    op.create_index(op.f("ix_tickets_ticket_id"), "tickets", ["ticket_id"], unique=True)
    op.create_index(op.f("ix_tickets_submitted_by"), "tickets", ["submitted_by"], unique=False)
    op.create_index(op.f("ix_tickets_target_team"), "tickets", ["target_team"], unique=False)
    op.create_index(op.f("ix_tickets_status"), "tickets", ["status"], unique=False)
    op.create_index(op.f("ix_tickets_created_at"), "tickets", ["created_at"], unique=False)

    op.create_table(
        "routing_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticket_pk", sa.Integer(), nullable=False),
        sa.Column("jev_engine", sa.String(length=32), nullable=False),
        sa.Column("gemini_engine", sa.String(length=32), nullable=False),
        sa.Column("jev_latency_ms", sa.Integer(), nullable=False),
        sa.Column("gemini_execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("jev_within_threshold", sa.Boolean(), nullable=False),
        sa.Column("gemini_bypassed", sa.Boolean(), nullable=False),
        sa.Column("time_saved_ms", sa.Integer(), nullable=False),
        sa.Column("cost_saved_usd", sa.Float(), nullable=False),
        sa.Column("decision_criteria", sa.JSON(), nullable=False),
        sa.Column("rag_sources", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ticket_pk"],
            ["tickets.id"],
            name=op.f("fk_routing_logs_ticket_pk_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_routing_logs")),
    )
    op.create_index(op.f("ix_routing_logs_ticket_pk"), "routing_logs", ["ticket_pk"], unique=False)
    op.create_index(op.f("ix_routing_logs_created_at"), "routing_logs", ["created_at"], unique=False)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("actor", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(op.f("ix_audit_logs_actor"), "audit_logs", ["actor"], unique=False)
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"], unique=False)
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_logs_created_at"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_action"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor"), table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index(op.f("ix_routing_logs_created_at"), table_name="routing_logs")
    op.drop_index(op.f("ix_routing_logs_ticket_pk"), table_name="routing_logs")
    op.drop_table("routing_logs")

    op.drop_index(op.f("ix_tickets_created_at"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_status"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_target_team"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_submitted_by"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_ticket_id"), table_name="tickets")
    op.drop_table("tickets")

    op.drop_index(op.f("ix_routing_rules_name"), table_name="routing_rules")
    op.drop_table("routing_rules")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
