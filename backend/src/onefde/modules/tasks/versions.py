import copy

from sqlalchemy import select

from onefde.modules.tasks import models as m


def save_version(db, task, actor, reason):
    db.flush()
    adopted = list(
        db.scalars(
            select(m.TaskInput)
            .where(m.TaskInput.task_id == task.id, m.TaskInput.status == "applied")
            .order_by(m.TaskInput.sequence)
        )
    )
    row = m.TaskVersion(
        task_id=task.id,
        spec_version=task.spec_version,
        spec=copy.deepcopy(task.spec),
        applied_input_ids=[str(i.id) for i in adopted],
        actor=actor,
        reason=reason,
    )
    db.add(row)
    db.flush()
    return row
