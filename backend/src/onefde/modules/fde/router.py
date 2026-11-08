from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import select

from onefde.core.errors import ApiException
from onefde.core.schemas import Page
from onefde.infrastructure.db.pagination import page
from onefde.infrastructure.idempotency import idempotent_create
from onefde.infrastructure.web.dependencies import DB, Key, Limit
from onefde.modules.auth.dependencies import Current, WriteSession
from onefde.modules.engagements.queries import require_engagement
from onefde.modules.fde import agent_schemas, agent_tools, agent_work, schemas, service
from onefde.modules.fde.agent_models import AgentWork

router = APIRouter(prefix="/api/v1", tags=["fde"])


@router.get(
    "/engagements/{engagement_id}/fde/work-history",
    response_model=Page[agent_schemas.WorkView],
    operation_id="pageFdeWork",
)
def work_history(
    engagement_id: UUID,
    current: Current,
    db: DB,
    limit: Limit = 50,
    cursor: str | None = None,
):
    require_engagement(db, engagement_id)
    return page(
        db,
        AgentWork,
        agent_schemas.WorkView,
        limit,
        cursor,
        scope=f"fde-work:{engagement_id}",
        filters=[AgentWork.engagement_id == engagement_id],
        project=lambda row: agent_schemas.WorkView.model_validate(
            agent_work.view(db, row)
        ),
    )


@router.get(
    "/engagements/{engagement_id}/fde/work/{work_id}",
    response_model=agent_schemas.WorkView,
    operation_id="getFdeWork",
)
def read_work(engagement_id: UUID, work_id: UUID, current: Current, db: DB):
    require_engagement(db, engagement_id)
    row = db.get(AgentWork, work_id)
    if not row or row.engagement_id != engagement_id:
        raise ApiException(404, "NOT_FOUND", "工作不存在或不属于当前项目")
    return agent_work.view(db, row)


@router.get(
    "/engagements/{engagement_id}/fde/work",
    response_model=list[agent_schemas.WorkView],
    operation_id="listFdeWork",
)
def list_work(engagement_id: UUID, current: Current, db: DB):
    require_engagement(db, engagement_id)
    rows = db.scalars(
        select(AgentWork)
        .where(AgentWork.engagement_id == engagement_id)
        .order_by(AgentWork.created_at.desc(), AgentWork.id)
        .limit(50)
    )
    return [agent_work.view(db, row) for row in rows]


@router.post(
    "/engagements/{engagement_id}/fde/work",
    status_code=202,
    response_model=agent_schemas.WorkView,
    operation_id="startFdeWork",
)
def start_work(
    engagement_id: UUID,
    data: agent_schemas.StartWork,
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
        lambda: agent_schemas.WorkView.model_validate(
            agent_work.start(db, engagement_id, data, current.username)
        ),
        status_code=202,
    )


@router.post(
    "/engagements/{engagement_id}/fde/work/{work_id}/dispatch",
    response_model=agent_schemas.WorkView,
    operation_id="decideFdeDispatch",
)
def decide_dispatch(
    engagement_id: UUID,
    work_id: UUID,
    data: agent_schemas.DispatchDecision,
    request: Request,
    current: WriteSession,
    db: DB,
    key: Key,
):
    def create():
        row = db.get(AgentWork, work_id, with_for_update=True)
        if not row or row.engagement_id != engagement_id:
            raise ApiException(404, "NOT_FOUND", "工作不存在或不属于当前项目")
        if data.decision == "confirm":
            agent_tools.confirm_dispatch(db, row)
        else:
            agent_tools.decline_dispatch(db, row)
        return agent_schemas.WorkView.model_validate(agent_work.view(db, row))

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
    "/engagements/{engagement_id}/delivery",
    response_model=schemas.DeliveryDetail,
    operation_id="getEngagementDelivery",
    summary="最小项目交付详情",
)
def get_delivery(engagement_id: UUID, current: Current, db: DB):
    return service.delivery_detail(db, engagement_id)


@router.post(
    "/engagements/{engagement_id}/fde/tools",
    response_model=schemas.FdeToolResult,
    operation_id="invokeFdeTool",
    summary="调用 FDE 受控工具",
    description="身份与项目范围由程序注入；模型不得自报 owner_role 或跨项目操作。"
    "白名单工具复用既有 Task 服务，不含 Worker 认领或发布。",
)
def invoke_tool(
    engagement_id: UUID,
    data: schemas.FdeToolCall,
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
        lambda: service.invoke(db, engagement_id, current.username, data),
        status_code=200,
    )
