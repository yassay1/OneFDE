"""Conversation commands share one transaction with their messages and Task changes."""

from secrets import compare_digest
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from onefde.core.errors import ApiException
from onefde.core.fde import AGENT_ACTOR, QUOTE_SUPPORT_ACTOR
from onefde.core.security import digest
from onefde.modules.business import agent_state, rules
from onefde.modules.business import models as m
from onefde.modules.business import schemas as s


def conflict(message):
    raise ApiException(409, "BUSINESS_STATE_CONFLICT", message)


def case_for(db, case_id, *, token=None, lock=False):
    query = select(m.Case).where(m.Case.id == case_id)
    row = db.scalar(query.with_for_update() if lock else query)
    if not row or (
        token is not None and not compare_digest(row.token_digest, digest(token))
    ):
        raise ApiException(404, "BUSINESS_CASE_NOT_FOUND", "会话不存在或凭证无效")
    return row


def add_message(db, row, kind, author, text, *, reference=None, data=None):
    message = m.Message(
        case_id=row.id,
        kind=kind,
        author=author,
        text=text,
        reference=reference,
        request_id=data.request_id if data else None,
        request_hash=digest(data.model_dump_json()) if data else None,
    )
    db.add(message)
    db.flush()
    return message


def replayed(db, row, data):
    prior = db.scalar(
        select(m.Message).where(
            m.Message.case_id == row.id, m.Message.request_id == data.request_id
        )
    )
    if prior and prior.request_hash != digest(data.model_dump_json()):
        conflict("消息编号已用于其他内容")
    return prior is not None


def start(db, case_id, token, data):
    # An invitation is an attribution capability only. It grants no read access.
    invitation = db.get(m.Candidate, data.invitation_id) if data.invitation_id else None
    if data.invitation_id and (not invitation or not invitation.invited_at):
        raise ApiException(404, "BUSINESS_INVITATION_NOT_FOUND", "演示邀请不存在")
    db.execute(
        insert(m.Case)
        .values(
            id=case_id,
            token_digest=digest(token),
            source="invitation" if invitation else "quote_page",
            invitation_id=data.invitation_id,
            workflow="outreach" if invitation else "inquiry",
            owner="business",
            state="open",
            next_step="读取客户问题",
        )
        .on_conflict_do_nothing(index_elements=[m.Case.id])
    )
    row = case_for(db, case_id, token=token, lock=True)
    if not replayed(db, row, data):
        if db.scalar(select(m.Message.id).where(m.Message.case_id == row.id).limit(1)):
            conflict("会话已创建，请在原会话追加消息")
        receive(db, row, data)
    return row


def message_page(db, row, after, *, public):
    query = select(m.Message).where(m.Message.case_id == row.id, m.Message.id > after)
    if public:
        query = query.where(m.Message.kind.in_(("customer", "reply")))
    items = list(db.scalars(query.order_by(m.Message.id).limit(101)))
    page = items[:100]
    return page, page[-1].id if page else after, len(items) > len(page)


def public_view(db, row, after=0):
    items, last, more = message_page(db, row, after, public=True)
    pending_retest = (
        row.state == "awaiting_retest"
        and row.retest
        and "result_message_id" not in row.retest
    )
    return s.PublicConversation(
        id=row.id,
        state="awaiting_retest"
        if pending_retest
        else ("closed" if row.state == "closed" else "open"),
        retest_notice_id=row.retest["notice_id"] if pending_retest else None,
        messages=items,
        last_message_id=last,
        has_more=more,
    )


def detail(db, row, after=0):
    items, last, more = message_page(db, row, after, public=False)
    return s.CaseDetail(
        **s.CaseSummary.model_validate(row).model_dump(),
        engagement_id=row.engagement_id,
        reported_version=row.reported_version,
        task_id=row.task_id,
        invitation_id=row.invitation_id,
        handoff=row.handoff,
        retest=row.retest,
        messages=items,
        last_message_id=last,
        has_more=more,
    )


def move(row, state, owner, next_step, handler=None):
    row.state, row.owner, row.next_step, row.handler = state, owner, next_step, handler


def reply(db, row, text, reference=None):
    return add_message(db, row, "reply", "business", text, reference=reference)


def customer_messages(db, row):
    return list(
        db.scalars(
            select(m.Message)
            .where(m.Message.case_id == row.id, m.Message.kind == "customer")
            .order_by(m.Message.id)
        )
    )


def handoff(db, row, *, title, goal, facts, unknowns, reproduction, evidence=None):
    if row.handoff:
        if row.owner == "founder" and row.state == "handling":
            move(row, "fde_queue", "fde", "FDE 确认项目与后续 Task")
        return
    snapshot = s.Handoff(
        id=uuid4(),
        title=title,
        goal=goal,
        confirmed_facts=facts,
        unknowns=unknowns,
        sources=[
            f"business:{row.id}/messages/{item.id}"
            for item in customer_messages(db, row)
        ],
        product_version=row.reported_version,
        reproduction=reproduction,
        **(evidence or {}),
    )
    row.handoff = snapshot.model_dump(mode="json")
    move(row, "fde_queue", "fde", "FDE 确认项目、版本与后续 Task")


def receive(db, row, data):
    if replayed(db, row, data):
        return
    if row.state == "closed":
        conflict("会话已关闭，请发起新咨询")
    # Clarification type is recorded with the question so restarts preserve routing.
    previous = db.scalar(
        select(m.Message)
        .where(
            m.Message.case_id == row.id,
            m.Message.kind == "reply",
        )
        .order_by(m.Message.id.desc())
        .limit(1)
    )
    intake = (
        (previous.reference or {}).get("intake")
        if previous and row.state == "clarifying"
        else None
    )
    decision, answer = rules.route(
        data.text, data.version_hint or row.reported_version, intake=intake
    )
    hints = {
        "project_hint": data.project_hint,
        "version_hint": data.version_hint,
        "willing_to_continue": data.willing_to_continue,
    }
    message = add_message(
        db, row, "customer", "customer", data.text, reference=hints, data=data
    )
    if row.state == "handling":
        if row.handler in (QUOTE_SUPPORT_ACTOR, AGENT_ACTOR) and decision == "founder":
            move(row, "founder_queue", "founder", "创始人接手并在原会话回复")
            reply(db, row, "已转给负责人，请保留这个链接查看后续回复。")
            return
        row.next_step = "接手人查看最新客户消息"
        return
    if row.state == "founder_queue":
        return
    if decision == "founder":
        move(row, "founder_queue", "founder", "创始人接手并在原会话回复")
        reply(db, row, "已转给负责人，请保留这个链接查看后续回复。")
        return
    if row.state in ("fde_queue", "awaiting_retest"):
        return
    if agent_state.owns_intake(row) and agent_state.active(db, row):
        row.next_step = "Business Agent 查看最新客户消息"
        return
    if decision in ("support", "requirement"):
        support = decision == "support"
        if support:
            row.workflow = "support"
        concrete = len(data.text.strip()) >= 8 and rules.concrete(data.text, support)
        consent = support or row.invitation_id is None or data.willing_to_continue
        if intake == decision and concrete and consent:
            handoff(
                db,
                row,
                title="报价工具故障" if support else "报价工具需求",
                goal="核实客户报告并确定下一步"
                if support
                else "确认客户需求及交付范围",
                facts=[f"客户已补充说明，见消息 {message.id}。"],
                unknowns=["项目及产品版本待核实", "客户描述待 FDE 核验"],
                reproduction=data.text if support else None,
            )
            reply(db, row, "已将你的说明转给交付同事，会在这个会话继续跟进。")
            return
        if support:
            question = "请描述触发问题的操作和页面显示的报错，例如选择文件后点击「比较」时发生了什么？"
        elif row.invitation_id:
            question = (
                "请描述希望改进的具体操作，并在下方确认是否愿意由交付同事继续联系。"
            )
        else:
            question = "请描述你希望在哪个操作中实现什么结果？"
        move(row, "clarifying", "business", "等待客户补充操作和结果")
        reply(db, row, question, {"intake": decision})
        return
    if answer:
        move(row, "open", "business", "等待客户继续提问")
        reply(
            db,
            row,
            answer.text,
            {
                "faq_id": answer.id,
                "revision": answer.revision,
                "product_version": answer.product_version,
            },
        )
    else:
        move(row, "clarifying", "business", "等待客户补充问题")
        reply(db, row, "请说明你遇到问题的是哪个步骤，例如导入、比较或导出？")
