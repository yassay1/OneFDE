from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OfficeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable feed id: kind:object_id")
    kind: Literal["case", "task", "fde_work", "run", "review"]
    role: Literal["business", "engineering", "fde"]
    title: str
    reason: str
    state: str
    object_id: UUID
    engagement_id: UUID | None = None
    case_id: UUID | None = None
    task_id: UUID | None = None
    run_id: UUID | None = None
    occurred_at: datetime
    href: str


class OfficeCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    case_cap: int
    task_cap: int
    fde_work_cap: int
    run_cap: int
    review_cap: int
    scanned_cases: int
    scanned_tasks: int
    scanned_fde_works: int
    scanned_runs: int
    scanned_reviews: int


class OfficePage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OfficeItem]
    next_cursor: str | None
    read_at: datetime
    coverage: OfficeCoverage
