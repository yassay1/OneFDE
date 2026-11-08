"""Allow model-free verification Runs.

Revision ID: b91f643af772
Revises: 71e7bc20e982
"""

import sqlalchemy as sa
from alembic import op

revision = "b91f643af772"
down_revision = "71e7bc20e982"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "runs", "model_profile_revision_id", existing_type=sa.Uuid(), nullable=True
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM runs WHERE model_profile_revision_id IS NULL)"
        )
    ):
        raise RuntimeError(
            "Model-free Run history exists; preserve it with a forward migration"
        )
    op.alter_column(
        "runs", "model_profile_revision_id", existing_type=sa.Uuid(), nullable=False
    )
