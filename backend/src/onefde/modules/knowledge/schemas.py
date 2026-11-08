from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from onefde.core.knowledge import TOOL_NAMES
from onefde.core.schemas import Input, Nonblank

ToolName = Literal[
    "search_assets",
    "get_asset",
    "record_business_handoff",
    "record_delivery_feedback",
]
CallerRole = Literal["business", "fde", "engineering"]
Purpose = Literal["delivery", "internal_research", "public_marketing"]

if set(ToolName.__args__) != TOOL_NAMES:  # pragma: no cover
    raise RuntimeError("Knowledge ToolName drifted from core.knowledge.TOOL_NAMES")


class KnowledgeToolCall(Input):
    tool: ToolName
    caller_role: CallerRole
    purpose: Purpose = "delivery"
    arguments: dict[str, Any] = Field(default_factory=dict)


class KnowledgeToolResult(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)
    tool: ToolName
    role_revision: str
    caller_role: CallerRole
    purpose: Purpose
    actor: str
    result: dict[str, Any]


class BusinessHandoff(Input):
    title: Nonblank
    goal: Nonblank
    sources: list[Nonblank] = Field(min_length=1)
    unknowns: list[str] = Field(default_factory=list)
    is_demo: bool = True
    notes: str = ""
