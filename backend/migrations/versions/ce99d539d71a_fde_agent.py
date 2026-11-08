"""Persist FDE work, leases and demo grants."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "ce99d539d71a"
down_revision = "b91f643af772"


def upgrade():
    op.create_table(
        "fde_agent_work",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "engagement_id", sa.Uuid(), sa.ForeignKey("engagements.id"), nullable=False
        ),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("business_cases.id")),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("tasks.id"), unique=True),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed", JSONB),
        sa.Column("completed", JSONB),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("report", JSONB, nullable=False),
        sa.Column("trace", JSONB, nullable=False),
        sa.Column("calls", sa.Integer(), nullable=False),
        sa.Column("usage", JSONB, nullable=False),
    )
    op.create_index(
        "ix_fde_agent_work_engagement_id", "fde_agent_work", ["engagement_id"]
    )
    op.create_index("ix_fde_agent_work_case_id", "fde_agent_work", ["case_id"])
    op.create_table(
        "fde_agent_grants",
        sa.Column(
            "work_id", sa.Uuid(), sa.ForeignKey("fde_agent_work.id"), primary_key=True
        ),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("model_profile_revisions.revision_id"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy", JSONB, nullable=False),
        sa.Column("sent", sa.Integer(), nullable=False),
        sa.Column("runs", JSONB, nullable=False),
    )


def downgrade():
    op.drop_table("fde_agent_grants")
    op.drop_table("fde_agent_work")
