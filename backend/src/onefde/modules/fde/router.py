from uuid import UUID

from fastapi import APIRouter, Request

from onefde.infrastructure.idempotency import idempotent_create
from onefde.infrastructure.web.dependencies import DB, Key
from onefde.modules.auth.dependencies import Current, WriteSession
from onefde.modules.fde import schemas, service

router = APIRouter(prefix="/api/v1", tags=["fde"])


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
