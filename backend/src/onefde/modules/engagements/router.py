from uuid import UUID

from fastapi import APIRouter, Request

from onefde.infrastructure.idempotency import idempotent_create
from onefde.infrastructure.web.dependencies import DB, Key, Limit
from onefde.modules.auth.dependencies import Current, WriteSession
from onefde.modules.engagements import models, queries, schemas
from onefde.modules.engagements import service as services

router = APIRouter(prefix="/api/v1", tags=["business"])


@router.get(
    "/engagements",
    response_model=schemas.Page[schemas.Engagement],
    operation_id="listEngagements",
)
def list_engagements(
    current: Current, db: DB, limit: Limit = 50, cursor: str | None = None
):
    return queries.page(db, models.Engagement, schemas.Engagement, limit, cursor)


@router.post(
    "/engagements",
    status_code=201,
    response_model=schemas.Engagement,
    operation_id="createEngagement",
)
def create_engagement(
    data: schemas.EngagementCreate,
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
        lambda: services.create_engagement(db, data),
    )


@router.get(
    "/engagements/{engagement_id}",
    response_model=schemas.Engagement,
    operation_id="getEngagement",
)
def get_engagement(engagement_id: UUID, current: Current, db: DB):
    return queries.require_engagement(db, engagement_id)
