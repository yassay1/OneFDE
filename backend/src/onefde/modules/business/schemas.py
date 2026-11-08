from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from onefde.core.schemas import Input, Nonblank, Title
from onefde.modules.knowledge.schemas import BusinessHandoff
from onefde.modules.tasks.schemas import TaskSpec

MessageText = Annotated[Nonblank, Field(max_length=4000)]
Version = Annotated[Nonblank, Field(max_length=128)]


class CustomerMessage(Input):
    request_id: UUID
    text: MessageText
    project_hint: Annotated[Nonblank, Field(max_length=200)] | None = None
    version_hint: Version | None = None
    willing_to_continue: bool = False


class StartConversation(CustomerMessage):
    invitation_id: UUID | None = None


class PublicMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: Literal["customer", "reply"]
    text: str
    created_at: datetime


class PublicConversation(BaseModel):
    id: UUID
    state: Literal["open", "awaiting_retest", "closed"]
    retest_notice_id: int | None
    messages: list[PublicMessage]
    last_message_id: int
    has_more: bool


class InternalMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: Literal["customer", "reply", "note"]
    author: str
    text: str
    reference: dict | None
    created_at: datetime


class Handoff(BusinessHandoff):
    id: UUID
    confirmed_facts: list[str]
    product_version: str | None
    reproduction: str | None
    consent_message_id: int | None = None
    fact_message_ids: list[int] = Field(default_factory=list)
    reproduction_message_id: int | None = None


class CaseSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: Literal["quote_page", "invitation"]
    workflow: Literal["inquiry", "support", "outreach"]
    state: Literal[
        "open",
        "clarifying",
        "founder_queue",
        "fde_queue",
        "handling",
        "awaiting_retest",
        "closed",
    ]
    owner: Literal["business", "founder", "fde"]
    handler: str | None
    next_step: str
    created_at: datetime


class CaseDetail(CaseSummary):
    engagement_id: UUID | None
    reported_version: str | None
    task_id: UUID | None
    invitation_id: UUID | None
    handoff: Handoff | None
    retest: dict | None
    messages: list[InternalMessage]
    last_message_id: int
    has_more: bool


class CandidateView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: str
    adcode: str
    poi_id: str
    name: str
    address: str
    reason: str
    queried_at: datetime
    invited_at: datetime | None
    invited_by: str | None


Adcode = Annotated[str, Field(pattern=r"^[1-9][0-9]{5}$")]


class InviteCandidate(Input):
    pass


class SearchDistrict(Input):
    adcode: Adcode
    sample: bool = False


class CandidateResults(BaseModel):
    items: list[CandidateView]


class TakeOver(Input):
    action: Literal["take_over"]


class StaffMessage(Input):
    action: Literal["reply", "note"]
    text: MessageText


class SendClarification(Input):
    action: Literal["send_clarification"]
    text: MessageText
    source_message_id: int = Field(gt=0)
    expected_last_public_message_id: int = Field(gt=0)


class ClarificationRequest(Input):
    source_message_id: int = Field(gt=0)
    understanding: Annotated[Nonblank, Field(max_length=500)]
    question: Annotated[Nonblank, Field(max_length=500)] | None = None
    kind: Literal["clarify", "commitment"]


class ClarificationDraft(BaseModel):
    source_message_id: int
    last_public_message_id: int
    public_reply: str
    internal_summary: str


class HandoffCommand(Input):
    action: Literal["handoff"]
    title: Title
    goal: MessageText
    confirmed_facts: list[MessageText] = Field(max_length=20)
    unknowns: list[MessageText] = Field(max_length=20)
    reproduction: MessageText | None = None


class AcceptHandoff(Input):
    action: Literal["accept_handoff"]
    engagement_id: UUID
    reported_version: Version | None = None
    task_id: UUID | None = None
    spec: TaskSpec | None = None


class RecordInput(Input):
    action: Literal["record_input"]
    message_id: int = Field(gt=0)


class ApproveFdeFeedback(Input):
    action: Literal["approve_fde_feedback"]
    fde_work_id: UUID
    expected_last_public_message_id: int = Field(gt=0)
    text: MessageText


class NotifyRetest(Input):
    action: Literal["notify_retest"]
    artifact_id: UUID
    version: Version
    access_url: Annotated[Nonblank, Field(max_length=2000)]
    steps: MessageText
    access_evidence: MessageText


class RetestResult(Input):
    request_id: UUID
    notice_id: int = Field(gt=0)
    passed: bool
    text: MessageText


CaseAction = Annotated[
    TakeOver
    | StaffMessage
    | SendClarification
    | HandoffCommand
    | AcceptHandoff
    | RecordInput
    | ApproveFdeFeedback
    | NotifyRetest,
    Field(discriminator="action"),
]
