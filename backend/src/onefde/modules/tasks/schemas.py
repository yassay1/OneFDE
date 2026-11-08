from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from onefde.core.schemas import Input, Nonblank, Title
from onefde.core.schemas import Page as Page
from onefde.core.schemas import SequencePage as SequencePage


class Dependency(Input):
    task_id: UUID
    spec_version: int = Field(ge=1)
    artifact_ids: list[UUID]


class TaskSpec(Input):
    title: Title
    objective: Nonblank
    scope: Nonblank
    inputs: list[str]
    confirmed_rules: list[str]
    completion_criteria: list[Nonblank] = Field(min_length=1)
    dependencies: list[Dependency]
    capability_versions: list[str]


class TaskCreate(Input):
    request_id: UUID
    task_key: Nonblank = Field(max_length=128)
    original_request: Nonblank
    spec: TaskSpec
    owner_role: Literal["fde"]
    executor_role: Literal["engineering"]
    related_task_id: UUID | None = None


class Task(BaseModel):
    model_config = ConfigDict(
        from_attributes=True, json_schema_serialization_defaults_required=True
    )
    id: UUID
    engagement_id: UUID
    state: Literal[
        "draft",
        "queued",
        "running",
        "waiting_input",
        "review",
        "blocked",
        "succeeded",
        "cancelled",
    ]
    revision: int = Field(ge=1)
    spec_version: int = Field(ge=1)
    spec: TaskSpec
    active_run_id: UUID | None = None
    block_reason: str | None = None
    owner_role: Literal["fde"]
    executor_role: Literal["engineering"]
    related_task_id: UUID | None = None
    pending_input_count: int = Field(default=0, ge=0)
    latest_run_id: UUID | None = None


Revision = Annotated[int, Field(ge=1, strict=True)]


InputKind = Literal["clarification", "change_request", "question", "answer"]


RunState = Literal[
    "queued",
    "running",
    "cancel_requested",
    "completed",
    "failed",
    "cancelled",
    "interrupted",
]


Outcome = Literal["submitted", "needs_input", "superseded"]


class TaskSpecUpdate(Input):
    expected_revision: Revision
    spec: TaskSpec


class TaskInputCreate(Input):
    expected_revision: Revision
    kind: InputKind
    text: Nonblank
    evidence_artifact_ids: list[UUID]
    reply_to_input_id: UUID | None = None

    @model_validator(mode="after")
    def answer_reference(self):
        if self.kind == "answer" and self.reply_to_input_id is None:
            raise ValueError("answer requires reply_to_input_id")
        if self.kind != "answer" and "reply_to_input_id" in self.model_fields_set:
            raise ValueError("only answer accepts reply_to_input_id")
        return self


class TaskInput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    task_id: UUID
    sequence: int = Field(ge=1)
    kind: InputKind
    text: str
    evidence_artifact_ids: list[UUID]
    status: Literal["pending", "applied", "rejected"]
    reply_to_input_id: UUID | None
    origin_run_id: UUID | None
    author: str
    applied_spec_version: int | None
    created_at: datetime
    processed_by: str | None
    processing_reason: str | None
    processed_at: datetime | None
    resolved_by_input_id: UUID | None


class TaskInputRecorded(Input):
    input: TaskInput
    task: Task


class TaskInputsApply(Input):
    expected_revision: Revision
    apply_ids: list[UUID] = Field(json_schema_extra={"uniqueItems": True})
    reject_ids: list[UUID] = Field(json_schema_extra={"uniqueItems": True})
    reason: Nonblank
    spec: TaskSpec | None = None

    @model_validator(mode="after")
    def distinct_nonempty(self):
        if not self.apply_ids and not self.reject_ids:
            raise ValueError("at least one input must be processed")
        if (
            len(set(self.apply_ids)) != len(self.apply_ids)
            or len(set(self.reject_ids)) != len(self.reject_ids)
            or set(self.apply_ids) & set(self.reject_ids)
        ):
            raise ValueError("input sets must be distinct and disjoint")
        if not self.apply_ids and self.spec is not None:
            raise ValueError("reject-only cannot change spec")
        return self


class Run(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    task_id: UUID
    task_spec_version: int = Field(ge=1)
    attempt: int = Field(ge=1)
    state: RunState
    model_profile_revision_id: UUID | None
    result_summary: str | None
    error_code: str | None
    created_at: datetime
    outcome: Outcome | None
    applied_input_ids: list[UUID]


class TaskAction(Input):
    command: Literal["queue", "start", "retry", "continue", "cancel", "stop_for_update"]
    expected_revision: Revision
    expected_run_id: UUID | None
    model_profile_revision_id: UUID | None = None

    @model_validator(mode="after")
    def command_arguments(self):
        if (
            self.command in ("start", "retry", "continue")
            and not self.model_profile_revision_id
        ):
            raise ValueError("starting a run requires model_profile_revision_id")
        if self.command in ("queue", "start") and self.expected_run_id is not None:
            raise ValueError("queue/start requires null expected_run_id")
        if (
            self.command in ("retry", "continue", "stop_for_update")
            and self.expected_run_id is None
        ):
            raise ValueError("command requires expected_run_id")
        return self


class VerificationStart(Input):
    """Trusted, in-process start command for an approved archive."""

    command: Literal["start"] = "start"
    expected_revision: Revision
    model_profile_revision_id: None = None


class ActionAccepted(Input):
    operation_id: UUID
    task: Task
    run: Run | None


class TaskReviewCreate(Input):
    expected_revision: Revision
    run_id: UUID
    task_spec_version: Revision
    artifact_ids: list[UUID] = Field(
        min_length=1, json_schema_extra={"uniqueItems": True}
    )
    verdict: Literal["accept", "request_changes"]
    reason: Nonblank
    check_evidence: list[Nonblank]

    @model_validator(mode="after")
    def review_evidence(self):
        if len(set(self.artifact_ids)) != len(self.artifact_ids):
            raise ValueError("artifact IDs must be unique")
        if self.verdict == "accept" and not self.check_evidence:
            raise ValueError("accept requires check evidence")
        return self


class TaskReview(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    task_id: UUID
    run_id: UUID
    task_spec_version: int
    artifact_ids: list[UUID]
    verdict: Literal["accept", "request_changes"]
    reason: str
    check_evidence: list[str]
    reviewer: str
    created_at: datetime


class TaskReviewed(Input):
    review: TaskReview
    task: Task


class TaskEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    task_id: UUID
    sequence: int = Field(ge=1)
    kind: Literal[
        "input_recorded",
        "inputs_processed",
        "state_changed",
        "run_created",
        "review_recorded",
        "assignment_changed",
    ]
    summary: str
    created_at: datetime


class ReviewCheck(BaseModel):
    command: str
    exit_code: int | None
    timeout: bool


class RunReviewEvidence(BaseModel):
    artifact_id: UUID
    artifact_sha256: str
    baseline_sha256: str
    mode: Literal["engineering", "deterministic"]
    design: str
    diff: str
    diff_truncated: bool
    self_checks: list[ReviewCheck]
    validation_checks: list[ReviewCheck]
    validation_passed: bool | None
    guide_revision: str | None = None
    assembly_revision: str | None = None
    baseline_origin: Literal["accepted_artifact", "trusted_starter"] | None = None
    baseline_artifact_id: UUID | None = None
    known_differences: list[str] = Field(default_factory=list)


class RunEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    sequence: int = Field(ge=1)
    kind: Literal["state", "progress", "check", "artifact", "error"]
    summary: str
    created_at: datetime


class TaskVersion(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    task_id: UUID
    spec_version: int = Field(ge=1)
    spec: TaskSpec
    applied_input_ids: list[UUID]
    actor: str
    reason: str
    created_at: datetime


class Artifact(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    engagement_id: UUID
    run_id: UUID | None
    name: str
    kind: str
    sha256: str
    size_bytes: int


class ModelProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    revision_id: UUID
    provider: str
    protocol: Literal["openai_chat_completions"]
    model: str
    capabilities: list[str]
    integration_status: Literal["configured", "smoke_passed", "unavailable"]


class ArtifactEvidence(Input):
    name: Title
    kind: Nonblank = Field(max_length=64)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)


class RunResult(Input):
    state: Literal["completed", "failed", "cancelled", "interrupted"]
    outcome: Outcome | None = None
    summary: Nonblank
    error_code: str | None = Field(default=None, max_length=128)
    stopped: bool = Field(strict=True)
    artifacts: list[ArtifactEvidence] = Field(default_factory=list)
    question: Nonblank | None = None

    @model_validator(mode="after")
    def result_evidence(self):
        if (self.state == "completed") != (self.outcome is not None):
            raise ValueError(
                "completed requires outcome; other states prohibit outcome"
            )
        if (
            self.state == "interrupted"
            and self.stopped
            or self.state != "interrupted"
            and not self.stopped
        ):
            raise ValueError("only interrupted retains uncertain execution")
        if self.outcome == "submitted" and not self.artifacts:
            raise ValueError("submission requires fixed artifact metadata")
        if self.outcome == "needs_input" and not self.question:
            raise ValueError("needs_input requires a question")
        if self.outcome != "needs_input" and self.question is not None:
            raise ValueError("question only allowed for needs_input")
        if self.state == "failed" and not self.error_code:
            raise ValueError("failure requires error code")
        return self
