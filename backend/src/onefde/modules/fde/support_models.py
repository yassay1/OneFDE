"""Durable state for the explicitly enrolled quote support pilot."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from onefde.infrastructure.db.base import Base


class QuoteSupport(Base):
    __tablename__ = "fde_quote_support"

    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("business_cases.id"), primary_key=True
    )
    engagement_id: Mapped[UUID] = mapped_column(ForeignKey("engagements.id"))
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("model_profile_revisions.revision_id")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stage: Mapped[str] = mapped_column(String(32))
    source: Mapped[dict] = mapped_column(JSONB)
    progress: Mapped[dict] = mapped_column(JSONB)
