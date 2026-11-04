from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Request

from onefde.infrastructure.idempotency import idempotent_create
from onefde.infrastructure.web.dependencies import DB, After, Key, Limit
from onefde.modules.auth.dependencies import Current, WriteSession
from onefde.modules.tasks import models as m
from onefde.modules.tasks import queries, schemas
from onefde.modules.tasks import schemas as s
from onefde.modules.tasks import service as services
from onefde.modules.tasks import service as tasks

business_router = APIRouter(prefix="/api/v1", tags=["business"])
router = APIRouter(prefix="/api/v1", tags=["tasks"])


@business_router.get(
    "/engagements/{engagement_id}/tasks",
    response_model=schemas.Page[schemas.Task],
    operation_id="listTasks",
)
def list_tasks(
    engagement_id: UUID,
    current: Current,
    db: DB,
    limit: Limit = 50,
    cursor: str | None = None,
):
    return queries.page(db, m.Task, schemas.Task, limit, cursor, engagement_id)


@business_router.post(
    "/engagements/{engagement_id}/tasks",
    status_code=201,
    response_model=schemas.Task,
    operation_id="createTask",
)
def create_task(
    engagement_id: UUID,
    data: schemas.TaskCreate,
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
        lambda: services.create_task(db, engagement_id, data, current.username),
    )


@business_router.get(
    "/tasks/{task_id}", response_model=schemas.Task, operation_id="getTask"
)
def get_task(task_id: UUID, current: Current, db: DB):
    return queries.require_task(db, task_id)


def command(db, current, request, key, data, function, status=200):
    return idempotent_create(
        db,
        current.username,
        request.url.path,
        key,
        data,
        function,
        method=request.method,
        status_code=status,
    )


@router.patch("/tasks/{task_id}", response_model=s.Task, operation_id="updateTaskSpec")
def update_spec(
    task_id: UUID,
    data: s.TaskSpecUpdate,
    current: WriteSession,
    db: DB,
    request: Request,
    key: Key,
):
    return command(
        db,
        current,
        request,
        key,
        data,
        lambda: tasks.update_spec(db, task_id, data, current.username),
    )


@router.post(
    "/tasks/{task_id}/inputs",
    status_code=201,
    response_model=s.TaskInputRecorded,
    operation_id="appendTaskInput",
)
def append_input(
    task_id: UUID,
    data: s.TaskInputCreate,
    current: WriteSession,
    db: DB,
    request: Request,
    key: Key,
):
    return command(
        db,
        current,
        request,
        key,
        data,
        lambda: tasks.append_input(db, task_id, data, current.username),
        201,
    )


@router.get(
    "/tasks/{task_id}/inputs",
    response_model=s.SequencePage[s.TaskInput],
    operation_id="listTaskInputs",
)
def list_inputs(
    task_id: UUID,
    current: Current,
    db: DB,
    after_sequence: After = 0,
    limit: Limit = 50,
):
    return queries.sequence_page(
        db, m.TaskInput, s.TaskInput, task_id, after_sequence, limit
    )


@router.post(
    "/tasks/{task_id}/apply-inputs",
    response_model=s.Task,
    operation_id="applyTaskInputs",
)
def apply_inputs(
    task_id: UUID,
    data: s.TaskInputsApply,
    current: WriteSession,
    db: DB,
    request: Request,
    key: Key,
):
    return command(
        db,
        current,
        request,
        key,
        data,
        lambda: tasks.apply_inputs(db, task_id, data, current.username),
    )


@router.post(
    "/tasks/{task_id}/actions",
    status_code=202,
    response_model=s.ActionAccepted,
    operation_id="actOnTask",
    description="仅持久登记命令、Run和待派发作业；当前未接Worker，不执行模型或工程。",
)
def action(
    task_id: UUID,
    data: s.TaskAction,
    current: WriteSession,
    db: DB,
    request: Request,
    key: Key,
):
    return command(
        db,
        current,
        request,
        key,
        data,
        lambda: tasks.action(db, task_id, data, current.username),
        202,
    )


@router.get(
    "/tasks/{task_id}/runs", response_model=s.Page[s.Run], operation_id="listRuns"
)
def list_runs(
    task_id: UUID,
    current: Current,
    db: DB,
    limit: Limit = 50,
    cursor: str | None = None,
):
    return queries.page(db, m.Run, s.Run, limit, cursor, task_id=task_id)


@router.get("/runs/{run_id}", response_model=s.Run, operation_id="getRun")
def get_run(run_id: UUID, current: Current, db: DB):
    return queries.require_run(db, run_id)


@router.get(
    "/runs/{run_id}/events",
    response_model=s.SequencePage[s.RunEvent],
    operation_id="listRunEvents",
)
def list_run_events(
    run_id: UUID, current: Current, db: DB, after_sequence: After = 0, limit: Limit = 50
):
    return queries.sequence_page(
        db, m.RunEvent, s.RunEvent, run_id, after_sequence, limit, run=True
    )


@router.get(
    "/runs/{run_id}/artifacts",
    response_model=s.Page[s.Artifact],
    operation_id="listArtifacts",
)
def list_artifacts(
    run_id: UUID, current: Current, db: DB, limit: Limit = 50, cursor: str | None = None
):
    return queries.page(db, m.Artifact, s.Artifact, limit, cursor, run_id=run_id)


@router.post(
    "/tasks/{task_id}/reviews",
    status_code=201,
    response_model=s.TaskReviewed,
    operation_id="reviewTask",
)
def review(
    task_id: UUID,
    data: s.TaskReviewCreate,
    current: WriteSession,
    db: DB,
    request: Request,
    key: Key,
):
    return command(
        db,
        current,
        request,
        key,
        data,
        lambda: tasks.review(db, task_id, data, current.username),
        201,
    )


@router.get(
    "/tasks/{task_id}/reviews",
    response_model=s.Page[s.TaskReview],
    operation_id="listTaskReviews",
)
def list_reviews(
    task_id: UUID,
    current: Current,
    db: DB,
    limit: Limit = 50,
    cursor: str | None = None,
):
    return queries.page(db, m.TaskReview, s.TaskReview, limit, cursor, task_id=task_id)


@router.get(
    "/tasks/{task_id}/events",
    response_model=s.SequencePage[s.TaskEvent],
    operation_id="listTaskEvents",
)
def list_events(
    task_id: UUID,
    current: Current,
    db: DB,
    after_sequence: After = 0,
    limit: Limit = 50,
):
    return queries.sequence_page(
        db, m.TaskEvent, s.TaskEvent, task_id, after_sequence, limit
    )


@router.get(
    "/tasks/{task_id}/versions",
    response_model=s.Page[s.TaskVersion],
    operation_id="listTaskVersions",
)
def list_versions(
    task_id: UUID,
    current: Current,
    db: DB,
    limit: Limit = 50,
    cursor: str | None = None,
):
    return queries.page(
        db, m.TaskVersion, s.TaskVersion, limit, cursor, task_id=task_id
    )


@router.get(
    "/tasks/{task_id}/versions/{spec_version}",
    response_model=s.TaskVersion,
    operation_id="getTaskVersion",
)
def get_version(
    task_id: UUID, spec_version: Annotated[int, Path(ge=1)], current: Current, db: DB
):
    return queries.get_version(db, task_id, spec_version)


@router.get(
    "/model-profiles",
    response_model=list[s.ModelProfile],
    operation_id="listModelProfiles",
)
def list_profiles(current: Current, db: DB):
    return queries.list_profiles(db)
