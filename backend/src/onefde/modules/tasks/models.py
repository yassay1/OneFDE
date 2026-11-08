from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from onefde.core.clock import now
from onefde.infrastructure.db.base import Base


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    engagement_id: Mapped[UUID] = mapped_column(ForeignKey("engagements.id"))
    request_id: Mapped[UUID]
    task_key: Mapped[str] = mapped_column(String(128))
    original_request: Mapped[str] = mapped_column(Text)
    spec: Mapped[dict] = mapped_column(JSONB)
    owner_role: Mapped[str] = mapped_column(String(32), default="fde")
    executor_role: Mapped[str] = mapped_column(String(32), default="engineering")
    state: Mapped[str] = mapped_column(String(32), default="draft")
    revision: Mapped[int] = mapped_column(default=1)
    spec_version: Mapped[int] = mapped_column(default=1)
    active_run_id: Mapped[UUID | None]
    latest_run_id: Mapped[UUID | None]
    block_reason: Mapped[str | None] = mapped_column(Text)
    pending_input_count: Mapped[int] = mapped_column(default=0, server_default="0")
    input_sequence: Mapped[int] = mapped_column(default=0, server_default="0")
    event_sequence: Mapped[int] = mapped_column(default=0, server_default="0")
    related_task_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        UniqueConstraint(
            "engagement_id", "request_id", "task_key", name="uq_task_request_key"
        ),
        UniqueConstraint("engagement_id", "id", name="uq_task_engagement_id"),
        ForeignKeyConstraint(
            ["engagement_id", "related_task_id"],
            ["tasks.engagement_id", "tasks.id"],
            name="fk_task_related_same_engagement",
        ),
        CheckConstraint(
            "state IN ('draft','queued','running','waiting_input','review','blocked','succeeded','cancelled') AND revision >= 1 AND spec_version >= 1 AND pending_input_count >= 0",
            name="ck_task_state",
        ),
        CheckConstraint(
            "owner_role = 'fde' AND executor_role = 'engineering'", name="ck_task_roles"
        ),
        Index("ix_tasks_page", "engagement_id", "created_at", "id"),
        *[
            ForeignKeyConstraint(
                ["id", field],
                ["runs.task_id", "runs.id"],
                name="fk_task_" + field,
                use_alter=True,
                deferrable=True,
                initially="DEFERRED",
            )
            for field in ("active_run_id", "latest_run_id")
        ],
        CheckConstraint(
            "(state = 'running' AND active_run_id IS NOT NULL) OR (state = 'blocked') OR (state NOT IN ('running','blocked') AND active_run_id IS NULL)",
            name="ck_task_active_state",
        ),
    )


class TaskVersion(Base):
    __tablename__ = "task_versions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id"))
    spec_version: Mapped[int]
    spec: Mapped[dict] = mapped_column(JSONB)
    applied_input_ids: Mapped[list] = mapped_column(JSONB)
    actor: Mapped[str] = mapped_column(String(256))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        UniqueConstraint("task_id", "spec_version", name="uq_task_version"),
    )


class ModelProfileRevision(Base):
    __tablename__ = "model_profile_revisions"
    revision_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    id: Mapped[UUID] = mapped_column(default=uuid4)
    provider: Mapped[str] = mapped_column(String(128))
    protocol: Mapped[str] = mapped_column(String(64), default="openai_chat_completions")
    model: Mapped[str] = mapped_column(String(200))
    capabilities: Mapped[list] = mapped_column(JSONB, default=list)
    integration_status: Mapped[str] = mapped_column(String(32), default="configured")
    # Only non-secret configuration/secret references. No live client is constructed.
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    __table_args__ = (
        CheckConstraint(
            "protocol = 'openai_chat_completions' AND integration_status IN ('configured','smoke_passed','unavailable')",
            name="ck_profile_config",
        ),
    )


ACTIVE_RUN_SQL = "state IN ('queued','running','cancel_requested','interrupted')"


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id"))
    task_spec_version: Mapped[int]
    attempt: Mapped[int]
    state: Mapped[str] = mapped_column(String(32), default="queued")
    outcome: Mapped[str | None] = mapped_column(String(32))
    model_profile_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("model_profile_revisions.revision_id")
    )
    applied_input_ids: Mapped[list] = mapped_column(JSONB)
    snapshot: Mapped[dict] = mapped_column(JSONB)
    result_summary: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(128))
    stop_reason: Mapped[str | None] = mapped_column(String(32))
    result_hash: Mapped[str | None] = mapped_column(String(64))
    event_sequence: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("task_id", "attempt", name="uq_run_attempt"),
        UniqueConstraint("task_id", "id", name="uq_run_task_id"),
        ForeignKeyConstraint(
            ["task_id", "task_spec_version"],
            ["task_versions.task_id", "task_versions.spec_version"],
            name="fk_run_version",
        ),
        CheckConstraint(
            "state IN ('queued','running','cancel_requested','completed','failed','cancelled','interrupted') AND attempt >= 1",
            name="ck_run_state",
        ),
        CheckConstraint(
            "(state = 'completed' AND outcome IS NOT NULL AND outcome IN ('submitted','needs_input','superseded')) OR (state <> 'completed' AND outcome IS NULL)",
            name="ck_run_outcome",
        ),
        Index(
            "uq_run_task_active",
            "task_id",
            unique=True,
            postgresql_where=text(ACTIVE_RUN_SQL),
        ),
        Index(
            "uq_run_global_active",
            text("(1)"),
            unique=True,
            postgresql_where=text(ACTIVE_RUN_SQL),
        ),
        Index("ix_runs_page", "task_id", "created_at", "id"),
    )


class DispatchJob(Base):
    __tablename__ = "dispatch_jobs"
    operation_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id"), unique=True)
    kind: Mapped[str] = mapped_column(String(32), default="engineering")
    state: Mapped[str] = mapped_column(String(32), default="pending")
    payload: Mapped[dict] = mapped_column(JSONB)
    claim_owner: Mapped[str | None] = mapped_column(String(128))
    claim_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    runtime_ref: Mapped[dict | None] = mapped_column(JSONB)
    result_digest: Mapped[str | None] = mapped_column(String(64))
    result_payload: Mapped[dict | None] = mapped_column(JSONB)
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending','running','cancel_requested','completed','failed','cancelled','interrupted')",
            name="ck_job_state",
        ),
        CheckConstraint(
            "attempts >= 0 AND ((claim_token IS NULL AND claim_owner IS NULL AND lease_until IS NULL) OR (claim_token IS NOT NULL AND claim_owner IS NOT NULL AND lease_until IS NOT NULL))",
            name="ck_job_claim",
        ),
        Index("ix_jobs_poll", "state", "lease_until"),
    )


class TaskInput(Base):
    __tablename__ = "task_inputs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id"))
    sequence: Mapped[int]
    kind: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    evidence_artifact_ids: Mapped[list] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    reply_to_input_id: Mapped[UUID | None]
    origin_run_id: Mapped[UUID | None]
    action_id: Mapped[UUID | None]
    author: Mapped[str] = mapped_column(String(256))
    applied_spec_version: Mapped[int | None]
    processed_by: Mapped[str | None] = mapped_column(String(256))
    processing_reason: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_input_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        UniqueConstraint("task_id", "sequence", name="uq_input_sequence"),
        UniqueConstraint("task_id", "id", name="uq_input_task_id"),
        UniqueConstraint("origin_run_id", "action_id", name="uq_input_run_action"),
        ForeignKeyConstraint(
            ["task_id", "reply_to_input_id"],
            ["task_inputs.task_id", "task_inputs.id"],
            name="fk_input_reply",
        ),
        ForeignKeyConstraint(
            ["task_id", "resolved_by_input_id"],
            ["task_inputs.task_id", "task_inputs.id"],
            name="fk_input_resolved",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["task_id", "origin_run_id"],
            ["runs.task_id", "runs.id"],
            name="fk_input_origin",
        ),
        ForeignKeyConstraint(
            ["task_id", "applied_spec_version"],
            ["task_versions.task_id", "task_versions.spec_version"],
            name="fk_input_version",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "kind IN ('clarification','change_request','question','answer') AND status IN ('pending','applied','rejected') AND sequence > 0",
            name="ck_input_state",
        ),
        CheckConstraint(
            "(kind = 'answer') = (reply_to_input_id IS NOT NULL)",
            name="ck_input_answer",
        ),
        CheckConstraint(
            "(origin_run_id IS NULL) = (action_id IS NULL)",
            name="ck_input_origin_action",
        ),
        CheckConstraint(
            "(status = 'applied') = (applied_spec_version IS NOT NULL)",
            name="ck_input_applied",
        ),
    )


class TaskEvent(Base):
    __tablename__ = "task_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id"))
    sequence: Mapped[int]
    kind: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(256))
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        UniqueConstraint("task_id", "sequence", name="uq_task_event_sequence"),
    )


class RunEvent(Base):
    __tablename__ = "run_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id"))
    sequence: Mapped[int]
    kind: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_run_event_sequence"),
    )


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    engagement_id: Mapped[UUID] = mapped_column(ForeignKey("engagements.id"))
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("runs.id"))
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(64))
    object_key: Mapped[str] = mapped_column(Text, unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        CheckConstraint(
            "size_bytes >= 0 AND sha256 ~ '^[a-f0-9]{64}$'", name="ck_artifact_metadata"
        ),
    )


class TaskReview(Base):
    __tablename__ = "task_reviews"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id"))
    run_id: Mapped[UUID]
    task_spec_version: Mapped[int]
    artifact_ids: Mapped[list] = mapped_column(JSONB)
    verdict: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    check_evidence: Mapped[list] = mapped_column(JSONB)
    reviewer: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id", "run_id"], ["runs.task_id", "runs.id"], name="fk_review_run"
        ),
        ForeignKeyConstraint(
            ["task_id", "task_spec_version"],
            ["task_versions.task_id", "task_versions.spec_version"],
            name="fk_review_version",
        ),
        CheckConstraint(
            "verdict IN ('accept','request_changes') AND jsonb_array_length(artifact_ids) > 0 AND (verdict <> 'accept' OR jsonb_array_length(check_evidence) > 0)",
            name="ck_review_evidence",
        ),
        Index("ix_reviews_page", "task_id", "created_at", "id"),
    )
