"""Model-facing capabilities. Every mutation uses the current durable work scope."""

from typing import Literal
from uuid import UUID

from pydantic import Field
from sqlalchemy import select

from onefde.core.engineering import derive_checks
from onefde.core.errors import ApiException
from onefde.core.fde import AGENT_ACTOR
from onefde.core.schemas import Input, Nonblank, Title
from onefde.modules.business import models as business
from onefde.modules.business import operations
from onefde.modules.business import schemas as bs
from onefde.modules.engagements.queries import require_engagement
from onefde.modules.engagements.schemas import Engagement
from onefde.modules.fde.agent_work import (
    customer_head,
    live_grant,
    reject,
    scoped_case,
    watermark,
)
from onefde.modules.tasks import models, queries
from onefde.modules.tasks import schemas as ts
from onefde.modules.tasks import service as tasks
from onefde.modules.tasks.assembly import register_source, start_assembled


class Empty(Input):
    pass


class Messages(Input):
    after: int = Field(default=0, ge=0)


class ConversationWindow(Input):
    before: int | None = Field(default=None, gt=0)


class Search(Input):
    query: str = Field(max_length=160)


class Asset(Input):
    asset_id: str = Field(min_length=1, max_length=128)


class Consult(Input):
    asset_ids: list[str] = Field(min_length=1, max_length=3)
    question: Nonblank = Field(max_length=500)


class Clarify(Input):
    source_message_id: int = Field(gt=0)
    expected_last_public_message_id: int = Field(gt=0)
    understanding: Nonblank = Field(max_length=500)
    question: Nonblank = Field(max_length=500)


class Send(Input):
    expected_last_public_message_id: int = Field(gt=0)


class Plan(Input):
    title: Title
    objective: Nonblank = Field(max_length=1500)
    scope: Nonblank = Field(max_length=1500)
    confirmed_rules: list[Nonblank] = Field(max_length=20)
    completion_criteria: list[Nonblank] = Field(min_length=1, max_length=12)
    source_message_ids: list[int] = Field(max_length=15)
    capability_versions: list[str] = Field(max_length=5)


class Versioned(Input):
    expected_revision: ts.Revision


class Record(Versioned):
    message_id: int = Field(gt=0)
    reply_to_input_id: UUID | None = None


class Adopt(Versioned):
    apply_ids: list[UUID] = Field(min_length=1, max_length=20)
    reason: Nonblank = Field(max_length=500)
    plan: Plan


class RunRef(Input):
    run_id: UUID


class Review(Versioned, RunRef):
    artifact_id: UUID
    verdict: Literal["accept", "request_changes", "needs_human_check"]
    reason: Nonblank = Field(max_length=1800)
    next_step: Nonblank = Field(max_length=500)


TOOLS = {
    "read_project": (
        Empty,
        "Read the current project, handoff, objective and allowed actions.",
    ),
    "read_conversation": (
        ConversationWindow,
        "Read the latest original messages and current public version. Use the returned before cursor for older messages.",
    ),
    "search_knowledge": (Search, "Search permitted Knowledge capability metadata."),
    "get_knowledge": (
        Asset,
        "Read an allowed asset and its fixed version and conditions.",
    ),
    "consult_knowledge": (
        Consult,
        "Request bounded Knowledge comparison of up to three permitted assets.",
    ),
    "draft_clarification": (
        Clarify,
        "Save an internal draft citing a current customer message.",
    ),
    "send_clarification": (Send, "Send the saved draft only under a live demo grant."),
    "create_task": (
        Plan,
        "Save the delivery plan as an internal Task draft, once per work.",
    ),
    "read_task": (
        Messages,
        "Read the linked Task, latest Run and input ledger. after is an input sequence.",
    ),
    "record_customer_input": (
        Record,
        "Save the current original customer reply as pending. Link an engineering question when answering it.",
    ),
    "adopt_inputs": (
        Adopt,
        "Adopt pending evidence and save the resulting full plan at the observed Task revision.",
    ),
    "delegate_engineering": (
        Versioned,
        "Start or continue Engineering using the trusted baseline, checks and model profile, only under a live grant.",
    ),
    "read_run": (RunRef, "Read the current linked Run and fixed submission evidence."),
    "suggest_review": (
        Review,
        "Record an advisory review citing a current fixed artifact and verification; requires separate human decision.",
    ),
}


def source_message(db, case, identifier):
    row = db.get(business.Message, identifier)
    if not case or not row or row.case_id != case.id or row.kind != "customer":
        raise ApiException(403, "FDE_SOURCE_DENIED", "只能引用当前会话的客户原话")
    return row


def customer_source(case, message):
    return f"[business:{case.id}/messages/{message.id}]\n{message.text}"


def current_task(task, revision=None):
    if not task:
        reject("FDE_TASK_REQUIRED", "请先保存或关联 Task")
    if revision is not None and task.revision != revision:
        reject("FDE_TASK_STALE", "Task 规格或输入已有更新")
    return task


def plan_spec(db, work, case, plan, knowledge):
    sources = [
        customer_source(case, source_message(db, case, i))
        for i in plan.source_message_ids
    ]
    for reference in plan.capability_versions:
        asset_id, separator, version = reference.partition("@")
        if (
            not separator
            or knowledge("get_asset", {"asset_id": asset_id})["asset"]["version"]
            != version
        ):
            reject("FDE_ASSET_STALE", "能力引用须为可见的当前固定版本")
    spec = ts.TaskSpec(
        **plan.model_dump(exclude={"source_message_ids"}),
        inputs=[f"[fde-work:{work.id}] {work.goal}", *sources],
        dependencies=[],
    )
    if any(check["kind"] == "automatic" for check in derive_checks(spec.model_dump())):
        reject("FDE_CHECK_UNTRUSTED", "自动执行的命令仅来自登记的工程检查")
    return spec


def inputs(db, task, after=0):
    return queries.sequence_page(db, models.TaskInput, ts.TaskInput, task.id, after, 20)


def read_run(db, task, run_id):
    current_task(task)
    if task.latest_run_id != run_id:
        raise ApiException(403, "FDE_RUN_SCOPE", "只能读取当前关联 Task 的最近运行")
    run = queries.require_run(db, run_id)
    evidence = queries.run_review_evidence(db, run.id)
    checks = run.snapshot.get("engineering", {}).get("checks", [])
    return {
        "run": ts.Run.model_validate(run).model_dump(mode="json"),
        "registered_checks": checks,
        "evidence": evidence.model_dump(mode="json") if evidence else None,
    }


def draft(db, work, case, data):
    source_message(db, case, data.source_message_id)
    if (
        case.state != "handling"
        or case.owner != "fde"
        or customer_head(db, case) != data.source_message_id
        or operations.latest_public_message(db, case)
        != data.expected_last_public_message_id
    ):
        reject("FDE_MESSAGE_STALE", "只能根据当前客户原话和会话版本起草澄清")
    result = operations.clarification_draft(
        db,
        case,
        bs.ClarificationRequest(
            source_message_id=data.source_message_id,
            understanding=data.understanding,
            question=data.question,
            kind="clarify",
        ),
        case.handler,
    ).model_dump(mode="json")
    work.report = work.report | {"clarification": result}
    return result


def send(db, work, case, grant, data):
    if (
        not grant
        or not case
        or case.handler != AGENT_ACTOR
        or grant.sent >= grant.policy["max_clarifications"]
    ):
        raise ApiException(
            403, "FDE_SEND_DENIED", "需由会话负责人发送，或登记有效模拟授权"
        )
    draft = work.report.get("clarification") or {}
    latest = operations.latest_public_message(db, case)
    head = customer_head(db, case)
    if (
        latest != data.expected_last_public_message_id
        or latest != draft.get("last_public_message_id")
        or head != draft.get("source_message_id")
    ):
        reject("FDE_MESSAGE_STALE", "旧草稿不能发送")
    previous = db.get(business.Message, latest)
    if (
        previous.kind == "reply"
        and (previous.reference or {}).get("draft_from_message_id") == head
    ):
        reject("FDE_ALREADY_SENT", "该客户消息已有澄清，请等待回答")
    operations.handle(
        db,
        case,
        bs.SendClarification(
            action="send_clarification",
            text=draft["public_reply"],
            source_message_id=head,
            expected_last_public_message_id=latest,
        ),
        AGENT_ACTOR,
    )
    grant.sent += 1
    message_id = operations.latest_public_message(db, case)
    work.report = work.report | {
        "clarification": draft | {"sent_message_id": message_id}
    }
    return {
        "message_id": message_id,
        "case_id": str(case.id),
        "source_message_id": head,
    }


def record(db, task, case, data):
    current_task(task, data.expected_revision)
    message = source_message(db, case, data.message_id)
    if (
        case.state != "handling"
        or case.owner != "fde"
        or message.id != customer_head(db, case)
    ):
        reject("FDE_MESSAGE_STALE", "只能登记当前客户补答")
    source = customer_source(case, message)
    prior = db.scalar(input_query(task.id, source, data.reply_to_input_id))
    if prior:
        return {"input": ts.TaskInput.model_validate(prior).model_dump(mode="json")}
    if data.reply_to_input_id:
        question = db.get(models.TaskInput, data.reply_to_input_id)
        if (
            not question
            or question.task_id != task.id
            or question.origin_run_id != task.latest_run_id
        ):
            reject("FDE_QUESTION_SCOPE", "回答须引用当前 Run 的原 Task 问题")
    return tasks.append_input(
        db,
        task.id,
        ts.TaskInputCreate(
            expected_revision=data.expected_revision,
            text=source,
            evidence_artifact_ids=[],
            **(
                {"kind": "answer", "reply_to_input_id": data.reply_to_input_id}
                if data.reply_to_input_id
                else {"kind": "change_request"}
            ),
        ),
        AGENT_ACTOR,
    ).model_dump(mode="json")


def input_query(task_id, source, reply_id):
    item = models.TaskInput
    return (
        select(item)
        .where(
            item.task_id == task_id,
            item.text == source,
            item.reply_to_input_id == reply_id,
        )
        .limit(1)
    )


def delegate(db, work, task, case, grant, data, store):
    if not grant or len(grant.runs) >= grant.policy["max_runs"]:
        raise ApiException(
            403, "FDE_DISPATCH_DENIED", "工程派发需现有负责人授权或有效模拟配额"
        )
    current_task(task, data.expected_revision)
    pending = (work.report or {}).get("pending_dispatch") or {}
    if (
        pending.get("status") == "pending"
        and pending.get("spec_version") == task.spec_version
    ):
        reject("FDE_ALREADY_DELEGATED", "该 Task 规格已经派发")
    if task.latest_run_id and any(
        r["spec_version"] == task.spec_version for r in grant.runs
    ):
        reject("FDE_ALREADY_DELEGATED", "该 Task 规格已经派发")
    head = customer_head(db, case) if case else None
    if head:
        source = customer_source(case, source_message(db, case, head))
        applied = db.scalar(
            select(models.TaskInput.id)
            .where(
                models.TaskInput.task_id == task.id,
                models.TaskInput.text == source,
                models.TaskInput.status == "applied",
            )
            .limit(1)
        )
        if not applied:
            reject("FDE_INPUT_NOT_ADOPTED", "派发前须采用当前客户补答")
    policy = grant.policy
    spec = ts.TaskSpec.model_validate(task.spec)
    criteria = [
        c["criterion"] for c in derive_checks(task.spec) if c["kind"] != "automatic"
    ] + ["[check] " + command for command in policy["checks"]]
    if spec.completion_criteria != criteria:
        if task.state == "waiting_input" or task.latest_run_id:
            reject("FDE_CHECKS_CHANGED", "续办规格缺少登记的固定检查")
        spec.completion_criteria = criteria
        tasks.update_spec(
            db,
            task.id,
            ts.TaskSpecUpdate(expected_revision=task.revision, spec=spec),
            AGENT_ACTOR,
        )
    task = db.get(models.Task, task.id)
    source = register_source(
        db,
        task,
        store,
        expected_sha256=policy["source_sha256"],
        allowed_paths=policy["allowed_paths"],
        review_paths=policy["review_paths"],
        archive=store.path(policy["source"]["object_key"]),
    )
    if task.state == "waiting_input":
        command = "continue"
        expected_run_id = str(task.latest_run_id)
    else:
        if task.state != "draft" or task.latest_run_id:
            reject("FDE_DISPATCH_STATE", "该任务需要负责人决定是否重新执行")
        command = "start"
        expected_run_id = None
    pending = {
        "status": "pending",
        "command": command,
        "task_id": str(task.id),
        "expected_revision": task.revision,
        "spec_version": task.spec_version,
        "model_profile_revision_id": str(grant.profile_id),
        "expected_run_id": expected_run_id,
        "initial_source": source,
        "impact": (
            f"在任务 {task.id} 的规格 {task.spec_version} 上"
            f"{'继续' if command == 'continue' else '启动'}工程运行。"
        ),
    }
    work.report = (work.report or {}) | {"pending_dispatch": pending}
    return {
        "pending_dispatch": pending,
        "task": ts.Task.model_validate(task).model_dump(mode="json"),
    }


def confirm_dispatch(db, work):
    pending = (work.report or {}).get("pending_dispatch") or {}
    if pending.get("status") != "pending":
        reject("FDE_DISPATCH_ABSENT", "没有待确认的工程派发")
    case = scoped_case(db, work) if work.case_id else None
    grant = live_grant(db, work, case)
    if not grant or len(grant.runs) >= grant.policy["max_runs"]:
        reject("FDE_DISPATCH_DENIED", "工程派发需现有负责人授权或有效模拟配额")
    task = db.get(models.Task, work.task_id, with_for_update=True)
    if (
        task is None
        or str(task.id) != pending["task_id"]
        or task.engagement_id != work.engagement_id
        or task.revision != pending["expected_revision"]
        or task.spec_version != pending["spec_version"]
    ):
        reject("FDE_TASK_STALE", "任务已变化，请重新准备派发")
    source = pending["initial_source"]
    if pending["command"] == "continue":
        accepted = tasks.action(
            db,
            task.id,
            ts.TaskAction(
                command="continue",
                expected_revision=task.revision,
                expected_run_id=pending["expected_run_id"],
                model_profile_revision_id=pending["model_profile_revision_id"],
            ),
            AGENT_ACTOR,
            initial_source=source,
        )
    else:
        accepted = start_assembled(
            db,
            task.id,
            expected_revision=task.revision,
            profile_id=grant.profile_id,
            actor=AGENT_ACTOR,
            initial_source=source,
        )
    result = accepted.model_dump(mode="json")
    grant.runs = [
        *grant.runs,
        {
            "run_id": result["run"]["id"],
            "spec_version": pending["spec_version"],
            "public": operations.latest_public_message(db, case) if case else None,
        },
    ]
    work.report = (work.report or {}) | {
        "pending_dispatch": pending
        | {
            "status": "confirmed",
            "run_id": result["run"]["id"],
            "operation_id": result["operation_id"],
        }
    }
    task = db.get(models.Task, task.id)
    point = watermark(db, work, case, task)
    if work.completed == work.observed:
        work.observed = point
        work.completed = point
    return result


def decline_dispatch(db, work):
    pending = (work.report or {}).get("pending_dispatch") or {}
    if pending.get("status") != "pending":
        reject("FDE_DISPATCH_ABSENT", "没有待确认的工程派发")
    work.report = (work.report or {}) | {
        "pending_dispatch": pending | {"status": "declined"}
    }
    return {"status": "declined"}


def suggest(db, work, task, data):
    current_task(task)
    task = db.scalar(
        select(models.Task)
        .where(models.Task.id == task.id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    current_task(task, data.expected_revision)
    result = read_run(db, task, data.run_id)
    evidence = result["evidence"]
    if (
        task.state != "review"
        or result["run"]["task_spec_version"] != task.spec_version
        or not evidence
        or evidence["artifact_id"] != str(data.artifact_id)
    ):
        reject("FDE_REVIEW_STALE", "评审建议必须引用当前规格和固定产物")
    registered = {
        c["command"] for c in result["registered_checks"] if c["kind"] == "automatic"
    }
    passed = {
        c["command"]
        for c in evidence["validation_checks"]
        if c["exit_code"] == 0 and not c["timeout"]
    }
    if data.verdict == "accept" and (
        evidence["validation_passed"] is not True
        or not registered
        or not registered <= passed
        or task.pending_input_count
    ):
        reject("FDE_VERIFICATION_REQUIRED", "建议接受前须有独立通过证据且无待采用输入")
    advice = data.model_dump(mode="json") | {
        "task_id": str(task.id),
        "spec_version": task.spec_version,
        "artifact_sha256": evidence["artifact_sha256"],
        "validation_checks": evidence["validation_checks"],
        "validation_passed": evidence["validation_passed"],
    }
    work.report = work.report | {"review_suggestion": advice}
    return advice


def execute(db, work, case, task, tool, data, knowledge, store):
    grant = live_grant(db, work, case)
    if tool == "read_project":
        return {
            "project": Engagement.model_validate(
                require_engagement(db, work.engagement_id)
            ).model_dump(mode="json"),
            "goal": work.goal,
            "case_id": str(case.id) if case else None,
            "handoff": case.handoff if case else None,
            "task_id": str(task.id) if task else None,
            "automation": {
                "may_send": bool(
                    grant
                    and case
                    and case.handler == AGENT_ACTOR
                    and grant.sent < grant.policy["max_clarifications"]
                ),
                "may_delegate": bool(
                    grant and len(grant.runs) < grant.policy["max_runs"]
                ),
            },
        }
    if tool == "read_conversation":
        if not case:
            return {"messages": [], "last_public_message_id": None}
        query = select(business.Message).where(
            business.Message.case_id == case.id,
            business.Message.kind.in_(("customer", "reply")),
        )
        if data.before is not None:
            query = query.where(business.Message.id < data.before)
        rows = list(db.scalars(query.order_by(business.Message.id.desc()).limit(7)))
        page = rows[:6]
        return {
            "messages": [
                bs.PublicMessage.model_validate(row).model_dump(mode="json")
                for row in reversed(page)
            ],
            "before": page[-1].id if len(rows) > len(page) else None,
            "last_public_message_id": operations.latest_public_message(db, case),
            "latest_customer_message_id": customer_head(db, case),
        }
    if tool == "search_knowledge":
        return knowledge("search_assets", data.model_dump())
    if tool == "get_knowledge":
        return knowledge("get_asset", data.model_dump())
    if tool == "consult_knowledge":
        return knowledge("consult", data.model_dump())
    if tool == "draft_clarification":
        return draft(db, work, case, data)
    if tool == "send_clarification":
        return send(db, work, case, grant, data)
    if tool == "create_task":
        if task:
            return {
                "task": ts.Task.model_validate(task).model_dump(mode="json"),
                "already_exists": True,
            }
        if case and (case.state != "handling" or case.owner != "fde"):
            reject("FDE_CASE_SCOPE", "该会话已转给其他负责人")
        spec = plan_spec(db, work, case, data, knowledge)
        created = tasks.create_task(
            db,
            work.engagement_id,
            ts.TaskCreate(
                request_id=work.id,
                task_key="delivery",
                original_request=work.goal,
                spec=spec,
                owner_role="fde",
                executor_role="engineering",
            ),
            AGENT_ACTOR,
        )
        work.task_id = created.id
        if case:
            case.task_id = created.id
        return {"task": created.model_dump(mode="json")}
    if tool == "read_task":
        if not task:
            return {"task": None}
        page = inputs(db, task, data.after)
        return {
            "task": ts.Task.model_validate(task).model_dump(mode="json"),
            **page,
            "items": [item.model_dump(mode="json") for item in page["items"]],
        }
    if tool == "record_customer_input":
        return record(db, task, case, data)
    if tool == "adopt_inputs":
        current_task(task, data.expected_revision)
        if case and (case.state != "handling" or case.owner != "fde"):
            reject("FDE_CASE_SCOPE", "该会话已转给其他负责人")
        if task.state not in ("draft", "waiting_input"):
            reject("FDE_ADOPT_STATE", "当前 Task 需由负责人决定如何处理补充")
        spec = plan_spec(db, work, case, data.plan, knowledge)
        if grant:
            spec.completion_criteria += [
                "[check] " + command for command in grant.policy["checks"]
            ]
        return tasks.apply_inputs(
            db,
            task.id,
            ts.TaskInputsApply(
                expected_revision=data.expected_revision,
                apply_ids=data.apply_ids,
                reject_ids=[],
                reason=data.reason,
                spec=spec,
            ),
            AGENT_ACTOR,
        ).model_dump(mode="json")
    if tool == "delegate_engineering":
        return delegate(db, work, task, case, grant, data, store)
    if tool == "read_run":
        return read_run(db, task, data.run_id)
    if tool == "suggest_review":
        return suggest(db, work, task, data)
    raise ApiException(403, "FDE_TOOL_DENIED", "工具不在模型白名单内")
