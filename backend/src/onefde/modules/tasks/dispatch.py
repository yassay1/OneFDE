"""Short PostgreSQL claim/heartbeat/completion transactions. No external execution."""

import copy
import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from onefde.core.clock import now
from onefde.core.errors import ApiException
from onefde.core.security import digest
from onefde.modules.tasks import models as m
from onefde.modules.tasks import schemas as s
from onefde.modules.tasks.commands.runs import mark_run_started, record_run_result
from onefde.modules.tasks.locking import global_slot, locked_task
from onefde.modules.tasks.policies import conflict
from onefde.modules.tasks.queries import require_run


def expire_claims(db):
    """Lease expiry is uncertainty, never permission to execute the job again."""
    global_slot(db)
    jobs = list(
        db.scalars(
            select(m.DispatchJob)
            .where(
                m.DispatchJob.state.in_(("running", "cancel_requested")),
                m.DispatchJob.lease_until <= db.scalar(select(func.clock_timestamp())),
            )
            .with_for_update(skip_locked=True)
        )
    )
    for job in jobs:
        run = require_run(db, job.run_id)
        if run.state in ("running", "cancel_requested"):
            result = s.RunResult(
                state="interrupted",
                summary="Worker租约过期，现场尚未核实",
                stopped=False,
                error_code="WORKER_LEASE_EXPIRED",
            )
            record_run_result(db, run.id, result)
    db.flush()
    return len(jobs)


def claim_next(db, owner, lease_seconds):
    global_slot(db)
    expire_claims(db)
    if db.scalar(select(m.Run.id).where(m.Run.state == "interrupted").limit(1)):
        return None
    job = db.scalar(
        select(m.DispatchJob)
        .where(m.DispatchJob.state == "pending")
        .order_by(m.DispatchJob.operation_id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    run = require_run(db, job.run_id)
    task = locked_task(db, run.task_id)
    if run.state != "queued" or task.active_run_id != run.id:
        conflict("RUN_MISMATCH", "待派发作业不再属于当前运行")
    # Pending input leaves the unclaimed job visible for explicit stop/update.
    if task.pending_input_count or run.task_spec_version != task.spec_version:
        return None
    token = uuid4()
    clock = db.scalar(select(func.clock_timestamp()))
    job.claim_owner, job.claim_token = owner, token
    job.claimed_at = clock
    job.lease_until = clock + timedelta(seconds=lease_seconds)
    job.attempts += 1
    mark_run_started(db, run.id)
    db.flush()
    return {
        "operation_id": job.operation_id,
        "claim_token": token,
        "run_id": run.id,
        "task_id": task.id,
        "engagement_id": task.engagement_id,
        "snapshot": copy.deepcopy(run.snapshot),
    }


def owned_job(db, operation_id, owner, token, *, allow_completed=False):
    job = db.scalar(
        select(m.DispatchJob)
        .where(m.DispatchJob.operation_id == operation_id)
        .with_for_update()
    )
    if not job or job.claim_owner != owner or job.claim_token != token:
        raise ApiException(409, "CLAIM_LOST", "作业不属于当前Worker代次")
    if allow_completed and job.result_digest:
        return job
    if job.state not in ("running", "cancel_requested") or job.lease_until <= db.scalar(
        select(func.clock_timestamp())
    ):
        raise ApiException(409, "CLAIM_LOST", "租约已失效，不能覆盖运行事实")
    return job


def heartbeat_claim(db, operation_id, owner, token, lease_seconds):
    job = owned_job(db, operation_id, owner, token)
    job.lease_until = db.scalar(select(func.clock_timestamp())) + timedelta(
        seconds=lease_seconds
    )
    run = require_run(db, job.run_id)
    return run.state == "cancel_requested"


def register_resource(db, operation_id, owner, token, reference):
    job = owned_job(db, operation_id, owner, token)
    if job.runtime_ref is not None and job.runtime_ref != reference:
        conflict("RESOURCE_CONFLICT", "已登记的执行现场不可替换")
    job.runtime_ref = copy.deepcopy(reference)


def complete_claim(db, operation_id, owner, token, payload, artifact_keys, proof):
    global_slot(db)
    job = owned_job(db, operation_id, owner, token, allow_completed=True)
    value = {"result": payload, "artifact_keys": list(artifact_keys), "proof": proof}
    fingerprint = digest(json.dumps(value, sort_keys=True, separators=(",", ":")))
    if job.result_digest:
        if job.result_digest != fingerprint:
            conflict("RUN_RESULT_CONFLICT", "重复回填的结果或证据不一致")
        return s.Run.model_validate(require_run(db, job.run_id))
    run = require_run(db, job.run_id)
    locked_task(db, run.task_id)
    result = s.RunResult.model_validate(payload)
    if result.stopped and proof.get("stopped") is not True:
        conflict("STOP_UNCONFIRMED", "没有已停止证据，不能释放运行占用")
    # Stop intent may arrive after adapter completion; normalize under the same lock.
    if run.state == "cancel_requested" and result.state != "interrupted":
        result = s.RunResult(
            state="cancelled" if run.stop_reason == "cancel" else "completed",
            outcome=None if run.stop_reason == "cancel" else "superseded",
            summary="已确认停止；遵循当前停止意图",
            stopped=True,
            artifacts=result.artifacts,
        )
    accepted = record_run_result(db, run.id, result, artifact_keys=artifact_keys)
    job.result_digest = fingerprint
    job.result_payload = {
        "result": result.model_dump(mode="json"),
        "artifact_keys": list(artifact_keys),
        "proof": copy.deepcopy(proof),
    }
    job.completed_at = now() if result.stopped else None
    db.flush()
    return accepted
