from fastapi import APIRouter

from onefde.infrastructure.web.dependencies import DB, Limit
from onefde.modules.auth.dependencies import Current
from onefde.modules.office import queries, schemas

router = APIRouter(prefix="/api/v1/office", tags=["office"])


@router.get(
    "/actionable",
    response_model=schemas.OfficePage,
    operation_id="listOfficeActionable",
)
def list_office_actionable(
    current: Current, db: DB, limit: Limit = 50, cursor: str | None = None
):
    return queries.list_actionable(db, limit=limit, cursor=cursor)


@router.get(
    "/activity",
    response_model=schemas.OfficePage,
    operation_id="listOfficeActivity",
)
def list_office_activity(
    current: Current, db: DB, limit: Limit = 50, cursor: str | None = None
):
    return queries.list_activity(db, limit=limit, cursor=cursor)
