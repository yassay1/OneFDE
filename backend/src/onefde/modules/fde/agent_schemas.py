from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from onefde.core.schemas import Input, Nonblank


class DispatchDecision(Input):
    decision: Literal["confirm", "decline"]


class StartWork(Input):
    goal: Nonblank | None = Field(default=None, max_length=4000)
    case_id: UUID | None = None

    @model_validator(mode="after")
    def goal_or_handoff(self):
        if not self.goal and not self.case_id:
            raise ValueError("provide a project goal or an approved case")
        return self


class WorkView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    engagement_id: UUID
    case_id: UUID | None
    task_id: UUID | None
    goal: str
    created_at: datetime
    state: Literal["pending", "processing", "reported"]
    report: dict[str, Any]
    trace: list[dict[str, Any]]
    calls: int
    usage: dict[str, int]


class DemoPolicy(Input):
    expires_at: datetime
    max_model_calls: int = Field(ge=1, le=80)
    max_clarifications: int = Field(ge=0, le=5)
    max_runs: int = Field(ge=0, le=3)
    max_fde_cost_nanousd: int = Field(gt=0)
    max_engineering_cost_nanousd_per_run: int = Field(ge=0)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    allowed_paths: list[str] = Field(min_length=1, max_length=30)
    review_paths: list[str] = Field(min_length=1, max_length=30)
    checks: list[Nonblank] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def engineering_budget(self):
        if self.max_runs and not self.max_engineering_cost_nanousd_per_run:
            raise ValueError("engineering requires an explicit per-run cost limit")
        return self


class ModelBudget(Input):
    max_cost_nanousd: int = Field(gt=0)
    max_input_tokens: int = Field(gt=0)
    input_nanousd_per_token: int = Field(gt=0)
    output_nanousd_per_token: int = Field(gt=0)
