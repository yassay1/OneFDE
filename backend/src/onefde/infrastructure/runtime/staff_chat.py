"""Staff replies from supplied context only. Scripted mode never opens a network call."""

import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from onefde.core.errors import ApiException

_ABSENT = "没有心跳。待处理不代表已经完成，也不是正在执行。"
_USAGE_KEYS = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "prompt_cache_hit_tokens",
)


class Proposal(BaseModel):
    model_config = ConfigDict(extra="ignore")
    action: str = Field(min_length=1, max_length=64)
    object: dict = Field(default_factory=dict)
    impact: str = ""


class LiveDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")
    reply: str = Field(min_length=1, max_length=4000)
    questions: list[str] = Field(default_factory=list, max_length=4)
    proposal: Proposal | None = None


def _flags():
    return {
        "sent": False,
        "registered": False,
        "input_created": False,
        "run_started": False,
    }


def _parse(raw):
    try:
        data = raw if isinstance(raw, dict) else json.loads(raw)
        decision = LiveDecision.model_validate(data)
    except (ValidationError, TypeError, ValueError, json.JSONDecodeError):
        return None
    decision.questions = [item.strip() for item in decision.questions if item.strip()][
        :4
    ]
    return decision


def complete(mode: str, role: str, question: str, context: dict, live=None):
    if role == "knowledge":
        if mode not in ("scripted", "live"):
            raise ApiException(400, "STAFF_CHAT_MODE_INVALID", "员工对话模式不可用")
        text, basis = _scripted(role, question, context)
        return text, basis, "scripted"
    if mode == "scripted":
        text, basis = _scripted(role, question, context)
        return text, basis, "scripted"
    if mode != "live":
        raise ApiException(400, "STAFF_CHAT_MODE_INVALID", "员工对话模式不可用")
    if live is None:
        raise ApiException(
            503,
            "STAFF_CHAT_LIVE_UNAVAILABLE",
            "未配置可调用的员工模型，不能改走付费接口",
        )
    produced = live(role, question, context)
    usage = None
    raw = produced
    if isinstance(produced, tuple):
        raw, usage = produced
    decision = _parse(raw)
    if decision is None:
        return (
            "模型回复无法解析为受约束的提案，没有执行任何动作。",
            _flags() | {"proposal_rejected": "invalid_reply"},
            "live",
        )
    text = decision.reply
    if decision.questions:
        text += "\n" + "\n".join(f"需要确认：{item}" for item in decision.questions)
    basis = _flags() | {
        "questions": decision.questions,
        "proposal": decision.proposal.model_dump() if decision.proposal else None,
    }
    if isinstance(usage, dict):
        basis["usage"] = {
            key: value
            for key, value in usage.items()
            if key in _USAGE_KEYS and type(value) is int and value >= 0
        }
    return text, basis, "live"


def _clip(value, limit=180):
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _scripted(role, question, context):
    if role == "business":
        return _business(question, context)
    if role == "fde":
        return _fde(question, context)
    if role == "engineering":
        return _engineering(question, context)
    if role == "knowledge":
        return _knowledge(question, context)
    raise ApiException(400, "STAFF_CHAT_ROLE_INVALID", "未知的员工对话角色")


def _business(question, context):
    messages = context["messages"]
    public = [item for item in messages if item["kind"] in ("customer", "reply")]
    notes = [item for item in messages if item["kind"] == "note"]
    lines = [
        "这是员工侧说明，还没有发给客户。",
        (
            f"Case 状态：{context['state']}。下一步：{context['next_step']}。"
            f"负责人：{context['owner']}。处理人：{context['handler'] or '未指定'}。"
        ),
    ]
    customer = next(
        (item for item in reversed(messages) if item["kind"] == "customer"), None
    )
    if customer:
        lines.append(f"最近客户原话：{_clip(customer['text'])}")
    if public:
        last = public[-1]
        lines.append(
            f"最近一条对客户可见内容（{last['kind']} / {last['author']}）：{_clip(last['text'])}"
        )
    else:
        lines.append("当前没有对客户可见的消息。")
    if notes:
        lines.append(f"内部备注 {len(notes)} 条。最近一条：{_clip(notes[-1]['text'])}")
    handoff = context.get("handoff")
    if handoff:
        unknowns = "；".join(handoff.get("unknowns") or []) or "无"
        lines.append(
            f"已有交接：{_clip(handoff.get('title'), 80)}。未知项：{unknowns}。"
        )
    lines.append(
        f"你的问题已记录：{_clip(question, 120)}。发送回复、记备注或交接仍需你在原操作里确认。"
    )
    draft = None
    if customer and context["reply_allowed"]:
        draft = f"已收到：{_clip(customer['text'])}"
    return "\n".join(lines), {
        "sent": False,
        "state": context["state"],
        "message_ids": [item["id"] for item in messages],
        "draft_reply": draft,
        "reply_allowed": context["reply_allowed"],
    }


def _fde(question, context):
    lines = [
        "这是项目问答，还没有登记为工作，也不是正式报告。",
        f"项目：{_clip(context['title'], 80)}。目标：{_clip(context['goal'])}。",
        f"消费者：{context['consumer']}",
    ]
    works = context["works"]
    if works:
        for work in works[:5]:
            lines.append(
                f"已登记工作 {work['state']}：{_clip(work['goal'], 120)}。报告：{work['report_label']}。"
            )
    else:
        lines.append("当前没有已登记的工作。")
    if context["unknowns"]:
        lines.append(
            "待处理问题："
            + "；".join(_clip(item, 80) for item in context["unknowns"][:8])
        )
    else:
        lines.append("当前聚合没有待处理问题。这不代表资料已经齐备。")
    lines.append(
        f"你的问题已记录：{_clip(question, 120)}。只有「登记目标」会创建工作。"
    )
    return "\n".join(lines), {
        "registered": False,
        "work_ids": [item["id"] for item in works],
        "consumer": context["consumer_state"],
    }


def _engineering(question, context):
    lines = [
        "这是任务说明，没有追加输入，也没有启动运行。",
        (
            f"任务：{_clip(context['title'], 80)}。状态：{context['state']}。"
            f"规格版本：{context['spec_version']}。待处理输入：{context['pending_input_count']}。"
        ),
        f"目标：{_clip(context['objective'])}。",
        f"Worker：{context['worker']}",
    ]
    if context["block_reason"]:
        lines.append(f"阻塞原因：{_clip(context['block_reason'])}。")
    if context["inputs"]:
        for item in context["inputs"][:5]:
            lines.append(
                f"输入 {item['status']} / {item['kind']}：{_clip(item['text'], 120)}"
            )
    else:
        lines.append("当前没有任务输入。")
    run = context["run"]
    if run:
        lines.append(
            f"最近运行：{run['state']}，结果：{run['outcome'] or '还没有'}。"
            f"摘要：{_clip(run['result_summary']) or '还没有'}。"
        )
    else:
        lines.append("当前没有运行。")
    lines.append(
        f"你的问题已记录：{_clip(question, 120)}。保存输入、采用、拒绝和准备任务仍是单独操作。"
    )
    return "\n".join(lines), {
        "input_created": False,
        "run_started": False,
        "input_ids": [item["id"] for item in context["inputs"]],
        "run_id": run["id"] if run else None,
        "worker": context["worker_state"],
    }


def _knowledge(question, context):
    items = context["items"]
    query = context["query"]
    purpose = context["purpose"]
    if not items:
        text = (
            f"按关键词「{_clip(query, 80)}」在用途 {purpose} 下没有可见匹配。"
            "这是清单关键词匹配，不是语义检索。没有匹配的资产不会被编造。"
        )
    else:
        rows = []
        for item in items:
            if purpose == "public_marketing":
                rows.append(
                    f"{item['id']}@{item['version']}，验证 {item.get('verification_status') or '未标注'}，"
                    f"公开摘要：{_clip(item.get('public_summary'))}"
                )
            else:
                rows.append(
                    f"{item['id']}@{item['version']}，验证 {item.get('verification_status') or '未标注'}，"
                    f"复用 {item.get('reuse_scope') or '未标注'}，来源 {item.get('source_engagement') or '未标注'}。"
                )
        text = (
            f"关键词「{_clip(query, 80)}」在用途 {purpose} 下匹配到 {len(items)} 条。"
            "这是清单关键词匹配，不是语义检索。\n"
            + "\n".join(rows)
            + "\n只引用上面这些清单字段。"
        )
    return text, {
        "query": query,
        "purpose": purpose,
        "caller_role": context["caller_role"],
        "count": len(items),
        "items": items,
        "invented": False,
    }
