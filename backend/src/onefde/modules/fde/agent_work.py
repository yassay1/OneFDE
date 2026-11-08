"""Durable wakeups and demo authorization for the delivery agent."""

import hashlib
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from onefde.core.clock import now
from onefde.core.errors import ApiException
from onefde.core.fde import AGENT_ACTOR
from onefde.modules.business import models as business
from onefde.modules.business import operations
from onefde.modules.business import service as cases
from onefde.modules.engagements.queries import require_engagement
from onefde.modules.fde.agent_models import AgentGrant, AgentWork
from onefde.modules.fde.support_models import QuoteSupport
from onefde.modules.tasks import models as tasks
from onefde.modules.tasks.assembly import archive_files, canonical_path


def reject(code, message):
    raise ApiException(409, code, message)


def isolated_demo_database(db):
    name = db.get_bind().engine.url.database
    return bool(name and name.endswith("_test"))


def start(db, engagement_id, data, actor, *, preserve_existing_task=False):
    require_engagement(db, engagement_id)
    case = cases.case_for(db, data.case_id, lock=True) if data.case_id else None
    if case:
        pilot = db.get(QuoteSupport, case.id)
        if pilot and pilot.stage not in ("closed", "manual"):
            if preserve_existing_task:
                return None
            reject("FDE_CASE_SCOPE", "原会话已有进行中的报价售后授权")
        prior = db.scalar(
            select(AgentWork).where(
                AgentWork.case_id == case.id, AgentWork.task_id == case.task_id
            )
        )
        if prior:
            if prior.engagement_id != engagement_id or (
                data.goal and data.goal != prior.goal
            ):
                reject("FDE_CASE_SCOPE", "会话已有项目或目标，请续办原工作")
            return view(db, prior)
        if case.engagement_id and case.engagement_id != engagement_id:
            reject("FDE_CASE_SCOPE", "只能关联当前项目的会话")
        if case.state == "fde_queue":
            operations.bind_handoff(db, case, engagement_id, actor)
        if (
            not case.handoff
            or case.handler != actor
            or case.owner != "fde"
            or case.state != "handling"
        ):
            reject("FDE_CASE_SCOPE", "仅可接入已批准且由当前负责人处理的 FDE 交接")
        if case.task_id:
            task = db.get(tasks.Task, case.task_id, with_for_update=True)
            if task.engagement_id != engagement_id:
                reject("FDE_TASK_SCOPE", "会话 Task 不属于当前项目")
            if db.scalar(select(AgentWork.id).where(AgentWork.task_id == task.id)):
                if preserve_existing_task:
                    return None
                reject("FDE_TASK_ALREADY_LINKED", "当前 Task 已有关联的 FDE 工作")
    row = AgentWork(
        engagement_id=engagement_id,
        case_id=data.case_id,
        goal=data.goal or case.handoff["goal"],
        task_id=case.task_id if case else None,
    )
    db.add(row)
    db.flush()
    return view(db, row)


def scoped_case(db, work, *, lock=False):
    if not work.case_id:
        return None
    case = cases.case_for(db, work.case_id, lock=lock)
    if case.engagement_id != work.engagement_id or case.task_id != work.task_id:
        reject("FDE_CASE_SCOPE", "会话项目或 Task 关联已有变动")
    return case


def scoped_task(db, work):
    task = db.get(tasks.Task, work.task_id) if work.task_id else None
    if task and task.engagement_id != work.engagement_id:
        reject("FDE_TASK_SCOPE", "只能读取当前工作关联的任务")
    return task


def customer_head(db, case):
    return db.scalar(
        select(func.max(business.Message.id)).where(
            business.Message.case_id == case.id, business.Message.kind == "customer"
        )
    )


def watermark(db, work, case, task):
    # No polling wakeup for a lease heartbeat or worker start. Terminal results
    # and input adoption advance Task.revision through the existing commands.
    run = db.get(tasks.Run, task.active_run_id) if task and task.active_run_id else None
    revision = task.revision if task else None
    if run and run.state in ("running", "cancel_requested"):
        revision -= 1
    return {
        "case_state": case.state if case else None,
        "case_owner": case.owner if case else None,
        "case_handler": case.handler if case else None,
        "customer": customer_head(db, case) if case else None,
        "public": operations.latest_public_message(db, case) if case else None,
        "task_revision": revision,
    }


def view(db, work):
    try:
        point = watermark(db, work, scoped_case(db, work), scoped_task(db, work))
    except ApiException:
        point = None
    state = "reported" if point == work.completed or point is None else "pending"
    if work.lease_token and work.lease_until and work.lease_until > now():
        state = "processing"
    return {
        "id": work.id,
        "engagement_id": work.engagement_id,
        "case_id": work.case_id,
        "task_id": work.task_id,
        "goal": work.goal,
        "created_at": work.created_at,
        "state": state,
        "report": work.report,
        "trace": work.trace,
        "calls": work.calls,
        "usage": work.usage,
    }


def claim(db, work_id=None):
    query = (
        select(AgentWork)
        .where((AgentWork.lease_until.is_(None)) | (AgentWork.lease_until <= now()))
        .order_by(AgentWork.created_at, AgentWork.id)
    )
    if work_id:
        query = query.where(AgentWork.id == work_id)
    for row in db.scalars(query):
        try:
            point = watermark(db, row, scoped_case(db, row), scoped_task(db, row))
        except ApiException:
            continue
        if row.completed == point:
            continue
        # Re-read after taking the lock to fence a concurrent consumer.
        row = db.scalar(
            select(AgentWork)
            .where(AgentWork.id == row.id)
            .execution_options(populate_existing=True)
            .with_for_update(skip_locked=True)
        )
        if row is None or (row.lease_until and row.lease_until > now()):
            continue
        try:
            case = scoped_case(db, row, lock=True)
            point = watermark(db, row, case, scoped_task(db, row))
        except ApiException:
            continue
        if row.completed == point:
            continue
        row.observed = point
        row.lease_token = uuid4()
        renew(row)
        return row.id, row.lease_token
    return None


def renew(row):
    row.lease_until = now() + timedelta(seconds=150)


def owned(db, work_id, token):
    row = db.scalar(select(AgentWork).where(AgentWork.id == work_id).with_for_update())
    if row is None or row.lease_token != token or row.lease_until <= now():
        reject("FDE_LEASE_LOST", "当前 FDE 处理权已过期")
    case, task = scoped_case(db, row, lock=True), scoped_task(db, row)
    if row.observed != watermark(db, row, case, task):
        reject("FDE_EVIDENCE_CHANGED", "业务记录已有更新，请重新读取")
    renew(row)
    return row, case, task


def enroll(db, work_id, profile_id, policy, archive, store):
    row = db.scalar(select(AgentWork).where(AgentWork.id == work_id).with_for_update())
    if (
        not isolated_demo_database(db)
        or not row
        or not require_engagement(db, row.engagement_id).is_demo
    ):
        reject("FDE_DEMO_ONLY", "自动授权仅适用于显式登记的模拟项目")
    case = scoped_case(db, row, lock=True)
    profile = db.get(tasks.ModelProfileRevision, profile_id)
    if (
        db.get(AgentGrant, row.id)
        or row.calls
        or row.lease_token
        or not profile
        or profile.integration_status == "unavailable"
        or policy.expires_at.utcoffset() is None
        or policy.expires_at <= now()
        or (
            policy.max_clarifications
            and (
                not case
                or not case.handoff
                or not case.handoff.get("is_demo")
                or case.state != "handling"
                or case.owner != "fde"
            )
        )
    ):
        reject("FDE_GRANT_INVALID", "请在处理前登记有效且范围明确的模拟授权")
    files = archive_files(archive)
    allowed = sorted({canonical_path(path) for path in policy.allowed_paths})
    review = sorted({canonical_path(path) for path in policy.review_paths})
    if not set(review) <= files.union(allowed):
        reject("FDE_GRANT_INVALID", "评审路径须在登记的源码或可改范围内")
    if any("\n" in command or len(command) > 500 for command in policy.checks):
        reject("FDE_GRANT_INVALID", "请登记单行固定检查命令")
    key = f"engagements/{row.engagement_id}/engineering-seeds/{policy.source_sha256}.tar.gz"
    if hashlib.sha256(archive).hexdigest() != policy.source_sha256:
        reject("FDE_GRANT_INVALID", "固定源码摘要不符")
    source = store.put(key, archive) | {"object_key": key}
    db.add(
        AgentGrant(
            work_id=row.id,
            profile_id=profile_id,
            expires_at=policy.expires_at,
            policy=policy.model_dump(mode="json", exclude={"expires_at"})
            | {
                "source": source,
                "allowed_paths": allowed,
                "review_paths": review,
            },
        )
    )
    if policy.max_clarifications:
        case.handler = AGENT_ACTOR


def live_grant(db, row, case):
    grant = db.get(AgentGrant, row.id)
    if (
        grant
        and grant.expires_at > now()
        and isolated_demo_database(db)
        and require_engagement(db, row.engagement_id).is_demo
        and (not case or (case.owner == "fde" and case.state == "handling"))
    ):
        return grant
    return None


def _engineering_grant(db, run, worker_cost_usd):
    work = db.scalar(
        select(AgentWork)
        .where(AgentWork.task_id == run.task_id)
        .with_for_update(skip_locked=True)
    )
    if work is None:
        return None
    case = None
    if work.case_id:
        case = db.scalar(
            select(business.Case)
            .where(business.Case.id == work.case_id)
            .with_for_update(skip_locked=True)
        )
        if (
            not case
            or case.engagement_id != work.engagement_id
            or case.task_id != work.task_id
            or case.owner != "fde"
            or case.state != "handling"
        ):
            return None
    grant = live_grant(db, work, case)
    if (
        grant is None
        or worker_cost_usd is None
        or worker_cost_usd * 1_000_000_000
        > grant.policy["max_engineering_cost_nanousd_per_run"]
    ):
        return None
    public = operations.latest_public_message(db, case) if case else None
    if not any(
        receipt["run_id"] == str(run.id) and receipt["public"] == public
        for receipt in grant.runs
    ):
        return None
    return grant, public


def claim_allowed(db, run, worker_cost_usd):
    return (
        run.snapshot.get("actor") != AGENT_ACTOR
        or _engineering_grant(db, run, worker_cost_usd) is not None
    )


def reserve_recovery(db, run, worker_cost_usd):
    if run.snapshot.get("actor") != AGENT_ACTOR:
        return lambda _: None
    authorized = _engineering_grant(db, run, worker_cost_usd)
    if authorized is None:
        return None
    grant, public = authorized
    if len(grant.runs) >= grant.policy["max_runs"] or not db.scalar(
        select(func.has_column_privilege("fde_agent_grants", "runs", "UPDATE"))
    ):
        return None

    def reserve(run_id):
        grant.runs = [
            *grant.runs,
            {
                "run_id": str(run_id),
                "spec_version": run.task_spec_version,
                "public": public,
            },
        ]

    return reserve
