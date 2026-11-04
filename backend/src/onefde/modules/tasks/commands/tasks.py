from onefde.core.errors import ApiException
from onefde.modules.engagements.queries import require_engagement
from onefde.modules.tasks import events, versions
from onefde.modules.tasks import models as m
from onefde.modules.tasks import schemas as s
from onefde.modules.tasks.locking import locked_task
from onefde.modules.tasks.policies import (
    no_active,
    no_pending,
    open_task,
    validate_spec,
)
from onefde.modules.tasks.queries import require_task


def update_spec(db, task_id, data, actor):
    task = locked_task(db, task_id, data.expected_revision)
    open_task(task)
    no_active(task)
    no_pending(task)
    validate_spec(data.spec)
    task.spec = data.spec.model_dump(mode="json")
    task.revision += 1
    task.spec_version += 1
    task.state, task.block_reason = "draft", None
    versions.save_version(db, task, actor, "显式替换规格")
    events.task_event(
        db,
        task,
        "state_changed",
        actor,
        "规格更新并回到草稿",
        spec_version=task.spec_version,
    )
    db.flush()
    return s.Task.model_validate(task)


def create_task(db, engagement_id, data, actor="system:bootstrap"):
    require_engagement(db, engagement_id)
    if data.spec.dependencies:
        raise ApiException(
            409, "DEPENDENCIES_NOT_SUPPORTED", "当前切片尚不支持非空任务依赖"
        )
    if data.related_task_id:
        related = require_task(db, data.related_task_id)
        if related.engagement_id != engagement_id:
            raise ApiException(
                409, "CROSS_ENGAGEMENT_REFERENCE", "关联任务必须属于同一项目"
            )
    row = m.Task(
        engagement_id=engagement_id,
        **data.model_dump(exclude={"spec"}),
        spec=data.spec.model_dump(mode="json"),
    )
    db.add(row)
    db.flush()

    versions.save_version(db, row, actor, "创建草稿")
    events.task_event(db, row, "state_changed", actor, "创建草稿")
    db.flush()
    return s.Task.model_validate(row)
