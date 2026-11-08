"""Founder and FDE actions over the Business work item."""

from urllib.parse import urlsplit

from sqlalchemy import select

from onefde.core.fde import AGENT_ACTOR, QUOTE_SUPPORT_ACTOR
from onefde.modules.business import agent_state, rules
from onefde.modules.business import models as m
from onefde.modules.business import schemas as s
from onefde.modules.business.service import (
    add_message,
    conflict,
    customer_messages,
    handoff,
    move,
    replayed,
    reply,
)
from onefde.modules.engagements.queries import require_engagement
from onefde.modules.tasks import queries as task_queries
from onefde.modules.tasks import schemas as ts
from onefde.modules.tasks import service as tasks


def latest_public_message(db, row):
    return db.scalar(
        select(m.Message.id)
        .where(m.Message.case_id == row.id, m.Message.kind.in_(("customer", "reply")))
        .order_by(m.Message.id.desc())
        .limit(1)
    )


def approve_fde_feedback(db, row, data, actor):
    if (
        row.owner != "fde"
        or row.state != "handling"
        or row.workflow == "support"
        or row.handler not in (actor, AGENT_ACTOR)
        or not agent_state.active(db, row)
        or latest_public_message(db, row) != data.expected_last_public_message_id
    ):
        conflict("仅可为当前模拟会话批准与原消息版本一致的 FDE 反馈")
    add_message(
        db,
        row,
        "note",
        f"fde:{actor}",
        data.text,
        reference={
            "type": "approved_fde_feedback",
            "fde_work_id": str(data.fde_work_id),
            "public_id": data.expected_last_public_message_id,
        },
    )
    row.next_step = "Business 在原会话跟进获准方案反馈"


def draft_source(db, row, message_id):
    source = db.get(m.Message, message_id)
    if not source or source.case_id != row.id or source.kind != "customer":
        conflict("澄清只能引用本会话的客户原话")
    return source


def clarification_draft(db, row, data, actor):
    if row.state != "handling" or row.owner != "fde" or row.handler != actor:
        conflict("请由接手本会话的 FDE 准备澄清")
    source = draft_source(db, row, data.source_message_id)
    if data.kind == "clarify":
        if not data.question:
            conflict("请填写一个会影响交付的待确认问题")
        question = f"想跟你确认一件事：{data.question}"
        next_step = "确认后，我会在这个会话告诉你下一步。"
    else:
        question = "时间、费用或范围需要负责人确认。"
        next_step = "确认结果会在这个会话告诉你。"
    return s.ClarificationDraft(
        source_message_id=source.id,
        last_public_message_id=latest_public_message(db, row),
        public_reply=f"我理解你的需求是：{data.understanding}\n{question}\n{next_step}",
        internal_summary=(
            f"来源 business:{row.id}/messages/{source.id}\n"
            f"接手人复述：{data.understanding}\n待确认：{data.question or question}"
        ),
    )


def handle(db, row, data, actor):
    if isinstance(data, s.HandoffCommand) and row.handoff and row.owner != "founder":
        return
    if row.state == "closed":
        conflict("会话已关闭")
    if isinstance(data, (s.StaffMessage, s.SendClarification)):
        kind = "reply" if isinstance(data, s.SendClarification) else data.action
        if kind == "reply" and (row.state != "handling" or row.handler != actor):
            conflict("请先接手再对外回复")
        reference = None
        if isinstance(data, s.SendClarification):
            if row.owner != "fde":
                conflict("仅接手本会话的 FDE 可以发送澄清草稿")
            source = draft_source(db, row, data.source_message_id)
            if data.expected_last_public_message_id != latest_public_message(db, row):
                conflict("会话已有更新，请刷新后重新预览草稿")
            reference = {"draft_from_message_id": source.id}
        add_message(db, row, kind, actor, data.text, reference=reference)
    elif isinstance(data, s.TakeOver):
        if row.state not in ("open", "clarifying", "founder_queue") and not (
            row.state == "handling"
            and row.handler in (QUOTE_SUPPORT_ACTOR, AGENT_ACTOR)
        ):
            conflict("仅未接手或待创始人接手的会话可接管")
        move(row, "handling", "founder", "创始人跟进客户", actor)
    elif isinstance(data, s.HandoffCommand):
        if row.state not in ("clarifying", "handling", "open", "fde_queue"):
            conflict("当前会话状态不能交接")
        if (
            row.invitation_id
            and row.workflow != "support"
            and not any(
                (message.reference or {}).get("willing_to_continue")
                and len(message.text.strip()) >= 8
                and rules.concrete(message.text, False)
                for message in customer_messages(db, row)
            )
        ):
            conflict("请先取得客户的具体需求和继续确认意愿")
        handoff(
            db,
            row,
            title=data.title,
            goal=data.goal,
            facts=data.confirmed_facts,
            unknowns=data.unknowns,
            reproduction=data.reproduction,
        )
    elif isinstance(data, s.AcceptHandoff):
        accept(db, row, data, actor)
    elif isinstance(data, s.RecordInput):
        record_input(db, row, data, actor)
    elif isinstance(data, s.NotifyRetest):
        notify(db, row, data, actor)


def accept(db, row, data, actor):
    if row.state != "fde_queue" or not row.handoff:
        conflict("请先将会话交给 FDE")
    if (data.spec is None) == (data.task_id is None):
        conflict("请选择关联 Task，或提交完整的新 Task 规格")
    if row.workflow == "support" and not (
        data.reported_version or row.reported_version
    ):
        conflict("售后需核实客户使用的产品版本")
    if row.engagement_id and row.engagement_id != data.engagement_id:
        conflict("已有项目归属，不能改绑其他项目")
    require_engagement(db, data.engagement_id)
    if data.task_id:
        task = task_queries.require_task(db, data.task_id)
        if task.engagement_id != data.engagement_id:
            conflict("Task 必须属于已核实的项目")
        if (
            row.task_id
            and task.id != row.task_id
            and task.related_task_id != row.task_id
        ):
            conflict("续办 Task 必须关联前一修复任务")
    else:
        task = tasks.create_task(
            db,
            data.engagement_id,
            ts.TaskCreate(
                request_id=row.id,
                task_key=f"business-{row.id}-{row.task_id or 'initial'}",
                original_request="\n".join(
                    f"[消息 {item.id}] {item.text}"
                    for item in customer_messages(db, row)
                ),
                spec=data.spec,
                owner_role="fde",
                executor_role="engineering",
                related_task_id=row.task_id,
            ),
            actor=f"fde:{actor}",
        )
    row.task_id = task.id
    bind_handoff(db, row, data.engagement_id, actor, data.reported_version)


def bind_handoff(db, row, engagement_id, actor, reported_version=None):
    """Accept a founder-approved handoff before the delivery task is known."""
    if row.state != "fde_queue" or row.owner != "fde" or not row.handoff:
        conflict("请先将会话交给 FDE")
    if row.engagement_id and row.engagement_id != engagement_id:
        conflict("已有项目归属，不能改绑其他项目")
    if row.workflow == "support" and not (reported_version or row.reported_version):
        conflict("售后需核实客户使用的产品版本")
    require_engagement(db, engagement_id)
    row.engagement_id = engagement_id
    row.reported_version = reported_version or row.reported_version
    move(row, "handling", "fde", "FDE 处理 Task 并保存证据", actor)
    add_message(
        db,
        row,
        "note",
        f"fde:{actor}",
        "FDE 已确认交接及项目关联。",
        reference={
            "handoff_id": row.handoff["id"],
            "engagement_id": str(row.engagement_id),
            "reported_version": row.reported_version,
            "task_id": str(row.task_id) if row.task_id else None,
        },
    )


def record_input(db, row, data, actor):
    if (
        row.owner != "fde"
        or row.state != "handling"
        or row.handler != actor
        or not row.task_id
    ):
        conflict("请由接手的 FDE 在本会话关联 Task 后记录输入")
    message = db.get(m.Message, data.message_id)
    if not message or message.case_id != row.id or message.kind != "customer":
        conflict("只能采用本会话客户消息作为待处理输入")
    marker = {"task_id": str(row.task_id), "message_id": message.id}
    source = f"[business:{row.id}/messages/{message.id}]\n{message.text}"
    if task_queries.has_input_text(db, row.task_id, source):
        return
    task = task_queries.require_task(db, row.task_id)
    recorded = tasks.append_input(
        db,
        row.task_id,
        ts.TaskInputCreate(
            expected_revision=task.revision,
            kind="change_request",
            text=source,
            evidence_artifact_ids=[],
        ),
        actor=f"fde:{actor}",
    )
    add_message(
        db,
        row,
        "note",
        f"fde:{actor}",
        "已登记待采用的 TaskInput。",
        reference=marker | {"task_input_id": str(recorded.input.id)},
    )


def notify(db, row, data, actor):
    if (
        row.workflow != "support"
        or row.state != "handling"
        or row.owner != "fde"
        or row.handler != actor
        or not row.task_id
        or not row.reported_version
    ):
        conflict("需由接手的 FDE 核实使用版本并关联修复 Task")
    url = urlsplit(data.access_url)
    if (
        url.scheme not in ("http", "https")
        or not url.hostname
        or url.username
        or any(char.isspace() for char in data.access_url)
    ):
        conflict("请填写已验证可访问的 HTTP(S) 修复地址")
    release = task_queries.accepted_artifact(db, row.task_id, data.artifact_id)
    if not release:
        conflict("固定产物必须来自本 Task 已接受的当前修复提交")
    if row.retest and row.retest.get("artifact_id") == str(data.artifact_id):
        conflict("上一次复试失败，请关联新的修复产物")
    snapshot = (
        data.model_dump(mode="json", exclude={"action"})
        | release
        | {"confirmed_by": actor}
    )
    notice = reply(
        db,
        row,
        f"请复试修复版本 {data.version}\n访问地址：{data.access_url}\n复试步骤：{data.steps}",
        {"release": snapshot},
    )
    row.retest = snapshot | {"notice_id": notice.id}
    move(row, "awaiting_retest", "business", "等待客户复试确认")


def retest_result(db, row, data):
    if replayed(db, row, data):
        return
    if (
        row.state != "awaiting_retest"
        or not row.retest
        or "result_message_id" in row.retest
        or data.notice_id != row.retest["notice_id"]
    ):
        conflict("请针对当前修复通知提交复试结果")
    message = add_message(
        db,
        row,
        "customer",
        "customer",
        data.text,
        data=data,
        reference={"notice_id": data.notice_id, "passed": data.passed},
    )
    row.retest = row.retest | {"result_message_id": message.id, "passed": data.passed}
    if data.passed:
        move(row, "closed", "business", "客户确认复试通过")
        reply(db, row, "已记录你确认可以使用。本次售后已关闭。")
    else:
        move(row, "fde_queue", "fde", "客户复试仍失败，FDE 在原会话关联后续修复 Task")
        reply(db, row, "已记录复试仍失败。交付同事会在这个会话继续跟进。")
