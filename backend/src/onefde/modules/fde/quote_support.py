"""Rules-only, explicitly enrolled quote CSV support.

Business messages and Task/Run state are durable inputs. Each polling pass
locks the case and commits one transition with its receipt.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from onefde.core.clock import now
from onefde.core.errors import ApiException
from onefde.core.fde import QUOTE_SUPPORT_ACTOR as ACTOR
from onefde.modules.business import models as business
from onefde.modules.business import operations
from onefde.modules.business import schemas as bs
from onefde.modules.business import service as cases
from onefde.modules.engagements.queries import require_engagement
from onefde.modules.fde.support_models import QuoteSupport
from onefde.modules.tasks import models as m
from onefde.modules.tasks import queries
from onefde.modules.tasks import schemas as ts
from onefde.modules.tasks import service as tasks

VERSION = "demo-supplier-quotes@1.1.0"
FIXTURE = "S01-unit-price-space"
QUESTION = "请确认使用的是 S01-unit-price-space 样例。"
ANSWER = "确认使用 S01-unit-price-space"
TERMINAL = ("closed", "manual")
CHECK = "[check] node products/demo-supplier-quotes/check.mjs --support-regression"


def enroll(db, case_id, engagement_id, profile_id, expires_at, source, *, max_runs):
    row = cases.case_for(db, case_id, lock=True)
    project = require_engagement(db, engagement_id)
    profile = db.get(m.ModelProfileRevision, profile_id)
    if (
        not project.is_demo
        or row.source != "quote_page"
        or row.state not in ("open", "clarifying")
        or row.handoff
        or row.engagement_id
        or not profile
        or profile.integration_status == "unavailable"
        or expires_at <= now()
        or not 1 <= max_runs <= 3
        or db.get(QuoteSupport, row.id)
    ):
        cases.conflict("仅可为尚未交接的模拟报价会话登记有效授权")
    db.add(
        QuoteSupport(
            case_id=row.id,
            engagement_id=engagement_id,
            profile_id=profile_id,
            expires_at=expires_at,
            stage="intake",
            source=source,
            progress={"max_runs": max_runs},
        )
    )


def _step(grant, stage, **evidence):
    grant.stage = stage
    grant.progress = {**grant.progress, **evidence}
    return True


def _manual(db, row, grant, reason):
    if grant.stage == "running" and row.task_id:
        task = queries.require_task(db, row.task_id)
        if task.active_run_id and str(task.active_run_id) == grant.progress.get(
            "run_id"
        ):
            run = queries.require_run(db, task.active_run_id)
            if run.state in ("queued", "running"):
                tasks.action(
                    db,
                    task.id,
                    ts.TaskAction(
                        command="stop_for_update",
                        expected_revision=task.revision,
                        expected_run_id=run.id,
                    ),
                    ACTOR,
                )
    if row.owner != "founder":
        cases.move(row, "founder_queue", "founder", reason)
    cases.add_message(db, row, "note", ACTOR, reason, reference=grant.progress)
    return _step(grant, "manual", reason=reason)


def register_verified_preview(db, case_id, artifact_id, url, checked_until):
    """Called by the trusted preview verifier after checking served bytes."""
    row = cases.case_for(db, case_id, lock=True)
    grant = db.get(QuoteSupport, row.id)
    release = (
        queries.accepted_artifact(db, row.task_id, artifact_id) if row.task_id else None
    )
    if not _preview_allowed(row, grant) or not release:
        cases.conflict("当前售后须有已接受的固定修复产物")
    return _step(
        grant,
        "review",
        preview={
            **release,
            "artifact_id": str(artifact_id),
            "url": url,
            "checked_until": checked_until.isoformat(),
        },
    )


def _preview_allowed(row, grant):
    return (
        grant
        and grant.stage == "review"
        and grant.expires_at > now()
        and _scope(row, grant)
    )


def preview_artifact(db, case_id, artifact_id):
    row = cases.case_for(db, case_id)
    grant = db.get(QuoteSupport, row.id)
    if not _preview_allowed(row, grant) or not queries.accepted_artifact(
        db, row.task_id, artifact_id
    ):
        cases.conflict("当前售后须有已接受的固定修复产物")
    return db.get(m.Artifact, artifact_id)


def _notify(db, row, grant):
    preview = grant.progress.get("preview")
    if not preview or datetime.fromisoformat(preview["checked_until"]) <= now():
        if row.next_step != "等待获准测试入口及访问核验":
            row.next_step = "等待获准测试入口及访问核验"
            return True
        return False
    artifact_id = UUID(preview["artifact_id"])
    release = queries.accepted_artifact(db, row.task_id, artifact_id)
    if not release or any(preview.get(key) != value for key, value in release.items()):
        return _manual(db, row, grant, "测试入口的版本与当前接受记录不一致")
    operations.notify(
        db,
        row,
        bs.NotifyRetest(
            action="notify_retest",
            artifact_id=artifact_id,
            version="quote-test-" + release["sha256"][:12],
            access_url=preview["url"],
            steps=f"导入 {FIXTURE}，确认 A=8、B=7.5 且仅 B 为组内最低。",
            access_evidence="受信验证器核对回环测试入口和固定产物内容",
        ),
        ACTOR,
    )
    return _step(grant, "notified", notice_id=row.retest["notice_id"], preview=None)


def _scope(row, grant):
    return (
        row.owner == "fde"
        and row.handler == ACTOR
        and row.engagement_id == grant.engagement_id
    )


def _spec(grant):
    return ts.TaskSpec(
        title="报价 CSV 表头空格兼容",
        objective="修复 S01 合成变体的 unit_price 尾随空格导入故障",
        scope="仅修改 products/demo-supplier-quotes/compare.js 的表头解析。",
        inputs=[
            f"固定基线 SHA256 {grant.source['sha256']}",
            f"复现样例 {FIXTURE}，保留所有样例和既有检查文件。",
            f"如需客户确认复现样例，使用这一固定业务问题：{QUESTION}",
        ],
        confirmed_rules=[
            "仅容忍 unit_price 表头边缘 ASCII 空格，缺列和归一后重名均须明确报错。保留 R01–R05 与原价格值。"
        ],
        completion_criteria=[CHECK, "A=8、B=7.5，仅 B 为组内最低。"],
        dependencies=[],
        capability_versions=[],
    )


def _execution(db, row, grant, task, command):
    if not _scope(row, grant) or task.engagement_id != grant.engagement_id:
        return _manual(db, row, grant, "售后授权与当前 Task 归属不一致")
    if task.spec != _spec(grant).model_dump(mode="json"):
        return _manual(db, row, grant, "当前规格超出售后模板，需创始人核查")
    if grant.progress.get("runs", 0) >= grant.progress["max_runs"]:
        return _manual(db, row, grant, "售后运行次数已达上限")
    try:
        with db.begin_nested():
            result = tasks.action(
                db,
                task.id,
                ts.TaskAction(
                    command=command,
                    expected_revision=task.revision,
                    expected_run_id=task.latest_run_id
                    if command == "continue"
                    else None,
                    model_profile_revision_id=grant.profile_id
                    if command != "queue"
                    else None,
                ),
                ACTOR,
                initial_source=grant.source,
            )
    except ApiException as error:
        if error.code == "ACTIVE_RUN_EXISTS":
            if db.scalar(select(m.Run.id).where(m.Run.state == "interrupted").limit(1)):
                return _manual(db, row, grant, "旧工程运行现场不明，核查后再派发")
            return False
        return _manual(db, row, grant, f"执行命令受阻：{error.code}")
    if result.run is None:
        return _step(grant, "queued", revision=result.task.revision)
    return _step(
        grant,
        "running",
        run_id=str(result.run.id),
        operation_id=str(result.operation_id),
        runs=int(grant.progress.get("runs", 0)) + 1,
    )


def _accept(db, row, grant):
    if row.state != "fde_queue":
        return False
    reproduction = row.handoff.get("reproduction") if row.handoff else None
    failed = row.retest and row.retest.get("passed") is False
    if failed:
        feedback = db.get(business.Message, row.retest["result_message_id"])
        reproduction = feedback.text
    if (
        row.workflow != "support"
        or not reproduction
        or "缺少 unit_price" not in reproduction
        or (row.engagement_id and row.engagement_id != grant.engagement_id)
    ):
        return _manual(db, row, grant, "交接不匹配已授权的报价复现样例")
    messages = cases.customer_messages(db, row)
    projects = {
        (message.reference or {}).get("project_hint") for message in messages
    } - {None}
    if projects - {str(grant.engagement_id), "demo-supplier-quotes"}:
        return _manual(db, row, grant, "客户报告的项目与售后登记不一致")
    hints = {(message.reference or {}).get("version_hint") for message in messages} - {
        None
    }
    if hints - {VERSION, "1.1", "1.1.0", "v1.1", "v1.1.0"}:
        return _manual(db, row, grant, "客户报告的产品版本需核实")
    if FIXTURE not in reproduction:
        if failed:
            return _manual(db, row, grant, "复测仍失败，需核对复现样例和实际测试版本")
        prompt_id = grant.progress.get("intake_prompt_id")
        if not prompt_id:
            prompt = cases.reply(db, row, QUESTION + " 请回复「" + ANSWER + "」。")
            row.next_step = "等待客户确认报价复现样例"
            return _step(grant, "intake", intake_prompt_id=prompt.id)
        replies = [message for message in messages if message.id > prompt_id]
        if not replies:
            return False
        if len(replies) != 1 or replies[0].text.strip() != ANSWER:
            return _manual(db, row, grant, "无法确认客户使用已授权的复现样例")
        grant.progress = {**grant.progress, "intake_answer_id": replies[0].id}
    if row.task_id and queries.require_task(db, row.task_id).state != "succeeded":
        return _manual(db, row, grant, "前一修复 Task 尚未关闭，需核对续办范围")
    if failed:
        artifact_id = UUID(row.retest["artifact_id"])
        accepted = queries.accepted_artifact(db, row.task_id, artifact_id)
        artifact = db.get(m.Artifact, artifact_id)
        if not accepted or artifact.kind != "source-snapshot":
            return _manual(db, row, grant, "续办需核对上次接受的固定源码")
        grant.source = {
            **grant.source,
            "object_key": artifact.object_key,
            "sha256": artifact.sha256,
            "size_bytes": artifact.size_bytes,
        }
    operations.accept(
        db,
        row,
        bs.AcceptHandoff(
            action="accept_handoff",
            engagement_id=grant.engagement_id,
            reported_version=VERSION,
            spec=_spec(grant),
        ),
        ACTOR,
    )
    return _step(
        grant,
        "accepted",
        task_id=str(row.task_id),
        handoff_id=row.handoff["id"],
        previous_notice_id=row.retest["notice_id"] if failed else None,
        feedback_message_id=row.retest["result_message_id"] if failed else None,
    )


def _result(db, row, grant, task):
    run = queries.require_run(db, task.latest_run_id)
    if str(run.id) != grant.progress.get("run_id"):
        return _manual(db, row, grant, "当前运行已由人工或其他操作替换")
    if run.state in ("queued", "running", "cancel_requested"):
        return False
    if run.state != "completed" or not run.finished_at:
        return _manual(db, row, grant, f"工程运行需核查：{run.error_code or run.state}")
    if task.state in ("review", "succeeded") and run.outcome == "submitted":
        artifacts = list(
            db.scalars(select(m.Artifact).where(m.Artifact.run_id == run.id))
        )
        if not artifacts:
            return _manual(db, row, grant, "工程提交缺固定产物")
        job = db.scalar(select(m.DispatchJob).where(m.DispatchJob.run_id == run.id))
        evidence = {
            "task_id": str(task.id),
            "run_id": str(run.id),
            "spec_version": run.task_spec_version,
            "artifacts": [{"id": str(a.id), "sha256": a.sha256} for a in artifacts],
            "check_result": (job.result_payload or {}).get("proof", {}),
        }
        row.next_step = (
            "创始人验收本轮固定提交"
            if task.state == "review"
            else "等待获准测试入口及访问核验"
        )
        cases.add_message(db, row, "note", ACTOR, row.next_step, reference=evidence)
        return _step(grant, "review", review=evidence)
    if task.state == "waiting_input" and run.outcome == "needs_input":
        question = db.scalar(
            select(m.TaskInput).where(
                m.TaskInput.origin_run_id == run.id, m.TaskInput.kind == "question"
            )
        )
        if not question or question.text != QUESTION or task.pending_input_count != 1:
            return _manual(db, row, grant, "工程问题超出可自动追问范围")
        reply = cases.reply(db, row, QUESTION + " 请回复「" + ANSWER + "」。")
        row.next_step = "等待客户在原会话确认复现样例"
        return _step(
            grant, "waiting_answer", question_id=str(question.id), prompt_id=reply.id
        )
    return _manual(db, row, grant, "工程结果与当前任务状态需核查")


def _answer(db, row, grant, task):
    question_id = UUID(grant.progress["question_id"])
    question = db.get(m.TaskInput, question_id)
    if (
        not question
        or question.task_id != task.id
        or question.status != "pending"
        or task.state != "waiting_input"
    ):
        return _manual(db, row, grant, "原问题已经变化，需核对客户答复")
    messages = [
        item
        for item in cases.customer_messages(db, row)
        if item.id > grant.progress["prompt_id"]
    ]
    if not messages:
        return False
    message = messages[0]
    item = tasks.append_input(
        db,
        task.id,
        ts.TaskInputCreate(
            expected_revision=task.revision,
            kind="answer",
            reply_to_input_id=question_id,
            text=f"[business:{row.id}/messages/{message.id}] {message.text}",
            evidence_artifact_ids=[],
        ),
        ACTOR,
    )
    if len(messages) != 1 or message.text.strip() != ANSWER:
        return _manual(db, row, grant, "已登记待采用答案，请核实是否解决原问题")
    return _step(
        grant,
        "answer_saved",
        input_id=str(item.input.id),
        revision=item.task.revision,
        answer_message_id=message.id,
    )


def advance(db, case_id):
    row = cases.case_for(db, case_id, lock=True)
    grant = db.get(QuoteSupport, case_id)
    if not grant or grant.stage in TERMINAL:
        return False
    if row.state == "closed":
        return _step(grant, "closed")
    if grant.stage == "notified" and row.state == "awaiting_retest":
        return False
    if row.owner == "founder" or grant.expires_at <= now():
        return _manual(db, row, grant, "创始人接管或售后授权已到期")
    if grant.stage == "intake" or (
        grant.stage == "notified" and row.state == "fde_queue"
    ):
        return _accept(db, row, grant)
    if grant.stage == "notified":
        return False
    if not _scope(row, grant) or str(row.task_id) != grant.progress["task_id"]:
        return _manual(db, row, grant, "售后关联已变更，需创始人核查")
    task = queries.require_task(db, row.task_id)
    if (
        grant.stage == "accepted"
        and task.state == "draft"
        and task.latest_run_id is None
    ):
        return _execution(db, row, grant, task, "queue")
    if (
        grant.stage == "queued"
        and task.state == "queued"
        and task.revision == grant.progress["revision"]
    ):
        return _execution(db, row, grant, task, "start")
    if grant.stage == "running":
        return _result(db, row, grant, task)
    if grant.stage == "waiting_answer":
        return _answer(db, row, grant, task)
    if grant.stage == "answer_saved" and task.revision == grant.progress["revision"]:
        if any(
            item.id > grant.progress["answer_message_id"]
            for item in cases.customer_messages(db, row)
        ):
            return _manual(db, row, grant, "采用前收到新补充，请核对待采用答案")
        applied = tasks.apply_inputs(
            db,
            task.id,
            ts.TaskInputsApply(
                expected_revision=task.revision,
                apply_ids=[UUID(grant.progress["input_id"])],
                reject_ids=[],
                reason="客户在原会话确认使用获准的固定复现样例",
            ),
            ACTOR,
        )
        return _step(grant, "continue", revision=applied.revision)
    if grant.stage == "continue" and task.revision == grant.progress["revision"]:
        return _execution(db, row, grant, task, "continue")
    if grant.stage == "review" and task.state in ("review", "succeeded"):
        return _notify(db, row, grant) if task.state == "succeeded" else False
    return _manual(db, row, grant, "任务或规格状态变化，需创始人核查")


def pending_cases(db):
    return list(
        db.scalars(
            select(QuoteSupport.case_id).where(QuoteSupport.stage.not_in(TERMINAL))
        )
    )


def claim_allowed(db, run):
    if run.snapshot.get("actor") != ACTOR:
        return True
    row = db.scalar(
        select(business.Case)
        .join(QuoteSupport, QuoteSupport.case_id == business.Case.id)
        .where(
            business.Case.task_id == run.task_id,
            QuoteSupport.progress["run_id"].astext == str(run.id),
        )
        .with_for_update(of=business.Case, skip_locked=True)
    )
    grant = db.get(QuoteSupport, row.id) if row else None
    return bool(
        grant
        and _scope(row, grant)
        and grant.stage == "running"
        and grant.progress.get("run_id") == str(run.id)
        and grant.expires_at > now()
    )
