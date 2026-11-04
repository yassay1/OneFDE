from onefde.modules.tasks import events
from onefde.modules.tasks import models as m
from onefde.modules.tasks.artifacts import validate_artifacts
from onefde.modules.tasks.policies import conflict


def add_input(
    db, task, kind, value, evidence, actor, reply=None, origin=None, action=None
):
    validate_artifacts(db, evidence, task)
    if kind == "answer":
        question = db.get(m.TaskInput, reply)
        if not question or question.task_id != task.id or question.kind != "question":
            conflict("INVALID_REPLY", "回答必须指向同任务的问题")
        if question.status != "pending" or question.resolved_by_input_id:
            conflict("QUESTION_CLOSED", "问题已处理，不能追加新答案")
    task.input_sequence += 1
    task.pending_input_count += 1
    item = m.TaskInput(
        task_id=task.id,
        sequence=task.input_sequence,
        kind=kind,
        text=value,
        evidence_artifact_ids=[str(i) for i in evidence],
        reply_to_input_id=reply,
        author=actor,
        origin_run_id=origin,
        action_id=action,
    )
    db.add(item)
    db.flush()
    events.task_event(
        db,
        task,
        "input_recorded",
        actor,
        "已记录输入，尚未采用",
        input_id=str(item.id),
        input_kind=kind,
    )
    return item
