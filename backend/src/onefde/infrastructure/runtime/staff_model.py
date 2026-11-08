"""Optional live staff replies. Absent configuration never opens a model call."""

import json
import os

from onefde.core.errors import ApiException
from onefde.infrastructure.runtime.fde_chat import ChatModel, ModelFailure
from onefde.modules.tasks.configuration import ModelConfiguration
from onefde.modules.tasks.models import ModelProfileRevision

_SYSTEM = (
    "你是 OneFDE 的员工助手。只返回一个 JSON 对象，不要使用 Markdown。"
    "字段为 reply、questions 和 proposal。proposal 为 null，或只含 action、object、impact。"
    "object 中的标识必须来自给定上下文，不能替换成其他 Case、项目或 Task。"
    "不要声称动作已经执行。允许的 action 只有 handoff_case、register_work、"
    "append_answer、send_reply、commit_scope、start_run、continue_run、retry_run、"
    "accept_review、request_changes、apply_inputs、record_knowledge_feedback。"
)
_TOOL = {
    "type": "function",
    "function": {
        "name": "propose",
        "description": "给出员工说明和至多一个当前锚点上的提案。",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "reply": {"type": "string"},
                "questions": {"type": "array", "items": {"type": "string"}},
                "proposal": {"type": ["object", "null"]},
            },
            "required": ["reply"],
        },
    },
}


def resolve(db, revision_id):
    if revision_id is None:
        raise ApiException(
            503,
            "STAFF_CHAT_LIVE_UNAVAILABLE",
            "未配置可调用的员工模型，不能改走付费接口",
        )
    row = db.get(ModelProfileRevision, revision_id)
    if row is None or row.integration_status == "unavailable":
        raise ApiException(
            503,
            "STAFF_CHAT_LIVE_UNAVAILABLE",
            "未配置可调用的员工模型，不能改走付费接口",
        )
    profile = ModelConfiguration.model_validate(
        {"provider": row.provider, "model": row.model}
        | {key: value for key, value in row.config.items() if key != "adapter"}
    )
    secret = os.environ.get(profile.secret_ref.removeprefix("env:"))
    if not secret:
        raise ApiException(
            503,
            "STAFF_CHAT_LIVE_UNAVAILABLE",
            "未配置可调用的员工模型，不能改走付费接口",
        )
    model = ChatModel(profile, secret)

    def live(role, question, context):
        payload = json.dumps(
            {"role": role, "question": question, "context": context},
            ensure_ascii=False,
            default=str,
        )
        if len(payload) > 24_000:
            payload = payload[:24_000]
        try:
            message, usage = model(
                [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": payload},
                ],
                [_TOOL],
            )
        except ModelFailure:
            raise ApiException(
                503,
                "STAFF_CHAT_LIVE_UNAVAILABLE",
                "员工模型这次没有返回可用回复",
            ) from None
        calls = message.get("tool_calls") or []
        if calls:
            raw = calls[0]["function"]["arguments"]
        else:
            raw = message.get("content") or ""
        return raw, usage

    return live
