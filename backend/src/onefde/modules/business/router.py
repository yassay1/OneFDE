import re
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from onefde.core.errors import ApiException
from onefde.core.schemas import Page
from onefde.infrastructure.db.pagination import page
from onefde.infrastructure.idempotency import idempotent_create
from onefde.infrastructure.web.dependencies import DB, After, Key, Limit
from onefde.modules.auth.dependencies import Current, WriteSession
from onefde.modules.business import leads, operations, service
from onefde.modules.business import models as m
from onefde.modules.business import schemas as s
from onefde.modules.fde import agent_work
from onefde.modules.fde.agent_models import AgentWork
from onefde.modules.fde.agent_schemas import StartWork

public = APIRouter(
    prefix="/api/v1/public/business/conversations", tags=["business-customer"]
)
router = APIRouter(prefix="/api/v1/business", tags=["business-workbench"])
bearer = HTTPBearer(auto_error=False)


def case_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    if not credentials or not re.fullmatch(r"[a-f0-9]{64}", credentials.credentials):
        raise ApiException(404, "BUSINESS_CASE_NOT_FOUND", "会话不存在或凭证无效")
    return credentials.credentials


Token = Annotated[str, Depends(case_token)]


def customer_write(request):
    if (
        request.headers.get("origin")
        != request.app.state.settings.business_customer_origin
    ):
        raise ApiException(403, "ORIGIN_FORBIDDEN", "报价产品 Origin 不受信任")
    if (
        request.headers.get("content-type", "").split(";")[0].strip().lower()
        != "application/json"
    ):
        raise ApiException(400, "JSON_REQUIRED", "写请求要求 application/json")


@public.put(
    "/{case_id}",
    response_model=s.PublicConversation,
    operation_id="startBusinessConversation",
)
def start(
    case_id: UUID, data: s.StartConversation, token: Token, request: Request, db: DB
):
    customer_write(request)
    row = service.start(db, case_id, token, data)
    result = service.public_view(db, row)
    db.commit()
    return result


@public.get(
    "/{case_id}",
    response_model=s.PublicConversation,
    operation_id="readBusinessConversation",
)
def read(case_id: UUID, token: Token, db: DB, after: After = 0):
    return service.public_view(db, service.case_for(db, case_id, token=token), after)


@public.post(
    "/{case_id}/messages",
    response_model=s.PublicConversation,
    operation_id="sendBusinessMessage",
)
def send(
    case_id: UUID, data: s.CustomerMessage, token: Token, request: Request, db: DB
):
    customer_write(request)
    row = service.case_for(db, case_id, token=token, lock=True)
    service.receive(db, row, data)
    result = service.public_view(db, row)
    db.commit()
    return result


@router.get(
    "/cases", response_model=Page[s.CaseSummary], operation_id="listBusinessCases"
)
def cases(
    current: Current,
    db: DB,
    limit: Limit = 50,
    cursor: str | None = None,
    workflow: Literal["inquiry", "support", "outreach"] | None = None,
    state: Literal[
        "open",
        "clarifying",
        "founder_queue",
        "fde_queue",
        "handling",
        "awaiting_retest",
        "closed",
    ]
    | None = None,
    owner: Literal["business", "founder", "fde"] | None = None,
    engagement_id: UUID | None = None,
):
    filters = []
    scope = "business-cases"
    for key, value in (
        ("workflow", workflow),
        ("state", state),
        ("owner", owner),
        ("engagement_id", engagement_id),
    ):
        if value is not None:
            filters.append(getattr(m.Case, key) == value)
            scope += f":{key}={value}"
    return page(db, m.Case, s.CaseSummary, limit, cursor, scope=scope, filters=filters)


@router.get(
    "/cases/{case_id}", response_model=s.CaseDetail, operation_id="readBusinessCase"
)
def read_case(case_id: UUID, current: Current, db: DB, after: After = 0):
    return service.detail(db, service.case_for(db, case_id), after)


@router.post(
    "/cases/{case_id}/clarification-draft",
    response_model=s.ClarificationDraft,
    operation_id="prepareBusinessClarification",
)
def prepare_clarification(
    case_id: UUID, data: s.ClarificationRequest, current: WriteSession, db: DB
):
    row = service.case_for(db, case_id, lock=True)
    return operations.clarification_draft(db, row, data, current.username)


@router.post(
    "/cases/{case_id}/actions",
    response_model=s.CaseDetail,
    operation_id="actOnBusinessCase",
)
def action(
    case_id: UUID,
    data: s.CaseAction,
    current: WriteSession,
    request: Request,
    db: DB,
    key: Key,
):
    def perform():
        row = service.case_for(db, case_id, lock=True)
        if isinstance(data, s.ApproveFdeFeedback):
            work = db.get(AgentWork, data.fde_work_id)
            if (
                not work
                or work.case_id != row.id
                or work.engagement_id != row.engagement_id
                or work.task_id != row.task_id
                or not work.report.get("summary")
                or work.report.get("error")
                or agent_work.view(db, work)["state"] != "reported"
            ):
                service.conflict("请引用原会话当前已完成的 FDE 回报")
            operations.approve_fde_feedback(db, row, data, current.username)
            return service.detail(db, row)
        operations.handle(db, row, data, current.username)
        if isinstance(data, s.AcceptHandoff):
            agent_work.start(
                db,
                row.engagement_id,
                StartWork(case_id=row.id),
                current.username,
                preserve_existing_task=True,
            )
        return service.detail(db, row)

    return idempotent_create(
        db, current.username, request.url.path, key, data, perform, status_code=200
    )


@public.post(
    "/{case_id}/retest",
    response_model=s.PublicConversation,
    operation_id="submitBusinessRetest",
)
def submit_retest(
    case_id: UUID, data: s.RetestResult, token: Token, request: Request, db: DB
):
    customer_write(request)
    row = service.case_for(db, case_id, token=token, lock=True)
    operations.retest_result(db, row, data)
    result = service.public_view(db, row)
    db.commit()
    return result


@router.post(
    "/candidate-search",
    response_model=s.CandidateResults,
    operation_id="searchBusinessCandidates",
)
def search_candidates(
    data: s.SearchDistrict, current: WriteSession, request: Request, db: DB, key: Key
):
    setting = request.app.state.settings.business_amap_key
    return idempotent_create(
        db,
        current.username,
        request.url.path,
        key,
        data,
        lambda: leads.search(db, setting.get_secret_value() if setting else None, data),
        status_code=200,
    )


@router.get(
    "/candidates",
    response_model=s.CandidateResults,
    operation_id="listBusinessCandidates",
)
def list_candidates(current: Current, db: DB, adcode: s.Adcode):
    return leads.candidates(db, adcode)


@router.post(
    "/candidates/{candidate_id}/invite",
    response_model=s.CandidateView,
    operation_id="inviteBusinessCandidate",
)
def invite(candidate_id: UUID, data: s.InviteCandidate, current: WriteSession, db: DB):
    result = leads.invite(db, candidate_id, current.username)
    db.commit()
    return result
