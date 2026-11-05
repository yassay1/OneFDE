from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from onefde.core.fde import TOOL_NAMES
from onefde.core.schemas import Input, Nonblank
from onefde.modules.engagements.schemas import Engagement
from onefde.modules.tasks import schemas as tasks

ToolName = Literal[
    "read_project",
    "create_task",
    "save_input",
    "adopt_inputs",
    "request_execution",
    "get_task",
    "get_run",
    "propose_review",
]

if set(ToolName.__args__) != TOOL_NAMES:  # pragma: no cover
    raise RuntimeError("FDE ToolName literal drifted from core.fde.TOOL_NAMES")


class FdeTaskCreate(Input):
    """Task create without role fields; tools inject owner=fde executor=engineering."""

    request_id: UUID
    task_key: Nonblank = Field(max_length=128)
    original_request: Nonblank
    spec: tasks.TaskSpec
    related_task_id: UUID | None = None


class FdeToolCall(Input):
    tool: ToolName
    arguments: dict[str, Any] = Field(default_factory=dict)


class FdeToolResult(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)
    tool: ToolName
    role_revision: str
    engagement_id: UUID
    actor: str
    result: dict[str, Any]


class DeliveryTaskSummary(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)
    id: UUID
    state: str
    title: str
    objective: str
    scope: str
    pending_input_count: int
    latest_run_id: UUID | None
    revision: int
    spec_version: int


class DeliveryDetail(BaseModel):
    """Minimal project delivery view for the thin workbench detail page."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)
    engagement: Engagement
    sources_note: str
    unknowns: list[str]
    scheme_summary: str | None
    tasks: list[DeliveryTaskSummary]
    latest_checks: list[str]
    fixed_version_hint: str | None
