from onefde.core.errors import ApiException
from onefde.modules.tasks import events, input_records
from onefde.modules.tasks import models as m
from onefde.modules.tasks import schemas as s
from onefde.modules.tasks.artifacts import validate_artifacts
from onefde.modules.tasks.locking import locked_task
from onefde.modules.tasks.policies import conflict, no_active, no_pending, open_task
from onefde.modules.tasks.queries import require_run


def review(db, task_id, data, actor, role="founder"):
    if role not in ("founder", "fde"):
        raise ApiException(403, "REVIEW_FORBIDDEN", "工程执行者不能接受自己的提交")
    task = locked_task(db, task_id, data.expected_revision)
    open_task(task)
    no_active(task)
    if task.state != "review":
        conflict("INVALID_TRANSITION", "仅待评审任务可以评审")
    run = require_run(db, data.run_id)
    if (
        run.task_id != task.id
        or run.id != task.latest_run_id
        or run.state != "completed"
        or run.outcome != "submitted"
        or run.task_spec_version != task.spec_version
        or data.task_spec_version != task.spec_version
    ):
        conflict("REVIEW_VERSION_MISMATCH", "评审必须固定当前版本的当前工程提交")
    validate_artifacts(db, data.artifact_ids, task, run.id)
    if data.verdict == "accept":
        no_pending(task)
    row = m.TaskReview(
        task_id=task.id,
        reviewer=actor,
        **data.model_dump(exclude={"expected_revision", "artifact_ids"}),
        artifact_ids=[str(i) for i in data.artifact_ids],
    )
    db.add(row)
    db.flush()
    if data.verdict == "request_changes":
        input_records.add_input(
            db, task, "change_request", data.reason, data.artifact_ids, actor
        )
        task.state = "draft"
    else:
        task.state = "succeeded"
    task.revision += 1
    events.task_event(
        db,
        task,
        "review_recorded",
        actor,
        "已保存固定版本评审：" + data.verdict,
        review_id=str(row.id),
    )
    db.flush()
    return s.TaskReviewed(
        review=s.TaskReview.model_validate(row), task=s.Task.model_validate(task)
    )
