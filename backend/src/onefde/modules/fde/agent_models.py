"""Persistent FDE work and its explicitly provisioned demo grant."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from onefde.core.clock import now
from onefde.infrastructure.db.base import Base


class AgentWork(Base):
    __tablename__ = "fde_agent_work"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    engagement_id: Mapped[UUID] = mapped_column(
        ForeignKey("engagements.id"), index=True
    )
    case_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("business_cases.id"), index=True
    )
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id"), unique=True)
    goal: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    observed: Mapped[dict | None] = mapped_column(JSONB)
    completed: Mapped[dict | None] = mapped_column(JSONB)
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    report: Mapped[dict] = mapped_column(JSONB, default=dict)
    trace: Mapped[list] = mapped_column(JSONB, default=list)
    calls: Mapped[int] = mapped_column(default=0)
    usage: Mapped[dict] = mapped_column(JSONB, default=dict)


class AgentGrant(Base):
    __tablename__ = "fde_agent_grants"

    work_id: Mapped[UUID] = mapped_column(
        ForeignKey("fde_agent_work.id"), primary_key=True
    )
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("model_profile_revisions.revision_id")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    policy: Mapped[dict] = mapped_column(JSONB)
    sent: Mapped[int] = mapped_column(default=0)
    runs: Mapped[list] = mapped_column(JSONB, default=list)
