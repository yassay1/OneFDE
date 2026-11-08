from datetime import datetime
from typing import Literal

from pydantic import Field

from onefde.core.schemas import Input, Nonblank, Title


class Policy(Input):
    expires_at: datetime
    max_calls: int = Field(ge=1, le=80)
    max_replies: int = Field(ge=1, le=20)
    max_cost_nanousd: int = Field(gt=0)
    max_input_tokens: int = Field(ge=128_000)
    input_nanousd_per_token: int = Field(gt=0)
    output_nanousd_per_token: int = Field(gt=0)


class ConversationWindow(Input):
    before: int | None = Field(default=None, gt=0)


class Search(Input):
    query: str = Field(max_length=100)


class FaqLookup(Input):
    topic: Literal["csv-format", "pending-reason", "export"]


class Answer(Input):
    source: Nonblank = Field(max_length=160)


class Clarify(Input):
    focus: list[
        Literal[
            "current_process",
            "desired_result",
            "input_and_output",
            "version",
            "reproduction",
            "observed_result",
            "consent",
        ]
    ] = Field(min_length=1, max_length=3)


class Handoff(Input):
    kind: Literal["requirement", "support"]
    title: Title
    goal: Nonblank = Field(max_length=1500)
    fact_message_ids: list[int] = Field(min_length=1, max_length=12)
    confirmed_facts: list[Nonblank] = Field(min_length=1, max_length=12)
    unknowns: list[str] = Field(max_length=12)
    reproduction_message_id: int | None = None


class Escalate(Input):
    reason: Literal["commercial", "human_requested", "unsupported", "uncertain"]
