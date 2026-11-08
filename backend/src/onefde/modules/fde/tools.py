"""Trusted FDE tool dispatch. Caller owns the DB transaction."""

from uuid import UUID

from onefde.core.errors import ApiException
from onefde.core.fde import DENIED_TOOL_NAMES, ROLE_REVISION, TOOL_NAMES
from onefde.modules.engagements.queries import require_engagement
from onefde.modules.engagements.schemas import Engagement
from onefde.modules.fde import schemas as fde
from onefde.modules.tasks import queries as task_queries
from onefde.modules.tasks import schemas as tasks
from onefde.modules.tasks import service as task_service


def _forbidden(tool: str):
    if tool in DENIED_TOOL_NAMES:
        raise ApiException(
            403,
            "FDE_TOOL_FORBIDDEN",
            "该操作不在 FDE 受控工具白名单内",
            details={"tool": tool},
        )
    raise ApiException(
        403,
        "FDE_TOOL_UNKNOWN",
        "未知或不允许的 FDE 工具",
        details={"tool": tool},
    )


def _task_in_engagement(db, engagement_id: UUID, task_id: UUID):
    task = task_queries.require_task(db, task_id)
    if task.engagement_id != engagement_id:
        raise ApiException(
            403,
            "FDE_SCOPE_DENIED",
            "只能操作当前项目范围内的任务",
            details={"engagement_id": str(engagement_id), "task_id": str(task_id)},
        )
    return task


def _run_in_engagement(db, engagement_id: UUID, run_id: UUID):
    run = task_queries.require_run(db, run_id)
    _task_in_engagement(db, engagement_id, run.task_id)
    return run


def _read_project(db, engagement_id, actor, arguments):
    if arguments:
        raise ApiException(400, "FDE_BAD_ARGUMENTS", "read_project 不接受参数")
    row = require_engagement(db, engagement_id)
    return {"engagement": Engagement.model_validate(row).model_dump(mode="json")}


def _create_task(db, engagement_id, actor, arguments):
    data = fde.FdeTaskCreate.model_validate(arguments)
    payload = tasks.TaskCreate(
        request_id=data.request_id,
        task_key=data.task_key,
        original_request=data.original_request,
        spec=data.spec,
        owner_role="fde",
        executor_role="engineering",
        related_task_id=data.related_task_id,
    )
    task = task_service.create_task(db, engagement_id, payload, actor)
    return {"task": task.model_dump(mode="json")}


def _save_input(db, engagement_id, actor, arguments):
    task_id = UUID(str(arguments.get("task_id")))
    _task_in_engagement(db, engagement_id, task_id)
    body = {k: v for k, v in arguments.items() if k != "task_id"}
    data = tasks.TaskInputCreate.model_validate(body)
    recorded = task_service.append_input(db, task_id, data, actor)
    return recorded.model_dump(mode="json")


def _adopt_inputs(db, engagement_id, actor, arguments):
    task_id = UUID(str(arguments.get("task_id")))
    _task_in_engagement(db, engagement_id, task_id)
    body = {k: v for k, v in arguments.items() if k != "task_id"}
    data = tasks.TaskInputsApply.model_validate(body)
    task = task_service.apply_inputs(db, task_id, data, actor)
    return {"task": task.model_dump(mode="json")}


def _request_execution(db, engagement_id, actor, arguments):
    task_id = UUID(str(arguments.get("task_id")))
    _task_in_engagement(db, engagement_id, task_id)
    body = {k: v for k, v in arguments.items() if k != "task_id"}
    data = tasks.TaskAction.model_validate(body)
    accepted = task_service.action(db, task_id, data, actor)
    return accepted.model_dump(mode="json")


def _get_task(db, engagement_id, actor, arguments):
    task_id = UUID(str(arguments["task_id"]))
    task = _task_in_engagement(db, engagement_id, task_id)
    return {"task": tasks.Task.model_validate(task).model_dump(mode="json")}


def _get_run(db, engagement_id, actor, arguments):
    run_id = UUID(str(arguments["run_id"]))
    run = _run_in_engagement(db, engagement_id, run_id)
    return {"run": tasks.Run.model_validate(run).model_dump(mode="json")}


def _propose_review(db, engagement_id, actor, arguments):
    task_id = UUID(str(arguments.get("task_id")))
    _task_in_engagement(db, engagement_id, task_id)
    body = {k: v for k, v in arguments.items() if k != "task_id"}
    data = tasks.TaskReviewCreate.model_validate(body)
    reviewed = task_service.review(db, task_id, data, actor, role="fde")
    return reviewed.model_dump(mode="json")


_HANDLERS = {
    "read_project": _read_project,
    "create_task": _create_task,
    "save_input": _save_input,
    "adopt_inputs": _adopt_inputs,
    "request_execution": _request_execution,
    "get_task": _get_task,
    "get_run": _get_run,
    "propose_review": _propose_review,
}


def invoke(
    db, engagement_id: UUID, actor: str, call: fde.FdeToolCall
) -> fde.FdeToolResult:
    require_engagement(db, engagement_id)
    if call.tool not in TOOL_NAMES or call.tool not in _HANDLERS:
        _forbidden(call.tool)
    payload = _HANDLERS[call.tool](db, engagement_id, actor, call.arguments)
    return fde.FdeToolResult(
        tool=call.tool,
        role_revision=ROLE_REVISION,
        engagement_id=engagement_id,
        actor=actor,
        result=payload,
    )
