"""Staff dialogue turns and runtime heartbeats."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "a7c4e1b90d22"
down_revision = "f2ee3d9000b1"


def upgrade():
    op.create_table(
        "staff_turns",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("anchor_id", sa.String(160), nullable=False),
        sa.Column("author", sa.String(256), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("basis", JSONB, nullable=False),
        sa.Column("adapter", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('business','fde','engineering','knowledge')",
            name="ck_staff_turn_role",
        ),
        sa.CheckConstraint(
            "adapter IN ('staff','scripted','live')",
            name="ck_staff_turn_adapter",
        ),
    )
    op.create_index(
        "ix_staff_turns_anchor",
        "staff_turns",
        ["role", "anchor_id", "created_at", "id"],
    )
    op.create_table(
        "runtime_beats",
        sa.Column("name", sa.String(64), primary_key=True),
        sa.Column("beat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "name IN ('fde_agent','engineering_worker')",
            name="ck_runtime_beat_name",
        ),
    )


def downgrade():
    op.drop_table("runtime_beats")
    op.drop_index("ix_staff_turns_anchor", table_name="staff_turns")
    op.drop_table("staff_turns")
