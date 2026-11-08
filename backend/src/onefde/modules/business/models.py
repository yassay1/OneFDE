from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from onefde.core.clock import now
from onefde.infrastructure.db.base import Base


class Case(Base):
    __tablename__ = "business_cases"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    token_digest: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(32))
    workflow: Mapped[str] = mapped_column(String(24))
    state: Mapped[str] = mapped_column(String(24))
    owner: Mapped[str] = mapped_column(String(24))
    handler: Mapped[str | None] = mapped_column(String(128))
    next_step: Mapped[str] = mapped_column(Text)
    engagement_id: Mapped[UUID | None] = mapped_column(ForeignKey("engagements.id"))
    reported_version: Mapped[str | None] = mapped_column(String(128))
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id"))
    handoff: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    retest: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    invitation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("business_candidates.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, index=True
    )


class Message(Base):
    __tablename__ = "business_messages"
    __table_args__ = (UniqueConstraint("case_id", "request_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("business_cases.id"), index=True)
    request_id: Mapped[UUID | None]
    request_hash: Mapped[str | None] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    author: Mapped[str] = mapped_column(String(160))
    text: Mapped[str] = mapped_column(Text)
    reference: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Candidate(Base):
    __tablename__ = "business_candidates"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(24))
    adcode: Mapped[str] = mapped_column(String(6))
    poi_id: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(Text)
    address: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    queried_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invited_by: Mapped[str | None] = mapped_column(String(128))


class AgentGrant(Base):
    __tablename__ = "business_agent_grants"

    # Registered before the customer creates the conversation.
    case_id: Mapped[UUID] = mapped_column(primary_key=True)
    engagement_id: Mapped[UUID | None] = mapped_column(ForeignKey("engagements.id"))
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("model_profile_revisions.revision_id")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    policy: Mapped[dict] = mapped_column(JSONB)
    progress: Mapped[dict] = mapped_column(JSONB)
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
