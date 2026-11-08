"""business conversations and candidates

Revision ID: f3afd81339dd
Revises: d5454eda0523
Create Date: 2026-11-05 15:15:18.546812

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f3afd81339dd"
down_revision: Union[str, Sequence[str], None] = "d5454eda0523"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "business_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("adcode", sa.String(length=6), nullable=False),
        sa.Column("poi_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("queried_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invited_by", sa.String(length=128), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "business_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("workflow", sa.String(length=24), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("owner", sa.String(length=24), nullable=False),
        sa.Column("handler", sa.String(length=128), nullable=True),
        sa.Column("next_step", sa.Text(), nullable=False),
        sa.Column("engagement_id", sa.Uuid(), nullable=True),
        sa.Column("reported_version", sa.String(length=128), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column(
            "handoff",
            postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "retest",
            postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("invitation_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["engagement_id"],
            ["engagements.id"],
        ),
        sa.ForeignKeyConstraint(
            ["invitation_id"],
            ["business_candidates.id"],
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_business_cases_created_at"),
        "business_cases",
        ["created_at"],
        unique=False,
    )
    op.create_table(
        "business_messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("author", sa.String(length=160), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "reference",
            postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["business_cases.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "request_id"),
    )
    op.create_index(
        op.f("ix_business_messages_case_id"),
        "business_messages",
        ["case_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade only before Business facts have been recorded."""
    for table in ("business_cases", "business_candidates"):
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")):
            raise RuntimeError(
                "Business records exist; preserve them with a forward migration"
            )
    op.drop_index(op.f("ix_business_messages_case_id"), table_name="business_messages")
    op.drop_table("business_messages")
    op.drop_index(op.f("ix_business_cases_created_at"), table_name="business_cases")
    op.drop_table("business_cases")
    op.drop_table("business_candidates")
