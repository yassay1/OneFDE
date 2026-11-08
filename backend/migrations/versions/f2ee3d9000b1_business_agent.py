"""Durable Business Agent grants, cursors and model receipts."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "f2ee3d9000b1"
down_revision = "ce99d539d71a"


def upgrade():
    op.create_table(
        "business_agent_grants",
        sa.Column("case_id", sa.Uuid(), primary_key=True),
        sa.Column("engagement_id", sa.Uuid(), sa.ForeignKey("engagements.id")),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("model_profile_revisions.revision_id"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy", JSONB, nullable=False),
        sa.Column("progress", JSONB, nullable=False),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
    )


def downgrade():
    op.drop_table("business_agent_grants")
