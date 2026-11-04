from sqlalchemy import select, text

from onefde.core.errors import ApiException
from onefde.modules.tasks import models as m


def global_slot(db):
    db.execute(text("SELECT pg_advisory_xact_lock(624013, 2)"))


def locked_task(db, task_id, expected_revision=None):
    task = db.scalar(
        select(m.Task)
        .where(m.Task.id == task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if task is None:
        raise ApiException(404, "NOT_FOUND", "任务不存在")
    if expected_revision is not None and task.revision != expected_revision:
        raise ApiException(
            409,
            "REVISION_CONFLICT",
            "任务已变更，请重新读取",
            {"revision": task.revision},
        )
    return task
