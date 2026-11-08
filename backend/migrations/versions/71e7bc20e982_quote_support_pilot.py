"""Durable quote support pilot enrollment and progress."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "71e7bc20e982"
down_revision = "f3afd81339dd"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fde_quote_support",
        sa.Column(
            "case_id", sa.Uuid(), sa.ForeignKey("business_cases.id"), primary_key=True
        ),
        sa.Column(
            "engagement_id", sa.Uuid(), sa.ForeignKey("engagements.id"), nullable=False
        ),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("model_profile_revisions.revision_id"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("source", postgresql.JSONB(), nullable=False),
        sa.Column("progress", postgresql.JSONB(), nullable=False),
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM fde_quote_support)")):
        raise RuntimeError(
            "Quote support enrollments exist; preserve them with a forward migration"
        )
    op.drop_table("fde_quote_support")
