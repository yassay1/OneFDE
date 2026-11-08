from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request

from onefde.infrastructure.idempotency import idempotent_create
from onefde.infrastructure.web.dependencies import DB, Key
from onefde.modules.auth.dependencies import Current, WriteSession
from onefde.modules.dialogue import actions, context, model, service
from onefde.modules.dialogue.schemas import (
    DialogueReply,
    DialogueView,
    KnowledgeQuestion,
    RuntimeStatus,
    StaffDecision,
    StaffQuestion,
    StaffTurnView,
)

router = APIRouter(prefix="/api/v1", tags=["staff-dialogue"])
Caller = Annotated[Literal["business", "fde", "engineering"], Query()]
Audience = Annotated[
    Literal["delivery", "internal_research", "public_marketing"], Query()
]


def _live(request, db, mode, role):
    if mode != "live" or role == "knowledge":
        return None
    injected = getattr(request.app.state, "staff_live", None)
    if injected is not None:
        return injected
    return model.resolve(db, request.app.state.settings.staff_model_revision_id)


def _ask(db, current, request, key, data, create):
    return idempotent_create(
        db,
        current.username,
        request.url.path,
        key,
        data,
        create,
        status_code=200,
    )


@router.get(
    "/business/cases/{case_id}/assistant",
    response_model=DialogueView,
    operation_id="listBusinessAssistant",
)
def list_business_assistant(case_id: UUID, current: Current, db: DB):
    context.business(db, case_id, current.username)
    return service.list_turns(db, "business", str(case_id))


@router.post(
    "/business/cases/{case_id}/assistant",
    response_model=DialogueReply,
    operation_id="askBusinessAssistant",
)
def ask_business_assistant(
    case_id: UUID,
    data: StaffQuestion,
    request: Request,
    current: WriteSession,
    db: DB,
    key: Key,
):
    built = context.business(db, case_id, current.username)
    mode = request.app.state.settings.staff_chat_mode
    live = _live(request, db, mode, "business")

    def create():
        return service.append(
            db,
            role="business",
            anchor_id=str(case_id),
            actor=current.username,
            question=data.text,
            context=built,
            mode=mode,
            live=live,
        )

    return _ask(db, current, request, key, data, create)


@router.get(
    "/engagements/{engagement_id}/fde/dialogue",
    response_model=DialogueView,
    operation_id="listFdeDialogue",
)
def list_fde_dialogue(engagement_id: UUID, current: Current, db: DB):
    context.fde(db, engagement_id)
    return service.list_turns(db, "fde", str(engagement_id))


@router.post(
    "/engagements/{engagement_id}/fde/dialogue",
    response_model=DialogueReply,
    operation_id="askFdeDialogue",
)
def ask_fde_dialogue(
    engagement_id: UUID,
    data: StaffQuestion,
    request: Request,
    current: WriteSession,
    db: DB,
    key: Key,
):
    built = context.fde(db, engagement_id)
    mode = request.app.state.settings.staff_chat_mode
    live = _live(request, db, mode, "fde")

    def create():
        return service.append(
            db,
            role="fde",
            anchor_id=str(engagement_id),
            actor=current.username,
            question=data.text,
            context=built,
            mode=mode,
            live=live,
        )

    return _ask(db, current, request, key, data, create)


@router.get(
    "/tasks/{task_id}/dialogue",
    response_model=DialogueView,
    operation_id="listTaskDialogue",
)
def list_task_dialogue(task_id: UUID, current: Current, db: DB):
    context.engineering(db, task_id)
    return service.list_turns(db, "engineering", str(task_id))


@router.post(
    "/tasks/{task_id}/dialogue",
    response_model=DialogueReply,
    operation_id="askTaskDialogue",
)
def ask_task_dialogue(
    task_id: UUID,
    data: StaffQuestion,
    request: Request,
    current: WriteSession,
    db: DB,
    key: Key,
):
    built = context.engineering(db, task_id)
    mode = request.app.state.settings.staff_chat_mode
    live = _live(request, db, mode, "engineering")

    def create():
        return service.append(
            db,
            role="engineering",
            anchor_id=str(task_id),
            actor=current.username,
            question=data.text,
            context=built,
            mode=mode,
            live=live,
        )

    return _ask(db, current, request, key, data, create)


@router.get(
    "/knowledge/dialogue",
    response_model=DialogueView,
    operation_id="listKnowledgeDialogue",
)
def list_knowledge_dialogue(
    current: Current,
    db: DB,
    caller_role: Caller,
    purpose: Audience = "delivery",
):
    return service.list_turns(db, "knowledge", f"{caller_role}:{purpose}")


@router.post(
    "/knowledge/dialogue",
    response_model=DialogueReply,
    operation_id="askKnowledgeDialogue",
)
def ask_knowledge_dialogue(
    data: KnowledgeQuestion,
    request: Request,
    current: WriteSession,
    db: DB,
    key: Key,
):
    built = context.knowledge(
        current.username, data.text, data.caller_role, data.purpose
    )
    mode = request.app.state.settings.staff_chat_mode
    anchor = f"{data.caller_role}:{data.purpose}"

    def create():
        return service.append(
            db,
            role="knowledge",
            anchor_id=anchor,
            actor=current.username,
            question=data.text,
            context=built,
            mode=mode,
            staff_basis={
                "case_id": str(data.case_id) if data.case_id else None,
                "engagement_id": str(data.engagement_id)
                if data.engagement_id
                else None,
                "task_id": str(data.task_id) if data.task_id else None,
                "run_id": str(data.run_id) if data.run_id else None,
                "work_id": str(data.work_id) if data.work_id else None,
                "purpose": data.purpose,
                "caller_role": data.caller_role,
            },
        )

    return _ask(db, current, request, key, data, create)


@router.post(
    "/dialogue/turns/{turn_id}/decision",
    response_model=StaffTurnView,
    operation_id="decideStaffTurn",
)
def decide_staff_turn(
    turn_id: UUID,
    data: StaffDecision,
    request: Request,
    current: WriteSession,
    db: DB,
    key: Key,
):
    return idempotent_create(
        db,
        current.username,
        request.url.path,
        key,
        data,
        lambda: actions.decide(db, turn_id, data.decision, current.username),
        status_code=200,
    )


@router.get(
    "/runtime/status", response_model=RuntimeStatus, operation_id="runtimeStatus"
)
def runtime_status(current: Current, db: DB):
    return service.runtime_status(db)
