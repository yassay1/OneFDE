"""Staff dialogue turns and process heartbeats. Not customer messages or runs."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from onefde.core.clock import now
from onefde.infrastructure.db.base import Base


class StaffTurn(Base):
    __tablename__ = "staff_turns"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    role: Mapped[str] = mapped_column(String(32))
    anchor_id: Mapped[str] = mapped_column(String(160))
    author: Mapped[str] = mapped_column(String(256))
    text: Mapped[str] = mapped_column(Text)
    basis: Mapped[dict] = mapped_column(JSONB)
    adapter: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        CheckConstraint(
            "role IN ('business','fde','engineering','knowledge')",
            name="ck_staff_turn_role",
        ),
        CheckConstraint(
            "adapter IN ('staff','scripted','live')",
            name="ck_staff_turn_adapter",
        ),
        Index("ix_staff_turns_anchor", "role", "anchor_id", "created_at", "id"),
    )


class RuntimeBeat(Base):
    __tablename__ = "runtime_beats"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    beat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    detail: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (
        CheckConstraint(
            "name IN ('fde_agent','engineering_worker')",
            name="ck_runtime_beat_name",
        ),
    )
