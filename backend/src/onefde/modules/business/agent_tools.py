"""Business dialogue commands. The model selects actions and references."""

from sqlalchemy import select

from onefde.modules.business import agent_schemas as s
from onefde.modules.business import agent_state as state
from onefde.modules.business import models as m
from onefde.modules.business import rules, service

TOOLS = {
    "read_conversation": (
        s.ConversationWindow,
        "Read public messages, consent and product version in this conversation. Use before for older messages.",
    ),
    "lookup_faq": (
        s.FaqLookup,
        "Read approved FAQ for this conversation's observed product version.",
    ),
    "search_public_knowledge": (
        s.Search,
        "Find public case or capability summaries permitted for customer use.",
    ),
    "answer": (
        s.Answer,
        "Send the exact approved content identified by a successful lookup in this turn.",
    ),
    "clarify": (
        s.Clarify,
        "Ask for selected missing details using approved question wording.",
    ),
    "handoff_fde": (
        s.Handoff,
        "Transfer a qualified opportunity or support issue with cited verbatim facts and current customer consent.",
    ),
    "escalate_founder": (
        s.Escalate,
        "Route to the founder for commercial or human decisions.",
    ),
}
ACTIONS = {"answer", "clarify", "handoff_fde", "escalate_founder"}

QUESTIONS = {
    "current_process": "你现在是怎么处理这件事的？",
    "desired_result": "你希望在哪个操作中看到什么结果？",
    "input_and_output": "现在使用什么资料，想得到什么结果或文件？",
    "version": "你用的是哪个产品版本？可以填写页面标注的版本。",
    "reproduction": "可以按顺序说一下触发问题的操作吗？",
    "observed_result": "页面实际显示了什么结果或提示？",
    "consent": "如果愿意由交付同事继续跟进，请勾选会话里的继续意愿选项。",
}
SUPPORTED_VERSION = "demo-supplier-quotes@1.1.0"
ALIASES = {"1.1", "1.1.0", "v1.1", "v1.1.0", SUPPORTED_VERSION}


def public_history(db, case, before):
    query = select(m.Message).where(
        m.Message.case_id == case.id,
        m.Message.kind.in_(("customer", "reply")),
    )
    if before is not None:
        query = query.where(m.Message.id < before)
    rows = db.scalars(query.order_by(m.Message.id.desc()).limit(9)).all()
    page = rows[:8]
    messages = [
        {
            "id": row.id,
            "kind": row.kind,
            "text": row.text,
            **(
                {
                    "willing_to_continue": bool(
                        (row.reference or {}).get("willing_to_continue")
                    ),
                    "version_hint": (row.reference or {}).get("version_hint"),
                    "project_hint": (row.reference or {}).get("project_hint"),
                }
                if row.kind == "customer"
                else {}
            ),
        }
        for row in reversed(page)
    ]
    return {
        "messages": messages,
        "before": page[-1].id if len(rows) > len(page) else None,
    }


def product_version(db, case):
    messages = service.customer_messages(db, case)
    for row in reversed(messages):
        hints = rules.VERSION.findall(row.text.casefold())
        hint = (row.reference or {}).get("version_hint")
        if hint:
            hints.append(hint.strip().casefold())
        versions = {SUPPORTED_VERSION if item in ALIASES else item for item in hints}
        if versions:
            return next(iter(versions)) if len(versions) == 1 else None
    return case.reported_version


def faq(db, case, topic):
    if product_version(db, case) != SUPPORTED_VERSION:
        return {"status": "version_missing_or_unmatched", "sources": []}
    items = [
        {
            "source": f"faq:{item.id}",
            "text": item.text,
            "revision": item.revision,
            "product_version": item.product_version,
        }
        for item in rules.FAQ
        if item.id == topic
    ]
    return {"sources": items}


def customer_reference(db, case, identifier):
    row = db.get(m.Message, identifier)
    if not row or row.case_id != case.id or row.kind != "customer":
        state.fail("BUSINESS_AGENT_SOURCE_DENIED", "证据须为本会话的客户原话")
    return row


def send(db, case, grant, event_id, text, reference=None):
    if grant.progress.get("replies", 0) >= grant.policy["max_replies"]:
        state.fail("BUSINESS_AGENT_REPLY_LIMIT", "模拟回复额度已用完")
    result = service.add_message(
        db,
        case,
        "reply",
        state.ACTOR,
        text,
        reference={
            "event_id": event_id,
            **(reference or {}),
        },
    )
    grant.progress = grant.progress | {"replies": grant.progress.get("replies", 0) + 1}
    return result.id


def escalate(db, case, grant, event_id, reason):
    service.move(case, "founder_queue", "founder", "创始人接手并在原会话回复")
    if grant.progress.get("replies", 0) >= grant.policy["max_replies"]:
        return {"route": "founder", "reason": reason}
    return {
        "route": "founder",
        "reason": reason,
        "message_id": send(
            db, case, grant, event_id, state.FOUNDER_TEXT, {"reason": reason}
        ),
    }


def transfer(db, case, grant, event_id, data, start_fde):
    latest = customer_reference(db, case, event_id)
    if not (latest.reference or {}).get("willing_to_continue"):
        state.fail("BUSINESS_AGENT_CONSENT_REQUIRED", "最新客户消息尚无继续意愿")
    facts = [
        customer_reference(db, case, identifier) for identifier in data.fact_message_ids
    ]
    if not any(len(row.text.strip()) >= 8 for row in facts):
        state.fail("BUSINESS_AGENT_FACTS_REQUIRED", "请引用具体客户说明")
    if any(not any(fact in row.text for row in facts) for fact in data.confirmed_facts):
        state.fail("BUSINESS_AGENT_FACTS_UNGROUNDED", "已确认事实请引用客户原话片段")
    reproduction = (
        customer_reference(db, case, data.reproduction_message_id)
        if data.reproduction_message_id
        else None
    )
    version = product_version(db, case)
    if data.kind == "support" and (not reproduction or not version):
        state.fail(
            "BUSINESS_AGENT_SUPPORT_DETAILS", "售后交接须有复现原话和客户所报版本"
        )
    if data.kind == "support":
        case.workflow = "support"
    case.reported_version = version
    service.handoff(
        db,
        case,
        title=data.title,
        goal=data.goal,
        facts=data.confirmed_facts,
        unknowns=data.unknowns,
        reproduction=reproduction.text if reproduction else None,
        evidence={
            "consent_message_id": latest.id,
            "fact_message_ids": sorted({row.id for row in facts}),
            "reproduction_message_id": reproduction.id if reproduction else None,
        },
    )
    work = start_fde(db, case, grant.engagement_id) if grant.engagement_id else None
    message_id = send(
        db,
        case,
        grant,
        event_id,
        "已将你的说明转给交付同事，会在这个会话继续跟进。",
        {"handoff_id": case.handoff["id"], "consent_message_id": latest.id},
    )
    return {
        "handoff_id": case.handoff["id"],
        "fde_work_id": work,
        "message_id": message_id,
    }


def execute(db, case, grant, event, name, data, sources, knowledge, start_fde):
    _, event_id, *_ = event
    if name == "read_conversation":
        return {
            **public_history(db, case, data.before),
            "product_version": product_version(db, case),
            "workflow": case.workflow,
            "latest_customer_message_id": event_id,
        }
    if name == "lookup_faq":
        return faq(db, case, data.topic)
    if name == "search_public_knowledge":
        return {"sources": knowledge("search", data.query)}
    if name == "answer":
        source = sources.get(data.source)
        if not source:
            state.fail("BUSINESS_AGENT_SOURCE_REQUIRED", "请先读取本轮获准对外的依据")
        if source["source"].startswith("faq:"):
            allowed = faq(db, case, source["source"].removeprefix("faq:"))["sources"]
        else:
            allowed = knowledge("get", source["asset_id"])
        if source not in allowed:
            state.fail("BUSINESS_AGENT_SOURCE_STALE", "依据已失效或不再获准")
        service.move(case, "open", "business", "等待客户继续提问")
        reference = {key: value for key, value in source.items() if key != "text"}
        return {
            "message_id": send(db, case, grant, event_id, source["text"], reference),
            **reference,
        }
    if name == "clarify":
        service.move(case, "clarifying", "business", "等待客户补充")
        focus = list(dict.fromkeys(data.focus))
        return {
            "message_id": send(
                db,
                case,
                grant,
                event_id,
                "\n".join(QUESTIONS[key] for key in focus),
                {"clarification_focus": focus},
            ),
            "focus": focus,
        }
    if name == "handoff_fde":
        return transfer(db, case, grant, event_id, data, start_fde)
    return escalate(db, case, grant, event_id, data.reason)


def relay(db, case, grant, event):
    note = db.get(m.Message, event[1])
    evidence = note.reference
    message_id = send(
        db,
        case,
        grant,
        note.id,
        note.text,
        {
            "approved_feedback_id": note.id,
            "fde_work_id": evidence["fde_work_id"],
        },
    )
    case.next_step = "已在原会话转达 FDE 反馈，等待后续"
    return {
        "message_id": message_id,
        "fde_work_id": evidence["fde_work_id"],
    }
