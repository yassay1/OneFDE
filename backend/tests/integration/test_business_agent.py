"""Real Case/FDE control with scripted model turns. No provider calls."""

import json
import os
from datetime import timedelta
from pathlib import Path
from secrets import token_hex
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from onefde.core.clock import now
from onefde.entrypoints.business_agent import BusinessAgent
from onefde.entrypoints.fde_agent import DeliveryAgent
from onefde.infrastructure.artifacts import PrivateArtifactStore
from onefde.infrastructure.runtime.fde_chat import ModelFailure
from onefde.modules.business import agent_state, models
from onefde.modules.business.agent_schemas import Policy
from onefde.modules.business.rules import FAQ
from onefde.modules.fde.agent_schemas import ModelBudget
from onefde.modules.tasks.models import Task
from tests.support.factories import create_engagement

CUSTOMER_PATH = "/api/v1/public/business/conversations"
STAFF_PATH = "/api/v1/business"
INITIAL = "店里供应商报价每天都很乱，希望处理得省事一点。"
CONFIRMED = "希望导入两家供应商的 CSV，按同规格比较每公斤单价，并导出对比结果。"
USAGE = {"prompt_tokens": 40, "completion_tokens": 8}


def register(app, profile, case, project=None):
    with Session(app.state.engine) as db, db.begin():
        agent_state.enroll(
            db,
            case,
            UUID(project) if project else None,
            UUID(profile),
            Policy(
                expires_at=now() + timedelta(minutes=10),
                max_calls=60,
                max_replies=10,
                max_cost_nanousd=100_000_000,
                max_input_tokens=1_048_576,
                input_nanousd_per_token=1,
                output_nanousd_per_token=2,
            ),
        )


def incoming(client, case, text, *, token=None, **fields):
    first = token is None
    token = token or {
        "Origin": "http://127.0.0.1:8765",
        "Authorization": f"Bearer {token_hex(32)}",
    }
    path = f"{CUSTOMER_PATH}/{case}" + ("" if first else "/messages")
    request = client.put if first else client.post
    payload = {"request_id": str(uuid4()), "text": text, **fields}
    response = request(path, headers=token, json=payload)
    assert response.status_code == 200, response.text
    assert request(path, headers=token, json=payload).json() == response.json()
    return token, response.json()["messages"][-1]["id"]


def staff(client, auth, case, action, status=200, **fields):
    response = client.post(
        f"{STAFF_PATH}/cases/{case}/actions",
        headers=auth | {"Idempotency-Key": str(uuid4())},
        json={"action": action, **fields},
    )
    assert response.status_code == status, response.text
    return response.json()


def detail(client, case):
    return client.get(f"{STAFF_PATH}/cases/{case}").json()


def call(name, **arguments):
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "type": "function",
                "id": str(uuid4()),
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                },
            }
        ],
    }, USAGE


def result(messages):
    return json.loads(messages[-1]["content"])


def scripted(engine, profile, *steps):
    iterator = iter(steps)
    return BusinessAgent(
        engine, UUID(profile), lambda messages, _: next(iterator)(messages)
    )


def handoff(messages, *, kind="requirement"):
    original = result(messages)["messages"][-1]
    return call(
        "handoff_fde",
        kind=kind,
        title="模拟供应商报价",
        goal="整理供应商报价的对比和导出"
        if kind == "requirement"
        else "核实 CSV 导入问题",
        fact_message_ids=[original["id"]],
        confirmed_facts=[original["text"]],
        unknowns=["确认业务规则和完成条件"],
        reproduction_message_id=original["id"] if kind == "support" else None,
    )


def test_simulated_invitation_business_to_fde_and_approved_feedback(
    client, auth, app, profile, tmp_path
):
    project = create_engagement(client, auth)["id"]
    candidate = client.post(
        f"{STAFF_PATH}/candidate-search",
        headers=auth,
        json={"adcode": "440106", "sample": True},
    ).json()["items"][0]["id"]
    assert (
        client.post(
            f"{STAFF_PATH}/candidates/{candidate}/invite", headers=auth, json={}
        ).status_code
        == 200
    )
    case = uuid4()
    register(app, profile, case, project)
    token, initial = incoming(client, case, INITIAL, invitation_id=candidate)
    assert detail(client, case)["messages"][-1]["kind"] == "customer"

    def verify_version(messages):
        assert result(messages)["messages"][-1]["id"] == initial
        return call("lookup_faq", topic="export")

    def choose_clarification(messages):
        assert result(messages)["status"] == "version_missing_or_unmatched"
        return call("clarify", focus=["input_and_output", "consent"])

    engine = app.state.engine
    first = scripted(
        engine,
        profile,
        lambda _: call("read_conversation"),
        verify_version,
        choose_clarification,
    )
    assert first.run_once(case)
    assert not first.run_once(case)
    clarification = detail(client, case)["messages"][-1]
    assert clarification["reference"]["event_id"] == initial
    assert detail(client, case)["state"] == "clarifying"

    _, consent = incoming(
        client,
        case,
        CONFIRMED,
        token=token,
        willing_to_continue=True,
        version_hint="1.1.0",
    )
    second = scripted(engine, profile, lambda _: call("read_conversation"), handoff)
    assert second.run_once(case) and not second.run_once(case)
    transferred = detail(client, case)
    snapshot = transferred["handoff"]
    assert transferred["handler"] == "service:fde:delivery"
    assert transferred["owner"] == "fde" and transferred["engagement_id"] == project
    assert transferred["task_id"] is None
    assert snapshot["consent_message_id"] == consent
    assert snapshot["product_version"] == "demo-supplier-quotes@1.1.0"
    assert snapshot["confirmed_facts"] == [CONFIRMED]
    assert snapshot["sources"] == [
        f"business:{case}/messages/{message}" for message in (initial, consent)
    ]
    work = client.get(f"/api/v1/engagements/{project}/fde/work").json()[0]
    assert work["case_id"] == str(case)

    fde_next = "先核实规格是否一致和导出范围，再形成工程规格。"

    def fde_model(messages, _):
        if len(messages) == 2:
            return call("read_project")
        if len(messages) == 4:
            assert result(messages)["handoff"]["id"] == snapshot["id"]
            return call("read_conversation")
        assert any(
            message["text"] == CONFIRMED for message in result(messages)["messages"]
        )
        return {"role": "assistant", "content": fde_next}, USAGE

    fde = DeliveryAgent(
        engine,
        PrivateArtifactStore(tmp_path),
        fde_model,
        max_calls=5,
        profile_id=UUID(profile),
        budget=ModelBudget(
            max_cost_nanousd=10_000_000,
            max_input_tokens=200_000,
            input_nanousd_per_token=1,
            output_nanousd_per_token=1,
        ),
    )
    assert fde.run_once(UUID(work["id"]))
    wrong = {"fde_work_id": work["id"], "text": fde_next}
    staff(
        client,
        auth,
        case,
        "approve_fde_feedback",
        status=409,
        expected_last_public_message_id=initial,
        **wrong,
    )
    approved = staff(
        client,
        auth,
        case,
        "approve_fde_feedback",
        **wrong,
        expected_last_public_message_id=transferred["messages"][-1]["id"],
    )
    note = approved["messages"][-1]
    assert note["kind"] == "note"
    assert second.run_once(case) and not second.run_once(case)
    public = client.get(f"{CUSTOMER_PATH}/{case}", headers=token).json()["messages"]
    assert public[-1]["text"] == fde_next and all(
        message["id"] != note["id"] for message in public
    )
    with Session(engine) as db:
        assert db.scalar(select(func.count(Task.id))) == 0
        progress = db.get(models.AgentGrant, case).progress
        assert progress["calls"] == 5 and progress["usage"]["prompt_tokens"] == 200
    if filename := os.getenv("ONEFDE_BUSINESS_CONTROL_EVIDENCE"):
        Path(filename).write_text(
            json.dumps(
                {
                    "scope": "isolated PostgreSQL scripted models",
                    "product": "demo-supplier-quotes",
                    "invitation_id": candidate,
                    "case_id": str(case),
                    "engagement_id": project,
                    "first_customer_message_id": initial,
                    "clarification_message_id": clarification["id"],
                    "consent_message_id": consent,
                    "handoff_id": snapshot["id"],
                    "fde_work_id": work["id"],
                    "fde_next_step": fde_next,
                    "approved_feedback_note_id": note["id"],
                    "business_followup_message_id": public[-1]["id"],
                    "business_trace": progress["trace"],
                    "business_scripted_calls": progress["calls"],
                    "provider_calls": 0,
                    "billable_tokens": 0,
                    "cost_usd": 0,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def test_faq_requires_applicable_version_and_exact_approved_content(
    client, auth, app, profile
):
    case = uuid4()
    register(app, profile, case)
    token, _ = incoming(client, case, "怎么导出比较结果？", version_hint="v2.0")
    engine = app.state.engine

    def missing(messages):
        assert not result(messages)["sources"]
        return call("clarify", focus=["version"])

    first = scripted(
        engine, profile, lambda _: call("lookup_faq", topic="export"), missing
    )
    assert first.run_once(case)
    _, corrected = incoming(
        client, case, "刚才写错了，实际是 v1.1，怎么导出？", token=token
    )

    def answer(messages):
        assert (
            result(messages)["sources"][0]["product_version"]
            == "demo-supplier-quotes@1.1.0"
        )
        return call("answer", source=result(messages)["sources"][0]["source"])

    second = scripted(
        engine, profile, lambda _: call("lookup_faq", topic="export"), answer
    )
    assert second.run_once(case) and not second.run_once(case)
    reply = detail(client, case)["messages"][-1]
    assert reply["text"] == next(item.text for item in FAQ if item.id == "export")
    assert reply["reference"] == {
        "event_id": corrected,
        "source": "faq:export",
        "product_version": "demo-supplier-quotes@1.1.0",
        "revision": "quote-faq@1",
    }


def test_scope_consent_and_commercial_guard(client, auth, app, profile):
    engine = app.state.engine
    other, case = uuid4(), uuid4()
    _, other_id = incoming(client, other, "其他会话的模拟客户原话。")
    register(app, profile, case)
    token, first = incoming(client, case, CONFIRMED)
    staff(client, auth, case, "note", text="仅内部信息 INTERNAL_ONLY")
    a = BusinessAgent(engine, UUID(profile), None)
    lease = a.transaction(agent_state.claim, UUID(profile), case)

    def invoke(name, **args):
        return a.transaction(
            a.invoke, lease, call(name, **args)[0]["tool_calls"][0], {}
        )[1]

    assert (
        invoke("read_conversation", case_id=str(other))["error"]
        == "BUSINESS_AGENT_BAD_ARGUMENTS"
    )
    conversation = invoke("read_conversation")
    assert "INTERNAL_ONLY" not in json.dumps(conversation)
    assert (
        invoke("search_public_knowledge", query="fixture-restricted-supplier-notes")[
            "sources"
        ]
        == []
    )
    visible = invoke("search_public_knowledge", query="fresh-quote-compare-csv")[
        "sources"
    ][0]
    assert set(visible) == {"source", "text", "asset_id", "revision"}
    assert (
        invoke("answer", source=visible["source"], text="保证明天交付，费用免费")[
            "error"
        ]
        == "BUSINESS_AGENT_BAD_ARGUMENTS"
    )
    assert (
        invoke("answer", source=visible["source"])["error"]
        == "BUSINESS_AGENT_SOURCE_REQUIRED"
    )
    transfer = {
        "kind": "requirement",
        "title": "模拟",
        "goal": "继续了解",
        "fact_message_ids": [first],
        "confirmed_facts": [CONFIRMED],
        "unknowns": [],
    }
    assert (
        invoke("handoff_fde", **transfer)["error"] == "BUSINESS_AGENT_CONSENT_REQUIRED"
    )
    a.transaction(agent_state.release, *lease[:2])
    _, consent = incoming(
        client, case, CONFIRMED, token=token, willing_to_continue=True
    )
    lease = a.transaction(agent_state.claim, UUID(profile), case)
    assert (
        invoke("handoff_fde", **(transfer | {"fact_message_ids": [other_id]}))["error"]
        == "BUSINESS_AGENT_SOURCE_DENIED"
    )
    assert (
        invoke("handoff_fde", **(transfer | {"confirmed_facts": ["编造已确认事实"]}))[
            "error"
        ]
        == "BUSINESS_AGENT_FACTS_UNGROUNDED"
    )
    assert invoke("escalate_founder", reason="commercial")["route"] == "founder"
    assert detail(client, case)["state"] == "founder_queue"
    assert detail(client, case)["messages"][-1]["reference"]["event_id"] == consent


def test_takeover_during_model_call_fences_reply(client, auth, app, profile):
    case = uuid4()
    register(app, profile, case)
    _, source = incoming(client, case, INITIAL)

    def takeover(_):
        staff(client, auth, case, "take_over")
        return call("clarify", focus=["input_and_output"])

    a = scripted(app.state.engine, profile, takeover)
    assert a.run_once(case) and not a.run_once(case)
    item = detail(client, case)
    assert item["owner"] == "founder" and item["handler"] == "founder"
    assert [message["id"] for message in item["messages"]] == [source]
    with Session(app.state.engine) as db:
        assert db.get(models.AgentGrant, case).progress["usage"]["prompt_tokens"] == 40


def test_new_customer_correction_during_model_call_discards_old_turn(
    client, auth, app, profile
):
    case = uuid4()
    register(app, profile, case)
    token, initial = incoming(client, case, "我用 v1.1，怎么导出？")

    def changed(_):
        incoming(client, case, "刚核对过，实际是 v2.0。", token=token)
        return call("clarify", focus=["consent"])

    engine = app.state.engine
    assert scripted(engine, profile, changed).run_once(case)
    messages = detail(client, case)["messages"]
    assert [item["kind"] for item in messages] == ["customer", "customer"]
    assert messages[0]["id"] == initial
    corrected = messages[1]["id"]

    def clarify(messages):
        assert result(messages)["status"] == "version_missing_or_unmatched"
        return call("clarify", focus=["version"])

    next_turn = scripted(
        engine, profile, lambda _: call("lookup_faq", topic="export"), clarify
    )
    assert next_turn.run_once(case) and not next_turn.run_once(case)
    reply = detail(client, case)["messages"][-1]
    assert reply["reference"]["event_id"] == corrected


def test_timeout_falls_back_once_after_restart_and_human_request_bypasses_model(
    client, auth, app, profile
):
    engine = app.state.engine
    case = uuid4()
    register(app, profile, case)
    incoming(client, case, INITIAL)

    def timeout(_):
        raise ModelFailure("FDE_PROVIDER_UNREACHABLE")

    first = scripted(engine, profile, timeout)
    assert first.transaction(agent_state.claim, UUID(profile), case)
    assert first.transaction(agent_state.claim, UUID(profile), case) is None

    def expire(db):
        db.get(models.AgentGrant, case).lease_until = now() - timedelta(seconds=1)

    first.transaction(expire)
    restarted = scripted(engine, profile, timeout)
    assert restarted.run_once(case) and not restarted.run_once(case)
    item = detail(client, case)
    assert item["state"] == "founder_queue"
    assert [message["kind"] for message in item["messages"]] == ["customer", "reply"]
    with Session(engine) as db:
        progress = db.get(models.AgentGrant, case).progress
        assert progress["trace"][-1]["error"] == "FDE_PROVIDER_UNREACHABLE"
        assert progress["usage"]["charged_or_reserved_nanousd"] > 0
    human = uuid4()
    register(app, profile, human)
    incoming(client, human, "请转人工，合同怎么签？")
    assert not restarted.run_once(human)
    assert detail(client, human)["state"] == "founder_queue"


def test_support_handoff_retains_actual_version_and_reproduction(
    client, auth, app, profile
):
    case = uuid4()
    register(app, profile, case)
    token, _ = incoming(client, case, "报价页用不了。", version_hint="1.1.0")
    first = scripted(
        app.state.engine,
        profile,
        lambda _: call("clarify", focus=["reproduction", "observed_result", "consent"]),
    )
    assert first.run_once(case)
    reproduction = "导入 CSV 后点击比较，页面提示缺少 unit_price。"
    _, customer_id = incoming(
        client, case, reproduction, token=token, willing_to_continue=True
    )
    second = scripted(
        app.state.engine,
        profile,
        lambda _: call("read_conversation"),
        lambda messages: handoff(messages, kind="support"),
    )
    assert second.run_once(case)
    item = detail(client, case)
    assert item["workflow"] == "support" and item["state"] == "fde_queue"
    assert item["handoff"]["reproduction"] == reproduction
    assert item["handoff"]["reproduction_message_id"] == customer_id
    assert item["handoff"]["product_version"] == "demo-supplier-quotes@1.1.0"
