from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict, Field

from onefde.core.schemas import Input, Nonblank, Title
from onefde.core.schemas import Page as Page


class EngagementCreate(Input):
    title: Title
    is_demo: bool = Field(strict=True)
    goal: Nonblank


class Engagement(EngagementCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
