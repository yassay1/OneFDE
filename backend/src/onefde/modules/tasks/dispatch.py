"""Short PostgreSQL claim/heartbeat/completion transactions. No external execution."""

import copy
import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from onefde.core.clock import now
from onefde.core.errors import ApiException
from onefde.core.security import digest
from onefde.modules.tasks import events
from onefde.modules.tasks import models as m
from onefde.modules.tasks import schemas as s
from onefde.modules.tasks.commands.runs import (
    action,
    mark_run_started,
    record_run_result,
)
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


def claim_next(db, owner, lease_seconds, guard=None):
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
    if guard and not guard(db, run):
        return None
    token = uuid4()
    clock = db.scalar(select(func.clock_timestamp()))
    job.claim_owner, job.claim_token = owner, token
    job.claimed_at = clock
    job.lease_until = clock + timedelta(seconds=lease_seconds)
    job.attempts += 1
    mark_run_started(db, run.id)
    db.flush()
    # Old queued snapshots omit spec_version. Fill only this execution copy.
    snapshot = copy.deepcopy(run.snapshot)
    snapshot["spec_version"] = run.task_spec_version
    return {
        "operation_id": job.operation_id,
        "claim_token": token,
        "run_id": run.id,
        "task_id": task.id,
        "engagement_id": task.engagement_id,
        "snapshot": snapshot,
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


def _normalize_runtime_ref(reference):
    value = copy.deepcopy(reference)
    if "resources" in value:
        return value
    if "container_id" in value or value.get("role") in ("engineering", "validation"):
        item = {key: val for key, val in value.items() if key != "role"}
        return {
            "resources": [{**item, "role": value.get("role", "engineering")}],
            "run_id": value.get("run_id"),
            "session_ref": value.get("session_ref"),
        }
    # Deterministic fixtures and legacy single blobs stay intact.
    return value


def _merge_runtime_ref(current, reference):
    incoming = _normalize_runtime_ref(reference)
    if "resources" not in current or "resources" not in incoming:
        return incoming if current == incoming or current == reference else None
    merged = copy.deepcopy(current)
    for item in incoming["resources"]:
        existing = next(
            (
                row
                for row in merged["resources"]
                if row.get("container_id")
                and row.get("container_id") == item.get("container_id")
            ),
            None,
        )
        if existing is not None:
            if existing != item:
                return None
            continue
        role = item.get("role")
        if role and any(row.get("role") == role for row in merged["resources"]):
            # Same role with a different container replaces only when previous stopped
            # tracking already recorded; Worker must not silently swap live IDs.
            return None
        merged["resources"].append(copy.deepcopy(item))
    for key in ("run_id", "session_ref"):
        if incoming.get(key) and merged.get(key) not in (None, incoming.get(key)):
            return None
        if incoming.get(key):
            merged[key] = incoming[key]
    return merged


def register_resource(db, operation_id, owner, token, reference):
    job = owned_job(db, operation_id, owner, token)
    incoming = _normalize_runtime_ref(reference)
    if job.runtime_ref is None:
        job.runtime_ref = incoming
        return
    if job.runtime_ref == reference or job.runtime_ref == incoming:
        return
    merged = _merge_runtime_ref(job.runtime_ref, incoming)
    if merged is None:
        conflict("RESOURCE_CONFLICT", "已登记的执行现场不可替换")
    job.runtime_ref = merged


def complete_claim(
    db, operation_id, owner, token, payload, artifact_keys, proof, recover=None
):
    global_slot(db)
    job = owned_job(db, operation_id, owner, token, allow_completed=True)
    value = {"result": payload, "artifact_keys": list(artifact_keys), "proof": proof}
    fingerprint = digest(json.dumps(value, sort_keys=True, separators=(",", ":")))
    if job.result_digest:
        if job.result_digest != fingerprint:
            conflict("RUN_RESULT_CONFLICT", "重复回填的结果或证据不一致")
        return s.Run.model_validate(require_run(db, job.run_id))
    run = require_run(db, job.run_id)
    task = locked_task(db, run.task_id)
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
    for attempt in proof.get("submission_diagnostics", []):
        for check in attempt["checks"]:
            code = check.get("exit_code")
            events.run_event(
                db,
                run,
                "check",
                f"提交门槛第 {attempt['phase']} 轮：{check.get('id', 'source')} "
                f"{check['status']}" + (f" (exit {code})" if code is not None else ""),
            )
    db.flush()
    if recover is not None:
        _recover_exhausted(db, task, run, result, proof, recover)
    return accepted


def _recover_exhausted(db, task, run, result, proof, authorize):
    engineering = run.snapshot.get("engineering") or {}
    source = engineering.get("initial_source") or {}
    if (
        result.state != "failed"
        or result.error_code != "ITERATION_LIMIT_REACHED"
        or not result.stopped
        or proof.get("stop_reason") != "ITERATION_LIMIT_REACHED"
        or not proof.get("source_digest")
        or source.get("assembly_revision") != "standard-v1"
        or source.get("task_id") != str(task.id)
        or source.get("engagement_id") != str(task.engagement_id)
        or task.latest_run_id != run.id
        or task.spec_version != run.task_spec_version
        or task.pending_input_count
        or engineering.get("recovery_parent_run_id")
        or not run.model_profile_revision_id
    ):
        return
    if db.scalar(
        select(m.Run.id)
        .where(
            m.Run.task_id == task.id,
            m.Run.snapshot["engineering"]["recovery_parent_run_id"].astext.is_not(None),
        )
        .limit(1)
    ):
        return
    candidate = db.scalar(
        select(m.Artifact).where(
            m.Artifact.run_id == run.id,
            m.Artifact.engagement_id == task.engagement_id,
            m.Artifact.kind == "source-snapshot",
        )
    )
    if candidate is None:
        return
    if not db.scalar(
        select(
            func.has_table_privilege("runs", "INSERT")
            & func.has_table_privilege("dispatch_jobs", "INSERT")
        )
    ):
        return
    try:
        with db.begin_nested():
            authorization = authorize(db, run)
            if authorization is None:
                return
            reserve, policy = authorization
            accepted = action(
                db,
                task.id,
                s.TaskAction(
                    command="retry",
                    expected_revision=task.revision,
                    expected_run_id=run.id,
                    model_profile_revision_id=run.model_profile_revision_id,
                ),
                run.snapshot["actor"],
                initial_source=source,
                recovery_source=candidate,
                recovery_policy=policy,
            )
            reserve(accepted.run.id)
            events.run_event(
                db,
                run,
                "state",
                f"已登记同 Task 自动续办 {accepted.run.id}",
                recovery_run_id=str(accepted.run.id),
                candidate_artifact_id=str(candidate.id),
            )
    except ApiException:
        # Completion is durable even if current controls prevent a successor.
        return
