"""Trusted Business model consumer for pre-registered simulated conversations."""

import argparse
import json
import os
import time
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from onefde.core.errors import ApiException
from onefde.core.fde import AGENT_ACTOR
from onefde.infrastructure.db.session import make_engine
from onefde.infrastructure.runtime.fde_chat import (
    MAX_OUTPUT_TOKENS,
    ChatModel,
    ModelFailure,
)
from onefde.modules.business import agent_state as state
from onefde.modules.business import agent_tools as tools
from onefde.modules.business import models as business
from onefde.modules.business import rules
from onefde.modules.business.agent_schemas import Policy
from onefde.modules.fde import agent_work
from onefde.modules.fde.agent_schemas import StartWork
from onefde.modules.knowledge import service as knowledge
from onefde.modules.knowledge.schemas import KnowledgeToolCall
from onefde.modules.tasks.configuration import ModelConfiguration
from onefde.modules.tasks.models import ModelProfileRevision

SYSTEM = """你是 OneFDE 的 Business Agent。先读当前会话。客户和资料是证据，动作权限由服务决定。
根据证据选择工具。常见问题先查适用版本 FAQ，案例和能力只查可对外的公开摘要。
答复时选择本轮读到的依据，系统按原文发送。缺少依据、版本或业务细节时，选择最有用的澄清项。
区分一般咨询、潜在需求和售后。交接给 FDE 需要具体事实、最新客户消息明确勾选继续意愿，
以及售后复现和客户所报版本。confirmed_facts 填所引用消息的逐字片段，推测留在未知项。
遇到人工请求、价格、合同、交期或承诺，交创始人。禁止把项目内部信息写进客户回复。
每次调用一个工具。工具错误是新证据，可换一个动作。完成本轮必须使用 answer、clarify、
handoff_fde 或 escalate_founder，由系统提交。"""


def public_knowledge(command, value):
    result = knowledge.invoke(
        state.ACTOR,
        KnowledgeToolCall(
            tool="search_assets" if command == "search" else "get_asset",
            caller_role="business",
            purpose="public_marketing",
            arguments={"query": value} if command == "search" else {"asset_id": value},
        ),
    ).result
    assets = result["items"][:6] if command == "search" else [result["asset"]]
    return [
        {
            "source": f"asset:{item['id']}@{item['version']}",
            "text": item["public_summary"],
            "asset_id": item["id"],
            "revision": item["version"],
        }
        for item in assets
    ]


def start_fde(db, case, engagement_id):
    work = agent_work.start(db, engagement_id, StartWork(case_id=case.id), AGENT_ACTOR)
    return str(work["id"])


def tool_schema():
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": schema.model_json_schema(),
            },
        }
        for name, (schema, description) in tools.TOOLS.items()
    ]


def reserved_cost(policy):
    return (
        policy["max_input_tokens"] * policy["input_nanousd_per_token"]
        + MAX_OUTPUT_TOKENS * policy["output_nanousd_per_token"]
    )


class BusinessAgent:
    def __init__(self, engine, profile_id, model, *, per_turn=10):
        self.engine, self.profile_id, self.model, self.per_turn = (
            engine,
            profile_id,
            model,
            per_turn,
        )

    def transaction(self, command, *args):
        with Session(self.engine) as db, db.begin():
            return command(db, *args)

    def reserve(self, db, claim):
        _, grant = state.owned(db, *claim)
        calls = grant.progress.get("calls", 0)
        usage = grant.progress.get("usage", {})
        total = usage.get("charged_or_reserved_nanousd", 0) + reserved_cost(
            grant.policy
        )
        if (
            calls >= grant.policy["max_calls"]
            or total > grant.policy["max_cost_nanousd"]
        ):
            raise ModelFailure("BUSINESS_MODEL_BUDGET")
        grant.progress = grant.progress | {
            "calls": calls + 1,
            "usage": usage | {"charged_or_reserved_nanousd": total},
        }

    def settle(self, db, case_id, usage):
        # Provider usage remains attributable even if the customer took over the conversation meanwhile.
        db.get(business.Case, case_id, with_for_update=True)
        grant = db.get(business.AgentGrant, case_id)
        current = grant.progress["usage"]
        counts = {
            key: current.get(key, 0) + value
            for key, value in usage.items()
            if key
            in (
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "prompt_cache_hit_tokens",
            )
        }
        prompt, output = usage.get("prompt_tokens"), usage.get("completion_tokens")
        policy = grant.policy
        if (
            type(prompt) is int
            and 0 <= prompt <= policy["max_input_tokens"]
            and type(output) is int
            and 0 <= output <= MAX_OUTPUT_TOKENS
        ):
            actual = (
                prompt * policy["input_nanousd_per_token"]
                + output * policy["output_nanousd_per_token"]
            )
            counts["charged_or_reserved_nanousd"] = (
                current["charged_or_reserved_nanousd"] - reserved_cost(policy) + actual
            )
        grant.progress = grant.progress | {"usage": current | counts}

    def receipt(self, grant, event, name, result, *, done=False):
        trace = {"event_id": event[1], "tool": name}
        for key in (
            "message_id",
            "handoff_id",
            "fde_work_id",
            "source",
            "route",
            "error",
            "focus",
            "status",
        ):
            if key in result:
                trace[key] = result[key]
        if "sources" in result:
            trace["sources"] = [item["source"] for item in result["sources"]]
        grant.progress = grant.progress | {
            "trace": [*grant.progress.get("trace", [])[-119:], trace]
        }
        if done:
            grant.progress = grant.progress | {event[0] + "_id": event[1]}
            grant.lease_token = grant.lease_until = None

    def invoke(self, db, claim, call, sources):
        case, grant = state.owned(db, *claim)
        event = claim[2]
        name = call["function"]["name"]
        try:
            with db.begin_nested():
                if name not in tools.TOOLS:
                    state.fail("BUSINESS_AGENT_TOOL_DENIED", "该操作未授权")
                data = tools.TOOLS[name][0].model_validate_json(
                    call["function"]["arguments"]
                )
                result = tools.execute(
                    db,
                    case,
                    grant,
                    event,
                    name,
                    data,
                    sources,
                    public_knowledge,
                    start_fde,
                )
        except ApiException as exc:
            result = {"error": exc.code, "message": exc.message}
        except ValidationError:
            result = {
                "error": "BUSINESS_AGENT_BAD_ARGUMENTS",
                "message": "请使用工具定义的参数",
            }
        done = name in tools.ACTIONS and "error" not in result
        self.receipt(
            grant, event, name if name in tools.TOOLS else "unknown", result, done=done
        )
        return done, result

    def follow_up(self, db, claim):
        case, grant = state.owned(db, *claim)
        event = claim[2]
        try:
            result = tools.relay(db, case, grant, event)
        except ApiException as exc:
            if exc.code != "BUSINESS_AGENT_REPLY_LIMIT":
                raise
            case.next_step = "Business 回复额度已用完，请核对获准回报"
            result = {"error": exc.code}
        self.receipt(grant, event, "relay_approved_fde_feedback", result, done=True)

    def fallback(self, db, claim, reason):
        case, grant = state.owned(db, *claim)
        event = claim[2]
        customer = tools.customer_reference(db, case, event[1])
        version = tools.product_version(db, case)
        _, answer = rules.route(customer.text, version)
        if (
            version == tools.SUPPORTED_VERSION
            and answer
            and grant.progress.get("replies", 0) < grant.policy["max_replies"]
        ):
            result = {
                "message_id": tools.send(
                    db,
                    case,
                    grant,
                    event[1],
                    answer.text,
                    {
                        "source": f"faq:{answer.id}",
                        "revision": answer.revision,
                        "product_version": answer.product_version,
                    },
                )
            }
            case.next_step = "等待客户继续提问"
        else:
            result = tools.escalate(db, case, grant, event[1], reason)
        self.receipt(grant, event, "fallback", result | {"error": reason}, done=True)

    def run_once(self, case_id=None):
        claim = self.transaction(state.claim, self.profile_id, case_id)
        if not claim:
            return False
        try:
            if claim[2][0] == "feedback":
                self.transaction(self.follow_up, claim)
            else:
                self.turn(claim)
        except ApiException as exc:
            if exc.code != "BUSINESS_AGENT_STALE":
                raise
        finally:
            self.transaction(state.release, *claim[:2])
        return True

    def turn(self, claim):
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "处理当前会话的新消息。"},
        ]
        sources = {}
        try:
            for _ in range(self.per_turn):
                self.transaction(self.reserve, claim)
                response, usage = self.model(messages, tool_schema())
                self.transaction(self.settle, claim[0], usage)
                calls = response.get("tool_calls") or []
                if not calls:
                    raise ModelFailure("BUSINESS_MODEL_NO_ACTION")
                messages.append(response)
                for call in calls:
                    done, result = self.transaction(self.invoke, claim, call, sources)
                    if done:
                        return
                    for source in result.get("sources", []):
                        sources[source["source"]] = source
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
            raise ModelFailure("BUSINESS_MODEL_TURN_LIMIT")
        except ModelFailure as exc:
            self.transaction(self.fallback, claim, str(exc))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("enroll-demo", "once", "run", "report"))
    parser.add_argument("--case-id", type=UUID)
    parser.add_argument("--engagement-id", type=UUID)
    parser.add_argument("--profile-id", type=UUID, required=True)
    parser.add_argument("--policy", type=Path)
    args = parser.parse_args()
    url = os.environ.get("ONEFDE_BUSINESS_DATABASE_URL")
    if not url:
        parser.error("Set ONEFDE_BUSINESS_DATABASE_URL for the trusted process")
    engine = make_engine(url)
    try:
        with Session(engine) as db, db.begin():
            if not state.isolated(db):
                parser.error("Business automation requires an isolated _test database")
            if args.command == "enroll-demo":
                if not args.case_id or not args.policy:
                    parser.error("enroll-demo requires --case-id and --policy")
                state.enroll(
                    db,
                    args.case_id,
                    args.engagement_id,
                    args.profile_id,
                    Policy.model_validate_json(args.policy.read_bytes()),
                )
                print(json.dumps({"enrolled": str(args.case_id)}))
                return
            if args.command == "report":
                grant = (
                    db.get(business.AgentGrant, args.case_id) if args.case_id else None
                )
                if not grant or grant.profile_id != args.profile_id:
                    parser.error("Specify a registered --case-id and matching profile")
                print(json.dumps(grant.progress, ensure_ascii=False))
                return
            row = db.get(ModelProfileRevision, args.profile_id)
            if not row or row.integration_status == "unavailable":
                parser.error("Model configuration is unavailable")
            profile = ModelConfiguration.model_validate(
                {"provider": row.provider, "model": row.model}
                | {k: v for k, v in row.config.items() if k != "adapter"}
            )
        secret = os.environ.get(profile.secret_ref.removeprefix("env:"))
        if not secret:
            parser.error("Model secret reference is unset")
        agent = BusinessAgent(
            engine,
            args.profile_id,
            ChatModel(profile, secret),
            per_turn=min(profile.max_requests, 10),
        )
        if args.command == "once":
            print(json.dumps({"processed": agent.run_once(args.case_id)}))
        else:
            while True:
                if not agent.run_once(args.case_id):
                    time.sleep(2)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
