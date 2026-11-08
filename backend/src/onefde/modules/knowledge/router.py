from fastapi import APIRouter, Request

from onefde.infrastructure.idempotency import idempotent_create
from onefde.infrastructure.web.dependencies import DB, Key
from onefde.modules.auth.dependencies import WriteSession
from onefde.modules.knowledge import schemas, service

router = APIRouter(prefix="/api/v1", tags=["knowledge"])


@router.post(
    "/knowledge/tools",
    response_model=schemas.KnowledgeToolResult,
    operation_id="invokeKnowledgeTool",
    summary="调用 Knowledge 受控工具",
    description="caller_role/purpose 由受信任调用方显式传入（当前单创始人演示）；"
    "权限过滤在服务端执行。不派发工程、不提升验证状态。",
)
def invoke_tool(
    data: schemas.KnowledgeToolCall,
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
        lambda: service.invoke(current.username, data, db),
        status_code=200,
    )
