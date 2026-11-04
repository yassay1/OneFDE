from onefde.modules.tasks import events, input_records, versions
from onefde.modules.tasks import models as m
from onefde.modules.tasks import schemas as s
from onefde.modules.tasks.locking import locked_task
from onefde.modules.tasks.policies import conflict, no_active, open_task, validate_spec


def append_input(db, task_id, data, actor):
    task = locked_task(db, task_id, data.expected_revision)
    open_task(task)
    item = input_records.add_input(
        db,
        task,
        data.kind,
        data.text,
        data.evidence_artifact_ids,
        actor,
        data.reply_to_input_id,
    )
    task.revision += 1
    db.flush()
    return s.TaskInputRecorded(
        input=s.TaskInput.model_validate(item), task=s.Task.model_validate(task)
    )


def apply_inputs(db, task_id, data, actor):
    task = locked_task(db, task_id, data.expected_revision)
    open_task(task)
    no_active(task)
    apply_ids, reject_ids = set(data.apply_ids), set(data.reject_ids)
    records = {}
    for identifier in apply_ids | reject_ids:
        row = db.get(m.TaskInput, identifier)
        if not row or row.task_id != task.id or row.status != "pending":
            conflict("INPUT_SCOPE_CONFLICT", "只能处理本任务尚未处理的输入")
        records[identifier] = row
    answers = {}
    for identifier in list(apply_ids):
        row = records[identifier]
        if row.kind == "answer":
            question = db.get(m.TaskInput, row.reply_to_input_id)
            if (
                not question
                or question.task_id != task.id
                or question.status != "pending"
                or question.id in reject_ids
                or question.resolved_by_input_id
            ):
                conflict("INVALID_REPLY", "回答对应的问题已处理或被拒绝")
            if question.id in answers:
                conflict("MULTIPLE_ANSWERS", "同次采用只能为一个问题选择一个答案")
            answers[question.id] = row
            records[question.id] = question
            apply_ids.add(question.id)
    for identifier in apply_ids:
        row = records[identifier]
        if row.kind == "question" and identifier not in answers:
            conflict("QUESTION_REQUIRES_ANSWER", "采用问题必须同时采用对应答案")
    if (
        any(records[i].kind in ("clarification", "change_request") for i in apply_ids)
        and data.spec is None
    ):
        conflict("SPEC_REQUIRED", "采用范围或规则变更必须提交完整规格")
    if data.spec is not None:
        validate_spec(data.spec)
        task.spec = data.spec.model_dump(mode="json")
    if apply_ids:
        task.spec_version += 1
    for identifier in apply_ids | reject_ids:
        row = records[identifier]
        row.status = "applied" if identifier in apply_ids else "rejected"
        row.applied_spec_version = (
            task.spec_version if identifier in apply_ids else None
        )
        row.processed_by, row.processing_reason, row.processed_at = (
            actor,
            data.reason,
            m.now(),
        )
        if identifier in answers:
            row.resolved_by_input_id = answers[identifier].id
    task.pending_input_count -= len(apply_ids | reject_ids)
    task.revision += 1
    if task.state != "waiting_input":
        task.state, task.block_reason = "draft", None
    if apply_ids:
        versions.save_version(db, task, actor, data.reason)
    events.task_event(
        db,
        task,
        "inputs_processed",
        actor,
        "输入已明确采用或拒绝",
        apply_ids=sorted(map(str, apply_ids)),
        reject_ids=sorted(map(str, reject_ids)),
        reason=data.reason,
    )
    db.flush()
    return s.Task.model_validate(task)
