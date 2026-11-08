"""FDE control proof with real PostgreSQL and explicitly scripted model replies."""

import hashlib
import io
import json
import os
import tarfile
from datetime import timedelta
from pathlib import Path
from secrets import token_hex
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from onefde.core.clock import now
from onefde.core.errors import ApiException
from onefde.entrypoints.fde_agent import DeliveryAgent
from onefde.infrastructure.artifacts import PrivateArtifactStore
from onefde.modules.fde import agent_tools, agent_work
from onefde.modules.fde.agent_models import AgentGrant, AgentWork
from onefde.modules.fde.agent_schemas import DemoPolicy, ModelBudget
from onefde.modules.tasks import models as m
from onefde.modules.tasks import service as tasks
from tests.support.factories import create_engagement, create_task

GOAL = "模拟维修店想在撤回报价后给客户一个更清楚的提示。"
CHECK = "python -B -m unittest -v check_quote"
PLAN = {
    "title": "模拟维修报价撤回提示",
    "objective": "说明当前报价不可用并提供下一步",
    "scope": "现有报价界面的撤回提示；保持原访问权限",
    "confirmed_rules": ["仅提示联系门店，不暴露报价数据"],
    "completion_criteria": ["已撤回的报价显示获准提示且不回显项目及金额"],
    "source_message_ids": [],
    "capability_versions": [],
}


def seed(client, auth):
    project = create_engagement(client, auth, str(uuid4()))
    path = "/api/v1/public/business/conversations/" + str(uuid4())
    token = {
        "Authorization": f"Bearer {token_hex(32)}",
        "Origin": "http://127.0.0.1:8765",
    }
    first = client.put(
        path, headers=token, json={"request_id": str(uuid4()), "text": GOAL}
    )
    assert first.status_code == 200, first.text
    case_id = first.json()["id"]
    case = client.post(
        f"/api/v1/business/cases/{case_id}/actions",
        headers=auth,
        json={
            "action": "handoff",
            "title": "维修报价查看",
            "goal": GOAL,
            "confirmed_facts": [],
            "unknowns": ["撤回提示文字"],
            "reproduction": None,
        },
    )
    assert case.status_code == 200, case.text
    work_path = f"/api/v1/engagements/{project['id']}/fde/work"
    return project, path, token, case_id, work_path


def start(client, auth, work_path, case_id=None):
    body = {"case_id": case_id, "goal": None if case_id else GOAL}
    headers = auth | {"Idempotency-Key": str(uuid4())}
    response = client.post(work_path, json=body, headers=headers)
    assert response.status_code == 202, response.text
    assert client.post(work_path, json=body, headers=headers).json() == response.json()
    return UUID(response.json()["id"])


def post_answer(client, path, token, content):
    body = {"request_id": str(uuid4()), "text": content}
    reply = client.post(path + "/messages", json=body, headers=token)
    assert reply.status_code == 200, reply.text
    assert (
        client.post(path + "/messages", json=body, headers=token).json() == reply.json()
    )
    return reply.json()["messages"][-1]["id"]


def agent(app, tmp_path, profile=None, model=None, *, maximum=60):
    return DeliveryAgent(
        app.state.engine,
        PrivateArtifactStore(tmp_path / "private"),
        model,
        max_calls=maximum,
        profile_id=UUID(profile) if profile else None,
        budget=ModelBudget(
            max_cost_nanousd=10_000_000,
            max_input_tokens=200_000,
            input_nanousd_per_token=1,
            output_nanousd_per_token=1,
        ),
    )


def enroll(a, work_id, profile, *, expires_at=None):
    package = io.BytesIO()
    product = Path("../products/demo-repair-quote-view")
    with tarfile.open(fileobj=package, mode="w:gz") as bundle:
        for name in ("DESIGN.md", "index.html", "repair_quotes.py", "check_quote.py"):
            bundle.add(product / name, arcname=name)
    archive = package.getvalue()
    a.transaction(
        agent_work.enroll,
        work_id,
        UUID(profile),
        DemoPolicy(
            expires_at=expires_at or now() + timedelta(minutes=10),
            max_model_calls=50,
            max_clarifications=2,
            max_runs=2,
            max_fde_cost_nanousd=8_000_000,
            max_engineering_cost_nanousd_per_run=250_000_000,
            source_sha256=hashlib.sha256(archive).hexdigest(),
            allowed_paths=["index.html", "DESIGN.md"],
            review_paths=["index.html", "DESIGN.md"],
            checks=[CHECK],
        ),
        archive,
        a.store,
    )


def request(tool, **kwargs):
    return {
        "id": str(uuid4()),
        "type": "function",
        "function": {"name": tool, "arguments": json.dumps(kwargs)},
    }


def invoke(a, claim, tool, **kwargs):
    return a.transaction(a.invoke, *claim, request(tool, **kwargs))


def send_draft(a, claim, source, public):
    draft = invoke(
        a,
        claim,
        "draft_clarification",
        source_message_id=source,
        expected_last_public_message_id=public,
        understanding="撤回后希望更清楚地说明下一步",
        question="希望客户看到什么提示？",
    )
    assert draft["last_public_message_id"] == public
    return invoke(
        a, claim, "send_clarification", expected_last_public_message_id=public
    )


def adopt_answer(a, claim, task, answer_id, question_id=None):
    added = invoke(
        a,
        claim,
        "record_customer_input",
        message_id=answer_id,
        expected_revision=task["revision"],
        reply_to_input_id=question_id,
    )
    return invoke(
        a,
        claim,
        "adopt_inputs",
        expected_revision=added["task"]["revision"],
        apply_ids=[added["input"]["id"]],
        reason="模拟客户已在原会话确认",
        plan=PLAN | {"source_message_ids": [answer_id]},
    )


def accept_dispatch(a, work_id):
    return a.transaction(
        lambda db, identifier: agent_tools.confirm_dispatch(
            db, db.get(AgentWork, identifier)
        ),
        work_id,
    )


def claim_engineering(a, cost=0.25):
    return a.transaction(
        tasks.claim_next,
        "fixture-worker",
        120,
        lambda db, run: agent_work.claim_allowed(db, run, cost),
    )


def test_scope_stale_evidence_and_ordinary_work(client, auth, app, profile, tmp_path):
    project, path, token, case_id, work_path = seed(client, auth)
    other, _, _, other_case, other_work_path = seed(client, auth)
    a = agent(app, tmp_path, profile)
    work_id = start(client, auth, work_path, case_id)
    assert (
        client.post(
            other_work_path,
            json={"case_id": case_id},
            headers=auth
            | {
                "Idempotency-Key": str(uuid4()),
            },
        ).status_code
        == 409
    )
    unrelated = start(client, auth, other_work_path, other_case)
    other_claim = a.transaction(agent_work.claim, unrelated)
    foreign = invoke(a, other_claim, "read_conversation")["latest_customer_message_id"]
    a.transaction(a.release, *other_claim)
    claim = a.transaction(agent_work.claim, work_id)
    context = invoke(a, claim, "read_conversation")
    head, public = (
        context["latest_customer_message_id"],
        context["last_public_message_id"],
    )
    assert (
        invoke(a, claim, "create_task", **(PLAN | {"source_message_ids": [foreign]}))[
            "error"
        ]
        == "FDE_SOURCE_DENIED"
    )
    assert (
        invoke(a, claim, "create_task", **(PLAN | {"engagement_id": other["id"]}))[
            "error"
        ]
        == "FDE_BAD_ARGUMENTS"
    )
    assert (
        invoke(
            a,
            claim,
            "create_task",
            **(PLAN | {"capability_versions": ["fresh-quote-compare-csv@old"]}),
        )["error"]
        == "FDE_ASSET_STALE"
    )
    assert invoke(a, claim, "propose_review")["error"] == "FDE_TOOL_DENIED"
    consultation = invoke(
        a,
        claim,
        "consult_knowledge",
        asset_ids=["fresh-quote-compare-csv"],
        question="CSV 比较能力能用于当前项目吗？",
    )
    assert consultation["options"][0]["reference"] == "fresh-quote-compare-csv@1.1.0"
    assert consultation["options"][0]["not_applicable_when"]
    assert send_draft(a, claim, head, public)["error"] == "FDE_SEND_DENIED"
    task = invoke(a, claim, "create_task", **PLAN)["task"]
    assert task["engagement_id"] == project["id"]
    assert (
        invoke(a, claim, "delegate_engineering", expected_revision=task["revision"])[
            "error"
        ]
        == "FDE_DISPATCH_DENIED"
    )
    newer = post_answer(client, path, token, "请写明可联系门店，并继续保留撤回限制。")
    with pytest.raises(ApiException, match="FDE_EVIDENCE_CHANGED"):
        invoke(a, claim, "send_clarification", expected_last_public_message_id=public)
    a.transaction(a.release, *claim)
    claim = a.transaction(agent_work.claim, work_id)
    assert (
        invoke(
            a,
            claim,
            "record_customer_input",
            message_id=head,
            expected_revision=task["revision"],
        )["error"]
        == "FDE_MESSAGE_STALE"
    )
    added = invoke(
        a,
        claim,
        "record_customer_input",
        message_id=newer,
        expected_revision=task["revision"],
    )
    assert (
        invoke(
            a,
            claim,
            "record_customer_input",
            message_id=newer,
            expected_revision=task["revision"],
        )["error"]
        == "FDE_TASK_STALE"
    )
    assert (
        invoke(
            a,
            claim,
            "adopt_inputs",
            expected_revision=added["task"]["revision"],
            apply_ids=[str(uuid4())],
            reason="伪造引用",
            plan=PLAN,
        )["error"]
        == "INPUT_SCOPE_CONFLICT"
    )
    assert invoke(a, claim, "read_run", run_id=str(uuid4()))["error"] == "FDE_RUN_SCOPE"


def test_restart_replay_dispatch_and_advisory_review(
    client, auth, app, profile, tmp_path
):
    project, path, token, case_id, work_path = seed(client, auth)
    a = agent(app, tmp_path, profile)
    work_id = start(client, auth, work_path, case_id)
    enroll(a, work_id, profile)
    first = a.transaction(agent_work.claim, work_id)
    assert a.transaction(agent_work.claim, work_id) is None
    conversation = invoke(a, first, "read_conversation")
    original = conversation["latest_customer_message_id"]
    sent = send_draft(a, first, original, conversation["last_public_message_id"])
    assert sent["case_id"] == case_id

    # Simulate process death after committing the send, before reporting the turn.
    def expire(db):
        db.get(AgentWork, work_id).lease_until = now() - timedelta(seconds=1)

    a.transaction(expire)
    restarted = agent(app, tmp_path, profile)
    second = restarted.transaction(agent_work.claim, work_id)
    with pytest.raises(ApiException, match="FDE_LEASE_LOST"):
        invoke(a, first, "read_project")
    assert (
        send_draft(restarted, second, original, sent["message_id"])["error"]
        == "FDE_ALREADY_SENT"
    )
    restarted.transaction(restarted.finish, *second, "等待原会话补答")
    assert not restarted.run_once(work_id)
    answer = post_answer(
        client, path, token, "撤回后只显示请联系门店，客户也不能看到报价明细。"
    )
    third = restarted.transaction(agent_work.claim, work_id)
    assert (
        invoke(
            restarted,
            third,
            "send_clarification",
            expected_last_public_message_id=sent["message_id"],
        )["error"]
        == "FDE_MESSAGE_STALE"
    )
    task = invoke(
        restarted, third, "create_task", **(PLAN | {"source_message_ids": [answer]})
    )["task"]
    assert invoke(restarted, third, "create_task", **PLAN)["task"]["id"] == task["id"]
    assert (
        invoke(
            restarted, third, "delegate_engineering", expected_revision=task["revision"]
        )["error"]
        == "FDE_INPUT_NOT_ADOPTED"
    )
    adopted = adopt_answer(restarted, third, task, answer)
    assert adopted["spec_version"] == 2
    assert (
        invoke(
            restarted, third, "delegate_engineering", expected_revision=task["revision"]
        )["error"]
        == "FDE_TASK_STALE"
    )
    delegated = invoke(
        restarted, third, "delegate_engineering", expected_revision=adopted["revision"]
    )
    assert delegated["pending_dispatch"]["status"] == "pending"
    assert "run" not in delegated
    assert (
        invoke(
            restarted,
            third,
            "delegate_engineering",
            expected_revision=delegated["task"]["revision"],
        )["error"]
        == "FDE_ALREADY_DELEGATED"
    )
    restarted.transaction(restarted.finish, *third, "等待确认工程派发")
    confirmed = accept_dispatch(restarted, work_id)
    run = confirmed["run"]
    assert claim_engineering(restarted, cost=1) is None
    job = claim_engineering(restarted)
    assert job["snapshot"]["original_request"] == GOAL
    assert job["snapshot"]["engineering"]["initial_source"]["allowed_paths"] == [
        "DESIGN.md",
        "index.html",
    ]
    assert job["snapshot"]["engineering"]["checks"][-1]["command"] == CHECK
    assert job["snapshot"]["inputs"][0]["status"] == "applied"
    assert not restarted.run_once(work_id)  # claiming alone isn't a business event

    # Deterministic engineering asks a question, and the same Task continues.
    restarted.transaction(
        tasks.complete_claim,
        job["operation_id"],
        "fixture-worker",
        job["claim_token"],
        {
            "state": "completed",
            "outcome": "needs_input",
            "summary": "模拟工程提问",
            "question": "请确认公开提示使用哪句文案",
            "stopped": True,
        },
        (),
        {"stopped": True},
    )
    fourth = restarted.transaction(agent_work.claim, work_id)
    details = invoke(restarted, fourth, "read_task")
    question = next(item for item in details["items"] if item["kind"] == "question")
    assert question["origin_run_id"] == run["id"]
    restarted.transaction(restarted.finish, *fourth, "等待客户确认确切文案")
    answer = post_answer(client, path, token, "请用这句：此报价已不可用，请联系门店。")
    fifth = restarted.transaction(agent_work.claim, work_id)
    task = invoke(restarted, fifth, "read_task")["task"]
    adopted = adopt_answer(restarted, fifth, task, answer, question["id"])
    continued = invoke(
        restarted, fifth, "delegate_engineering", expected_revision=adopted["revision"]
    )
    assert continued["pending_dispatch"]["command"] == "continue"
    assert continued["task"]["id"] == task["id"]
    restarted.transaction(restarted.finish, *fifth, "等待确认续作")
    confirmed = accept_dispatch(restarted, work_id)
    assert confirmed["run"]["id"] != run["id"]
    continued = confirmed
    job = claim_engineering(restarted)
    assert job["run_id"] == UUID(continued["run"]["id"])
    baseline = job["snapshot"]["engineering"]["initial_source"]["sha256"]
    key = f"engagements/{project['id']}/runs/{job['run_id']}/deterministic"
    blob = a.store.put(key, b"deterministic control fixture; no real engineering")
    result = {
        "state": "completed",
        "outcome": "submitted",
        "summary": "模拟工程提交",
        "stopped": True,
        "artifacts": [{"name": "workspace.tar.gz", "kind": "source-snapshot", **blob}],
    }
    proof = {
        "stopped": True,
        "validation": {
            "passed": True,
            "results": [
                {"command": CHECK, "exit_code": 0, "timeout": False},
            ],
        },
        "review_material": {
            "mode": "deterministic",
            "artifact_sha256": blob["sha256"],
            "baseline_sha256": baseline,
            "design": "模拟",
            "diff": "",
            "diff_truncated": False,
        },
    }
    complete = (
        job["operation_id"],
        "fixture-worker",
        job["claim_token"],
        result,
        (key,),
        proof,
    )
    restarted.transaction(tasks.complete_claim, *complete)
    restarted.transaction(tasks.complete_claim, *complete)
    sixth = restarted.transaction(agent_work.claim, work_id)
    task = invoke(restarted, sixth, "read_task")["task"]
    evidence = invoke(restarted, sixth, "read_run", run_id=str(job["run_id"]))[
        "evidence"
    ]
    review = {
        "expected_revision": task["revision"],
        "run_id": str(job["run_id"]),
        "artifact_id": evidence["artifact_id"],
        "verdict": "accept",
        "reason": "确定性独立检查证据已关联",
        "next_step": "请创始人决定是否接受",
    }
    assert (
        invoke(
            restarted,
            sixth,
            "suggest_review",
            **(review | {"artifact_id": str(uuid4())}),
        )["error"]
        == "FDE_REVIEW_STALE"
    )
    assert (
        invoke(
            restarted,
            sixth,
            "suggest_review",
            **(review | {"expected_revision": task["revision"] - 1}),
        )["error"]
        == "FDE_TASK_STALE"
    )
    assert invoke(restarted, sixth, "suggest_review", **review)["validation_passed"]
    restarted.transaction(restarted.finish, *sixth, "已给出评审建议，等待业务接受")
    assert not restarted.run_once(work_id)
    work = client.get(work_path).json()[0]
    assert work["report"]["review_suggestion"]["artifact_sha256"] == blob["sha256"]
    if output := os.environ.get("ONEFDE_FDE_CONTROL_EVIDENCE"):
        Path(output).write_text(
            json.dumps(
                {
                    "scope": "deterministic PostgreSQL control fixture",
                    "demo": "demo-repair-quote-view",
                    "engagement_id": project["id"],
                    "case_id": case_id,
                    "work_id": str(work_id),
                    "task_id": task["id"],
                    "question_run_id": run["id"],
                    "submitted_run_id": str(job["run_id"]),
                    "baseline_sha256": baseline,
                    "artifact_id": evidence["artifact_id"],
                    "artifact_sha256": blob["sha256"],
                    "trace": work["trace"],
                    "actual_model_calls": 0,
                    "actual_model_cost_usd": 0,
                    "engineering_submission": "deterministic fixture",
                    "business_acceptance": "not recorded",
                    "release": "not performed",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    with Session(app.state.engine) as db:
        assert db.scalar(select(func.count(m.Task.id))) == 1
        assert db.scalar(select(func.count(m.Run.id))) == 2
        assert db.scalar(select(func.count(m.TaskReview.id))) == 0
        assert db.get(m.Task, UUID(task["id"])).state == "review"
        assert db.get(AgentGrant, work_id).sent == 1


@pytest.mark.parametrize("tool", ["delegate_engineering", "read_run"])
@pytest.mark.parametrize("state", ["queued", "running", "cancel_requested"])
def test_active_engineering_result_ends_fde_turn(
    client, auth, app, tmp_path, monkeypatch, tool, state
):
    project = create_engagement(client, auth)
    work_id = start(client, auth, f"/api/v1/engagements/{project['id']}/fde/work")
    calls = []

    def model(messages, tools):
        calls.append(messages)
        assert len(calls) == 1, "FDE must wait for a new engineering fact"
        return {"role": "assistant", "tool_calls": [request(tool)]}, {
            "prompt_tokens": 10,
            "completion_tokens": 2,
        }

    a = agent(app, tmp_path, model=model)
    monkeypatch.setattr(
        a, "invoke", lambda db, *args: {"run": {"id": str(uuid4()), "state": state}}
    )
    assert a.run_once(work_id)
    assert not a.run_once(work_id)
    with Session(app.state.engine) as db:
        work = db.get(AgentWork, work_id)
        assert work.calls == len(calls) == 1
        assert work.report["error"] is None
        assert "等待" in work.report["summary"]


@pytest.mark.parametrize("state", ["succeeded", "cancelled"])
def test_closed_task_reporting_uses_no_model(
    client, auth, app, tmp_path, monkeypatch, state
):
    project = create_engagement(client, auth)
    work_id = start(client, auth, f"/api/v1/engagements/{project['id']}/fde/work")
    a = agent(
        app, tmp_path, model=lambda *_: pytest.fail("closed work must not spend tokens")
    )
    monkeypatch.setattr(a, "context", lambda db, *args: {"task_state": state})
    assert a.run_once(work_id)
    assert not a.run_once(work_id)
    with Session(app.state.engine) as db:
        work = db.get(AgentWork, work_id)
        assert work.calls == 0
        assert work.report["error"] is None


def test_model_receives_tool_results_and_persists_usage(client, auth, app, tmp_path):
    project = create_engagement(client, auth)
    work_id = start(client, auth, f"/api/v1/engagements/{project['id']}/fde/work")
    calls = 0

    def model(messages, tools):
        nonlocal calls
        calls += 1
        assert "propose_review" not in {tool["function"]["name"] for tool in tools}
        assert "delegate_engineering" in {tool["function"]["name"] for tool in tools}
        if calls == 1:
            reply = {"tool_calls": [request("read_project")]}
        elif calls == 2:
            assert json.loads(messages[-1]["content"])["project"]["id"] == project["id"]
            reply = {"tool_calls": [request("create_task", **PLAN)]}
        else:
            assert json.loads(messages[-1]["content"])["task"]["state"] == "draft"
            reply = {"content": "已起草方案，请负责人确认执行。"}
        return {"role": "assistant", **reply}, {
            "prompt_tokens": 10,
            "completion_tokens": 2,
        }

    a = agent(app, tmp_path, model=model, maximum=3)
    assert a.run_once(work_id)
    assert not a.run_once(work_id)
    with Session(app.state.engine) as db:
        row = db.get(AgentWork, work_id)
        assert calls == row.calls == 3
        assert row.usage == {
            "prompt_tokens": 30,
            "completion_tokens": 6,
            "cost_charged_or_reserved_nanousd": 36,
        }
        assert [item["tool"] for item in row.trace] == ["read_project", "create_task"]
        assert row.report["summary"] == "已起草方案，请负责人确认执行。"


def test_approved_business_handoff_wakes_the_same_linked_task(
    client, auth, app, tmp_path
):
    project, _, _, case_id, work_path = seed(client, auth)
    task = create_task(client, auth, project["id"]).json()
    response = client.post(
        f"/api/v1/business/cases/{case_id}/actions",
        json={
            "action": "accept_handoff",
            "engagement_id": project["id"],
            "task_id": task["id"],
        },
        headers=auth | {"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    work = client.get(work_path).json()
    assert (
        len(work) == 1
        and work[0]["case_id"] == case_id
        and work[0]["task_id"] == task["id"]
    )
    a = agent(app, tmp_path)
    claim = a.transaction(agent_work.claim, UUID(work[0]["id"]))
    assert invoke(a, claim, "read_task")["task"]["id"] == task["id"]


def test_expired_demo_grant_blocks_model_send_and_dispatch(
    client, auth, app, profile, tmp_path
):
    _, _, _, case_id, work_path = seed(client, auth)
    a = agent(
        app, tmp_path, profile, model=lambda *_: pytest.fail("expired model access")
    )
    work_id = start(client, auth, work_path, case_id)
    enroll(a, work_id, profile)
    claim = a.transaction(agent_work.claim, work_id)
    current = invoke(a, claim, "read_conversation")
    task = invoke(a, claim, "create_task", **PLAN)["task"]

    def expire(db):
        db.get(AgentGrant, work_id).expires_at = now() - timedelta(seconds=1)

    a.transaction(expire)
    assert (
        send_draft(
            a,
            claim,
            current["latest_customer_message_id"],
            current["last_public_message_id"],
        )["error"]
        == "FDE_SEND_DENIED"
    )
    assert (
        invoke(a, claim, "delegate_engineering", expected_revision=task["revision"])[
            "error"
        ]
        == "FDE_DISPATCH_DENIED"
    )
    a.transaction(a.release, *claim)
    assert a.run_once(work_id)
    work = client.get(work_path).json()[0]
    assert work["calls"] == 0
    assert work["report"]["error"] == "FDE_MODEL_BUDGET_OR_EXPIRY"


def test_worker_does_not_claim_after_new_customer_message(
    client, auth, app, profile, tmp_path
):
    _, path, token, case_id, work_path = seed(client, auth)
    a = agent(app, tmp_path, profile)
    work_id = start(client, auth, work_path, case_id)
    enroll(a, work_id, profile)
    claim = a.transaction(agent_work.claim, work_id)
    head = invoke(a, claim, "read_conversation")["latest_customer_message_id"]
    task = invoke(a, claim, "create_task", **PLAN)["task"]
    adopted = adopt_answer(a, claim, task, head)
    delegated = invoke(
        a, claim, "delegate_engineering", expected_revision=adopted["revision"]
    )
    assert delegated["pending_dispatch"]["status"] == "pending"
    assert "operation_id" not in delegated
    a.transaction(a.finish, *claim, "工程派发待确认")
    confirmed = accept_dispatch(a, work_id)
    post_answer(client, path, token, "补充：撤回提示还需要核对。")
    assert claim_engineering(a) is None
    with Session(app.state.engine) as db:
        job = db.get(m.DispatchJob, UUID(confirmed["operation_id"]))
        assert job.state == "pending" and job.attempts == 0
