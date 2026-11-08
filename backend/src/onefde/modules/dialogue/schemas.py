from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from onefde.core.schemas import Input, Nonblank
from onefde.modules.knowledge.schemas import CallerRole, Purpose

StaffRole = Literal["business", "fde", "engineering", "knowledge"]
AdapterName = Literal["staff", "scripted", "live"]


class StaffQuestion(Input):
    text: Nonblank = Field(max_length=4000)


class StaffDecision(Input):
    decision: Literal["confirm", "decline"]


class KnowledgeQuestion(StaffQuestion):
    caller_role: CallerRole
    purpose: Purpose = "delivery"
    case_id: UUID | None = None
    engagement_id: UUID | None = None
    task_id: UUID | None = None
    run_id: UUID | None = None
    work_id: UUID | None = None


class StaffTurnView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    role: StaffRole
    author: str
    text: str
    basis: dict[str, Any]
    adapter: AdapterName
    created_at: datetime


class DialogueView(BaseModel):
    turns: list[StaffTurnView]


class DialogueReply(BaseModel):
    turns: list[StaffTurnView]


class BeatView(BaseModel):
    name: Literal["fde_agent", "engineering_worker"]
    state: Literal["running", "not_running"]
    beat_at: datetime | None
    age_seconds: int | None
    detail: str


class RuntimeStatus(BaseModel):
    fde_agent: BeatView
    engineering_worker: BeatView
