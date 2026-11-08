import copy
import json
from uuid import uuid4, uuid5

from sqlalchemy import func, select

from onefde.core.engineering import CONTEXT_REVISION, ROLE_REVISION, derive_checks
from onefde.core.security import digest
from onefde.modules.tasks import events, input_records
from onefde.modules.tasks import models as m
from onefde.modules.tasks import schemas as s
from onefde.modules.tasks.locking import global_slot, locked_task
from onefde.modules.tasks.policies import (
    ACTIVE,
    conflict,
    no_active,
    no_pending,
    open_task,
    validate_spec,
)
from onefde.modules.tasks.queries import require_run


def trusted_prior_source(db, task_id):
    """Latest source archive from a confirmed-stopped completed or failed Run.

    Interrupted runs are not a baseline. The caller still compares the workspace
    to this archive and blocks unknown drift.
    """
    return db.scalar(
        select(m.Artifact)
        .join(m.Run, m.Run.id == m.Artifact.run_id)
        .where(
            m.Run.task_id == task_id,
            m.Artifact.kind == "source-snapshot",
            m.Run.finished_at.is_not(None),
            m.Run.state.in_(("completed", "failed")),
        )
        .order_by(m.Run.finished_at.desc(), m.Artifact.created_at.desc())
        .limit(1)
    )


def current_prior(db, task, expected_id, state):
    if expected_id != task.latest_run_id:
        conflict("RUN_MISMATCH", "命令必须引用当前最近运行")
    run = require_run(db, expected_id)
    if run.task_id != task.id or run.state not in state:
        conflict("RUN_NOT_STOPPED", "前次运行尚未确认停止或结果不适用")
    return run


def action(
    db,
    task_id,
    data,
    actor,
    *,
    initial_source=None,
    reuse_asset=None,
    recovery_source=None,
    recovery_policy=None,
):
    global_slot(db)
    task = locked_task(db, task_id, data.expected_revision)
    open_task(task)
    operation_id, run = uuid4(), None
    command = data.command
    if command == "queue":
        no_active(task)
        no_pending(task)
        if task.state not in ("draft", "blocked"):
            conflict("INVALID_TRANSITION", "只有草稿或已停止的阻塞任务可以准备")
        task.state, task.block_reason = "queued", None
    elif command in ("start", "retry", "continue"):
        no_active(task)
        no_pending(task)
        expected_state = {
            "start": "queued",
            "retry": "blocked",
            "continue": "waiting_input",
        }[command]
        if task.state != expected_state:
            conflict("INVALID_TRANSITION", "任务状态不允许此启动命令")
        if command == "retry":
            current_prior(db, task, data.expected_run_id, ("failed", "cancelled"))
        if command == "continue":
            prior = current_prior(db, task, data.expected_run_id, ("completed",))
            if prior.outcome != "needs_input":
                conflict("INVALID_TRANSITION", "续作必须引用已结束的待答运行")
            questions = list(
                db.scalars(
                    select(m.TaskInput).where(
                        m.TaskInput.origin_run_id == prior.id,
                        m.TaskInput.kind == "question",
                    )
                )
            )
            if not questions or any(
                q.status != "applied" or not q.resolved_by_input_id for q in questions
            ):
                conflict("QUESTION_UNRESOLVED", "续作要求原问题已有明确采用的答案")
        validate_spec(s.TaskSpec.model_validate(task.spec))
        if db.scalar(select(m.Run.id).where(m.Run.state.in_(ACTIVE)).limit(1)):
            conflict("ACTIVE_RUN_EXISTS", "全局已有活动或现场不明的工程运行")
        verification = isinstance(data, s.VerificationStart)
        if verification and (not initial_source or not reuse_asset):
            conflict("REUSE_SOURCE_REQUIRED", "复用验证必须固定已授权能力及归档")
        profile = (
            None
            if verification
            else db.get(m.ModelProfileRevision, data.model_profile_revision_id)
        )
        if not verification and (
            not profile or profile.integration_status == "unavailable"
        ):
            conflict(
                "MODEL_PROFILE_UNAVAILABLE", "未供给可用模型配置修订；当前不会调用模型"
            )
        if profile and set(profile.config) - {
            "base_url",
            "secret_ref",
            "max_requests",
            "timeout_seconds",
            "adapter",
        }:
            conflict(
                "MODEL_PROFILE_UNAVAILABLE",
                "配置仅可保存端点、secret引用和限额，不接受原始凭据",
            )
        version = db.scalar(
            select(m.TaskVersion).where(
                m.TaskVersion.task_id == task.id,
                m.TaskVersion.spec_version == task.spec_version,
            )
        )
        inputs = list(
            db.scalars(
                select(m.TaskInput)
                .where(m.TaskInput.task_id == task.id, m.TaskInput.status == "applied")
                .order_by(m.TaskInput.sequence)
            )
        )
        attempt = (
            db.scalar(select(func.max(m.Run.attempt)).where(m.Run.task_id == task.id))
            or 0
        ) + 1
        # A trusted start or retry can explicitly pin its baseline. The Worker
        # still compares the existing workspace before allowing any writes.
        prior_source = recovery_source or (
            None
            if command in ("start", "retry") and initial_source is not None
            else trusted_prior_source(db, task.id)
        )
        prior_failures = [
            {
                "run_id": str(item.id),
                "state": item.state,
                "error_code": item.error_code,
                "summary": item.result_summary,
            }
            for item in db.scalars(
                select(m.Run)
                .where(
                    m.Run.task_id == task.id,
                    m.Run.state.in_(("failed", "cancelled", "interrupted")),
                )
                .order_by(m.Run.finished_at.desc())
                .limit(5)
            )
        ]
        checks = derive_checks(version.spec)
        run = m.Run(
            task_id=task.id,
            task_spec_version=task.spec_version,
            attempt=attempt,
            model_profile_revision_id=profile.revision_id if profile else None,
            applied_input_ids=copy.deepcopy(version.applied_input_ids),
            snapshot={
                "spec_version": task.spec_version,
                "original_request": task.original_request,
                "spec": copy.deepcopy(version.spec),
                "inputs": [
                    s.TaskInput.model_validate(i).model_dump(mode="json")
                    for i in inputs
                ],
                "actor": actor,
                "owner_role": task.owner_role,
                "executor_role": task.executor_role,
                "model_profile": (
                    s.ModelProfile.model_validate(profile).model_dump(mode="json")
                    if profile
                    else None
                ),
                "config": copy.deepcopy(profile.config) if profile else {},
                "permissions": ["engineering:task-workspace"],
                "engineering": {
                    "role_revision": ROLE_REVISION,
                    "context_revision": CONTEXT_REVISION,
                    "checks": checks,
                    "prior_source": (
                        {
                            "artifact_id": str(prior_source.id),
                            "object_key": prior_source.object_key,
                            "sha256": prior_source.sha256,
                            "size_bytes": prior_source.size_bytes,
                            "run_id": str(prior_source.run_id),
                        }
                        if prior_source
                        else None
                    ),
                    "prior_failures": prior_failures,
                    "workspace_policy": "compare_or_block",
                    **(
                        {
                            "recovery_parent_run_id": str(recovery_source.run_id),
                            "recovery_policy": recovery_policy,
                        }
                        if recovery_source is not None
                        else {}
                    ),
                    **({"reuse_asset": reuse_asset} if verification else {}),
                    **(
                        {"initial_source": copy.deepcopy(initial_source)}
                        if initial_source
                        else {}
                    ),
                },
            },
        )
        db.add(run)
        db.flush()
        db.add(
            m.DispatchJob(
                operation_id=operation_id,
                run_id=run.id,
                payload={"run_id": str(run.id)},
            )
        )
        task.state, task.active_run_id, task.latest_run_id, task.block_reason = (
            "running",
            run.id,
            run.id,
            None,
        )
        events.run_event(db, run, "state", "已登记待派发；尚未执行")
        events.task_event(
            db,
            task,
            "run_created",
            actor,
            "已持久接单；尚未执行",
            run_id=str(run.id),
            operation_id=str(operation_id),
        )
    else:
        if task.active_run_id:
            if task.active_run_id != data.expected_run_id:
                conflict("RUN_MISMATCH", "停止命令必须引用当前活动运行")
            run = require_run(db, task.active_run_id)
            if run.state == "interrupted":
                conflict("RUN_NOT_STOPPED", "现场不明，必须先受控核查")
            if run.state == "cancel_requested":
                conflict("INVALID_TRANSITION", "停止意图已登记，不可覆盖")
            job = db.scalar(
                select(m.DispatchJob)
                .where(m.DispatchJob.run_id == run.id)
                .with_for_update()
            )
            run.stop_reason = command
            if run.state == "queued" and job.state == "pending":
                # Locked, never claimed job: no runtime exists, so stopping is provable locally.
                result = s.RunResult(
                    state="cancelled" if command == "cancel" else "completed",
                    outcome=None if command == "cancel" else "superseded",
                    summary="未认领作业已撤销，未执行任何工程",
                    stopped=True,
                )
                apply_result(db, task, run, job, result, bump=False)
            else:
                run.state, job.state = "cancel_requested", "cancel_requested"
                events.run_event(db, run, "state", "停止意图已记录，尚未确认停止")
        elif command == "cancel":
            if data.expected_run_id is not None:
                conflict("RUN_MISMATCH", "无活动运行的取消须传 null")
            task.state, task.block_reason = "cancelled", None
        else:
            conflict("INVALID_TRANSITION", "当前没有可停止的运行")
    task.revision += 1
    events.task_event(
        db,
        task,
        "state_changed",
        actor,
        "已记录任务命令：" + command,
        operation_id=str(operation_id),
    )
    db.flush()
    return s.ActionAccepted(
        operation_id=operation_id,
        task=s.Task.model_validate(task),
        run=s.Run.model_validate(run) if run else None,
    )


def mark_run_started(db, run_id):
    """Trusted domain transition; Worker claim wraps it. No HTTP claim endpoint."""
    global_slot(db)
    run = require_run(db, run_id)
    task = locked_task(db, run.task_id)
    job = db.scalar(
        select(m.DispatchJob).where(m.DispatchJob.run_id == run.id).with_for_update()
    )
    if task.active_run_id != run.id or run.state != "queued" or job.state != "pending":
        conflict("INVALID_TRANSITION", "只有当前未认领运行可进入执行状态")
    no_pending(task)
    if task.spec_version != run.task_spec_version:
        conflict("RUN_MISMATCH", "运行规格已失效")
    run.state, job.state = "running", "running"
    task.revision += 1
    events.run_event(db, run, "state", "受控适配已确认开始本轮")
    events.task_event(
        db, task, "state_changed", "runtime", "已确认本轮开始", run_id=str(run.id)
    )
    db.flush()


def apply_result(db, task, run, job, result, bump=True, artifact_keys=None):
    actor = "engineering:run:" + str(run.id)
    run.state, run.outcome = result.state, result.outcome
    run.result_summary, run.error_code = result.summary, result.error_code
    run.result_hash = digest(json.dumps(result.model_dump(mode="json"), sort_keys=True))
    run.finished_at = m.now() if result.stopped else None
    job.state = result.state
    if artifact_keys is not None and (
        len(artifact_keys) != len(result.artifacts)
        or any(
            not key.startswith(f"engagements/{task.engagement_id}/runs/{run.id}/")
            or ".." in key.split("/")
            for key in artifact_keys
        )
    ):
        conflict("ARTIFACT_SCOPE_CONFLICT", "受控产物存储引用不属于当前运行")
    for index, value in enumerate(result.artifacts):
        identifier = uuid4()
        db.add(
            m.Artifact(
                id=identifier,
                engagement_id=task.engagement_id,
                run_id=run.id,
                object_key=artifact_keys[index]
                if artifact_keys is not None
                else f"engagements/{task.engagement_id}/runs/{run.id}/{identifier}",
                **value.model_dump(),
            )
        )
        events.run_event(
            db, run, "artifact", "已登记固定产物元数据", artifact_id=str(identifier)
        )
    if result.outcome == "needs_input":
        input_records.add_input(
            db,
            task,
            "question",
            result.question,
            [],
            actor,
            origin=run.id,
            action=uuid5(run.id, "result-question"),
        )
    if result.state == "interrupted":
        task.state, task.block_reason = "blocked", "RUN_INTERRUPTED"
    else:
        task.active_run_id = None
        task.block_reason = result.error_code if result.state == "failed" else None
        if result.state == "failed":
            task.state = "blocked"
        elif result.state == "cancelled":
            task.state = "cancelled"
        elif result.outcome == "needs_input":
            task.state = "waiting_input"
        elif result.outcome == "submitted" and not task.pending_input_count:
            task.state = "review"
        else:
            task.state = "draft"
    if bump:
        task.revision += 1
    events.run_event(db, run, "state", "运行事实已登记：" + result.state)
    events.task_event(
        db,
        task,
        "state_changed",
        actor,
        "运行结束与业务接受分开登记",
        run_id=str(run.id),
    )
    db.flush()


def record_run_result(db, run_id, result, *, artifact_keys=None):
    """Trusted internal result registration; caller commits. Never exposed as an owner API.

    C2 Worker verifies private blobs and stop evidence before calling this boundary.
    C1b tests supply explicitly simulated evidence.
    """
    global_slot(db)
    run = require_run(db, run_id)
    task = locked_task(db, run.task_id)
    fingerprint = digest(json.dumps(result.model_dump(mode="json"), sort_keys=True))
    if run.result_hash:
        if run.result_hash == fingerprint:
            return s.Run.model_validate(run)
        conflict("RUN_RESULT_CONFLICT", "已登记的运行事实不可被不同结果覆盖")
    if task.active_run_id != run.id or task.spec_version != run.task_spec_version:
        conflict("RUN_MISMATCH", "迟到或旧版本结果不可覆盖当前任务")
    if run.state not in ("running", "cancel_requested"):
        conflict("RUN_NOT_STOPPED", "未开始或现场不明的运行不能直接登记结束")
    if run.state == "cancel_requested" and result.state != "interrupted":
        if run.stop_reason == "cancel" and result.state != "cancelled":
            conflict("RUN_STOP_MISMATCH", "业务取消必须确认取消结果")
        if run.stop_reason == "stop_for_update" and (
            result.state != "completed" or result.outcome != "superseded"
        ):
            conflict("RUN_STOP_MISMATCH", "停止本轮必须确认 superseded")
    job = db.scalar(
        select(m.DispatchJob).where(m.DispatchJob.run_id == run.id).with_for_update()
    )
    apply_result(db, task, run, job, result, artifact_keys=artifact_keys)
    return s.Run.model_validate(run)
