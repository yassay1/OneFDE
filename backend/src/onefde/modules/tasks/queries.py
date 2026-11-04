from sqlalchemy import select

from onefde.core.errors import ApiException
from onefde.infrastructure.db.pagination import page as paginate
from onefde.modules.engagements.queries import require_engagement
from onefde.modules.tasks import models as m


def require_task(db, task_id):
    row = db.get(m.Task, task_id)
    if row is None:
        raise ApiException(404, "NOT_FOUND", "任务不存在")
    return row


def require_run(db, run_id):
    row = db.get(m.Run, run_id)
    if row is None:
        raise ApiException(404, "NOT_FOUND", "运行不存在")
    return row


def sequence_page(db, model, schema, parent_id, after, limit, *, run=False):
    (require_run if run else require_task)(db, parent_id)
    column = model.run_id if run else model.task_id
    rows = list(
        db.scalars(
            select(model)
            .where(column == parent_id, model.sequence > after)
            .order_by(model.sequence)
            .limit(limit + 1)
        )
    )
    items = rows[:limit]
    return {
        "items": [schema.model_validate(i) for i in items],
        "last_sequence": items[-1].sequence if items else after,
        "has_more": len(rows) > limit,
    }


def page(
    db, model, schema, limit, cursor, engagement_id=None, *, task_id=None, run_id=None
):
    filters = []
    scope = "engagements"
    if engagement_id:
        require_engagement(db, engagement_id)
        filters.append(model.engagement_id == engagement_id)
        scope = str(engagement_id)
    if task_id:
        require_task(db, task_id)
        filters.append(model.task_id == task_id)
        scope = model.__tablename__ + ":" + str(task_id)
    if run_id:
        require_run(db, run_id)
        filters.append(model.run_id == run_id)
        scope = model.__tablename__ + ":" + str(run_id)
    return paginate(db, model, schema, limit, cursor, filters=filters, scope=scope)


def get_version(db, task_id, spec_version):
    require_task(db, task_id)
    row = db.scalar(
        select(m.TaskVersion).where(
            m.TaskVersion.task_id == task_id, m.TaskVersion.spec_version == spec_version
        )
    )
    if row is None:
        raise ApiException(404, "NOT_FOUND", "任务版本不存在")
    return row


def list_profiles(db):
    return list(
        db.scalars(
            select(m.ModelProfileRevision).order_by(
                m.ModelProfileRevision.id, m.ModelProfileRevision.revision_id
            )
        )
    )
