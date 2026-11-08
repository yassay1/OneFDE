"""Staff dialogue restores turns without creating customer messages, work, inputs or runs."""

import json
from secrets import token_hex
from uuid import uuid4

from fastapi.testclient import TestClient

from onefde.entrypoints.api import create_app
from onefde.modules.dialogue.service import record_beat
from tests.support.factories import create_engagement, create_task

CUSTOMER_ORIGIN = "http://127.0.0.1:8765"
PUBLIC = "/api/v1/public/business/conversations"


def customer(text, **fields):
    return {"request_id": str(uuid4()), "text": text, **fields}


def start_case(client, data):
    url = f"{PUBLIC}/{uuid4()}"
    headers = {"Authorization": f"Bearer {token_hex(32)}", "Origin": CUSTOMER_ORIGIN}
    response = client.put(url, json=data, headers=headers)
    assert response.status_code == 200, response.text
    return url, headers, response.json()


def _post(client, auth, path, payload, key):
    return client.post(
        path,
        json=payload,
        headers={**auth, "Idempotency-Key": key},
    )


def test_business_assistant_restores_without_customer_message(client, auth):
    _, _, conversation = start_case(client, customer("门店报价怎么核对？"))
    case_id = conversation["id"]
    before = client.get(f"/api/v1/business/cases/{case_id}", headers=auth)
    assert before.status_code == 200, before.text
    messages = before.json()["messages"]

    first = _post(
        client,
        auth,
        f"/api/v1/business/cases/{case_id}/assistant",
        {"text": "这条该怎么回客户？"},
        "biz-ask-1",
    )
    assert first.status_code == 200, first.text
    body = first.json()["turns"]
    assert [item["author"] for item in body] == ["founder", "assistant"]
    assert body[1]["adapter"] == "scripted"
    assert body[1]["basis"]["sent"] is False
    assert "还没有发给客户" in body[1]["text"]
    assert "门店报价怎么核对" in body[1]["text"]

    replay = _post(
        client,
        auth,
        f"/api/v1/business/cases/{case_id}/assistant",
        {"text": "这条该怎么回客户？"},
        "biz-ask-1",
    )
    assert replay.json() == first.json()
    second = _post(
        client,
        auth,
        f"/api/v1/business/cases/{case_id}/assistant",
        {"text": "内部还缺什么？"},
        "biz-ask-2",
    )
    assert second.status_code == 200, second.text
    restored = client.get(f"/api/v1/business/cases/{case_id}/assistant", headers=auth)
    assert restored.status_code == 200, restored.text
    assert [item["text"] for item in restored.json()["turns"]] == [
        "这条该怎么回客户？",
        body[1]["text"],
        "内部还缺什么？",
        second.json()["turns"][1]["text"],
    ]
    after = client.get(f"/api/v1/business/cases/{case_id}", headers=auth)
    assert after.json()["messages"] == messages


def test_fde_dialogue_does_not_register_work(client, auth):
    project = create_engagement(client, auth, key="fde-dialogue")
    eid = project["id"]
    asked = _post(
        client,
        auth,
        f"/api/v1/engagements/{eid}/fde/dialogue",
        {"text": "现在缺什么？"},
        "fde-ask",
    )
    assert asked.status_code == 200, asked.text
    reply = asked.json()["turns"][1]
    assert reply["basis"]["registered"] is False
    assert "还没有登记" in reply["text"]
    assert client.get(f"/api/v1/engagements/{eid}/fde/work", headers=auth).json() == []
    again = client.get(f"/api/v1/engagements/{eid}/fde/dialogue", headers=auth)
    assert again.json()["turns"][0]["text"] == "现在缺什么？"


def test_engineering_dialogue_does_not_create_input_or_run(client, auth):
    project = create_engagement(client, auth, key="eng-dialogue")
    created = create_task(client, auth, project["id"], key="eng-dialogue-task")
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    asked = _post(
        client,
        auth,
        f"/api/v1/tasks/{task_id}/dialogue",
        {"text": "这轮在执行吗？"},
        "eng-ask",
    )
    assert asked.status_code == 200, asked.text
    reply = asked.json()["turns"][1]
    assert reply["basis"]["input_created"] is False
    assert reply["basis"]["run_started"] is False
    assert "没有追加输入" in reply["text"]
    assert "没有心跳" in reply["text"]
    inputs = client.get(f"/api/v1/tasks/{task_id}/inputs", headers=auth)
    runs = client.get(f"/api/v1/tasks/{task_id}/runs", headers=auth)
    assert inputs.json()["items"] == []
    assert runs.json()["items"] == []
    restored = client.get(f"/api/v1/tasks/{task_id}/dialogue", headers=auth)
    assert restored.json()["turns"][1]["text"] == reply["text"]


def test_knowledge_dialogue_does_not_invent_assets(client, auth):
    found = _post(
        client,
        auth,
        "/api/v1/knowledge/dialogue",
        {"text": "报价", "caller_role": "fde", "purpose": "delivery"},
        "kn-hit",
    )
    assert found.status_code == 200, found.text
    hit = found.json()["turns"][1]
    assert "fresh-quote-compare-csv@1.1.0" in hit["text"]
    assert hit["basis"]["invented"] is False
    assert "关键词" in hit["text"]
    missed = _post(
        client,
        auth,
        "/api/v1/knowledge/dialogue",
        {
            "text": "zzznomatchtoken",
            "caller_role": "fde",
            "purpose": "delivery",
        },
        "kn-miss",
    )
    assert missed.status_code == 200, missed.text
    assert "没有可见匹配" in missed.json()["turns"][1]["text"]
    assert "fixture-restricted" not in missed.text
    other = client.get(
        "/api/v1/knowledge/dialogue",
        params={"caller_role": "fde", "purpose": "public_marketing"},
        headers=auth,
    )
    assert other.json()["turns"] == []
    same = client.get(
        "/api/v1/knowledge/dialogue",
        params={"caller_role": "fde", "purpose": "delivery"},
        headers=auth,
    )
    assert len(same.json()["turns"]) == 4


def test_runtime_status_without_and_with_heartbeat(client, auth, app):
    quiet = client.get("/api/v1/runtime/status", headers=auth)
    assert quiet.status_code == 200, quiet.text
    body = quiet.json()
    assert body["fde_agent"]["state"] == "not_running"
    assert body["engineering_worker"]["state"] == "not_running"
    assert "没有心跳" in body["fde_agent"]["detail"]
    record_beat(app.state.engine, "engineering_worker")
    fresh = client.get("/api/v1/runtime/status", headers=auth).json()
    assert fresh["engineering_worker"]["state"] == "running"
    assert fresh["fde_agent"]["state"] == "not_running"


def test_live_staff_chat_is_refused(settings, client, auth):
    _, _, conversation = start_case(client, customer("只用来准备一个会话"))
    case_id = conversation["id"]
    live = create_app(settings.model_copy(update={"staff_chat_mode": "live"}))
    try:
        with TestClient(live, raise_server_exceptions=False) as live_client:
            live_client.cookies.update(client.cookies)
            refused = live_client.post(
                f"/api/v1/business/cases/{case_id}/assistant",
                json={"text": "不要调用模型"},
                headers={**auth, "Idempotency-Key": "live-refuse"},
            )
    finally:
        live.state.engine.dispose()
    assert refused.status_code == 503, refused.text
    assert refused.json()["code"] == "STAFF_CHAT_LIVE_UNAVAILABLE"
    restored = client.get(f"/api/v1/business/cases/{case_id}/assistant", headers=auth)
    assert restored.json()["turns"] == []


def _live(settings, client, responder):
    app = create_app(settings.model_copy(update={"staff_chat_mode": "live"}))
    app.state.staff_live = responder
    live = TestClient(app, raise_server_exceptions=False)
    live.__enter__()
    live.cookies.update(client.cookies)
    return app, live


def _close(app, live):
    live.__exit__(None, None, None)
    app.state.engine.dispose()


def test_live_handoff_stays_on_the_current_case(settings, client, auth):
    fact = "请核对两家供应商的苹果一级大果每公斤价格"
    url, headers, conversation = start_case(
        client, customer(fact, willing_to_continue=True)
    )
    case_id = conversation["id"]
    before = client.get(url, headers=headers).json()["messages"]

    def responder(role, question, context):
        assert role == "business"
        return json.dumps(
            {
                "reply": "当前 Case 的事实可以交接，不会发给客户。",
                "questions": [],
                "proposal": {
                    "action": "handoff_case",
                    "object": {
                        "case_id": case_id,
                        "title": "模拟报价交接",
                        "goal": fact,
                        "confirmed_facts": [fact],
                        "unknowns": ["运费不在本轮"],
                    },
                    "impact": "把当前 Case 交给 FDE",
                },
            }
        )

    app, live = _live(settings, client, responder)
    try:
        asked = _post(
            live,
            auth,
            f"/api/v1/business/cases/{case_id}/assistant",
            {"text": "把这个 Case 交给 FDE"},
            "live-handoff",
        )
    finally:
        _close(app, live)
    assert asked.status_code == 200, asked.text
    basis = asked.json()["turns"][1]["basis"]
    assert basis["sent"] is False
    assert basis["proposal"]["executed"] is True
    detail = client.get(f"/api/v1/business/cases/{case_id}", headers=auth).json()
    assert detail["state"] == "fde_queue"
    assert detail["handoff"]["confirmed_facts"] == [fact]
    public = client.get(url, headers=headers).json()
    assert public["messages"] == before
    assert "handoff" not in public


def test_live_proposal_cannot_name_another_case(settings, client, auth):
    _, _, conversation = start_case(client, customer("只看当前会话"))
    case_id = conversation["id"]

    def responder(role, question, context):
        return json.dumps(
            {
                "reply": "我不会处理别的会话。",
                "proposal": {
                    "action": "handoff_case",
                    "object": {
                        "case_id": str(uuid4()),
                        "title": "越权",
                        "goal": "越权",
                    },
                    "impact": "错误对象",
                },
            }
        )

    app, live = _live(settings, client, responder)
    try:
        asked = _post(
            live,
            auth,
            f"/api/v1/business/cases/{case_id}/assistant",
            {"text": "交给 FDE"},
            "live-foreign",
        )
    finally:
        _close(app, live)
    assert asked.status_code == 200, asked.text
    assert asked.json()["turns"][1]["basis"]["proposal_rejected"] == "anchor_or_role"
    assert (
        client.get(f"/api/v1/business/cases/{case_id}", headers=auth).json()["handoff"]
        is None
    )


def test_customer_reply_waits_for_the_bound_confirmation(settings, client, auth):
    url, headers, conversation = start_case(
        client, customer("门店想了解比较结果怎么看")
    )
    case_id = conversation["id"]
    taken = client.post(
        f"/api/v1/business/cases/{case_id}/actions",
        json={"action": "take_over"},
        headers={**auth, "Idempotency-Key": "live-take"},
    )
    assert taken.status_code == 200, taken.text
    before = client.get(url, headers=headers).json()["messages"]

    def responder(role, question, context):
        return json.dumps(
            {
                "reply": "下面这句需要你确认后才会发给客户。",
                "proposal": {
                    "action": "send_reply",
                    "object": {"text": "比较结果只说明约定口径，不含运费。"},
                    "impact": "向当前客户发送这一句",
                },
            }
        )

    app, live = _live(settings, client, responder)
    try:
        asked = _post(
            live,
            auth,
            f"/api/v1/business/cases/{case_id}/assistant",
            {"text": "准备一句客户回复"},
            "live-reply",
        )
        assert asked.status_code == 200, asked.text
        turn = asked.json()["turns"][1]
        assert turn["basis"]["sent"] is False
        assert turn["basis"]["pending_action"]["status"] == "pending"
        assert client.get(url, headers=headers).json()["messages"] == before
        declined = live.post(
            f"/api/v1/dialogue/turns/{turn['id']}/decision",
            json={"decision": "decline"},
            headers={**auth, "Idempotency-Key": "live-decline"},
        )
        assert declined.status_code == 200, declined.text
        assert declined.json()["basis"]["pending_action"]["status"] == "declined"
        again = live.post(
            f"/api/v1/dialogue/turns/{turn['id']}/decision",
            json={"decision": "confirm"},
            headers={**auth, "Idempotency-Key": "live-decline-again"},
        )
        assert again.status_code == 409, again.text
    finally:
        _close(app, live)
    assert client.get(url, headers=headers).json()["messages"] == before


def test_register_work_uses_the_user_words(settings, client, auth):
    project = create_engagement(client, auth, key="live-work")
    goal = "整理当前模拟项目的报价比较范围"

    def responder(role, question, context):
        return json.dumps(
            {
                "reply": "按你的原话登记工作。",
                "proposal": {
                    "action": "register_work",
                    "object": {"goal": "模型改写后的目标"},
                    "impact": "登记当前项目工作",
                },
            }
        )

    app, live = _live(settings, client, responder)
    try:
        asked = _post(
            live,
            auth,
            f"/api/v1/engagements/{project['id']}/fde/dialogue",
            {"text": goal},
            "live-work",
        )
    finally:
        _close(app, live)
    assert asked.status_code == 200, asked.text
    assert asked.json()["turns"][1]["basis"]["registered"] is True
    works = client.get(
        f"/api/v1/engagements/{project['id']}/fde/work", headers=auth
    ).json()
    assert works[0]["goal"] == goal


def test_answer_is_pending_until_owner_adopts_it(settings, client, auth):
    project = create_engagement(client, auth, key="live-answer")
    created = create_task(client, auth, project["id"], key="live-answer-task")
    assert created.status_code == 201, created.text
    task = created.json()
    question = client.post(
        f"/api/v1/tasks/{task['id']}/inputs",
        json={
            "expected_revision": task["revision"],
            "kind": "question",
            "text": "公开提示用哪一句？",
            "evidence_artifact_ids": [],
        },
        headers={**auth, "Idempotency-Key": "live-question"},
    )
    assert question.status_code == 201, question.text
    question_id = question.json()["input"]["id"]

    def responder(role, question_text, context):
        return json.dumps(
            {
                "reply": "这句先记成待采用答复。",
                "proposal": {
                    "action": "append_answer",
                    "object": {"question_id": question_id},
                    "impact": "写入当前任务的待采用答复",
                },
            }
        )

    app, live = _live(settings, client, responder)
    try:
        asked = _post(
            live,
            auth,
            f"/api/v1/tasks/{task['id']}/dialogue",
            {"text": "请用：此报价已不可用，请联系门店。"},
            "live-answer",
        )
        assert asked.status_code == 200, asked.text
        basis = asked.json()["turns"][1]["basis"]
        assert basis["input_created"] is True
        assert basis["run_started"] is False
        turn_id = asked.json()["turns"][1]["id"]
        stale = live.post(
            f"/api/v1/dialogue/turns/{turn_id}/decision",
            json={"decision": "confirm"},
            headers={**auth, "Idempotency-Key": "live-no-pending"},
        )
        assert stale.status_code == 404, stale.text
    finally:
        _close(app, live)
    inputs = client.get(f"/api/v1/tasks/{task['id']}/inputs", headers=auth).json()
    answer = next(item for item in inputs["items"] if item["kind"] == "answer")
    assert answer["status"] == "pending"
    assert answer["text"] == "请用：此报价已不可用，请联系门店。"
    assert (
        client.get(f"/api/v1/tasks/{task['id']}/runs", headers=auth).json()["items"]
        == []
    )


def test_confirmation_rejects_a_changed_revision(settings, client, auth):
    project = create_engagement(client, auth, key="live-stale")
    created = create_task(client, auth, project["id"], key="live-stale-task")
    task = created.json()

    def responder(role, question, context):
        return json.dumps(
            {
                "reply": "采用前要核对修订。",
                "proposal": {
                    "action": "apply_inputs",
                    "object": {
                        "task_id": task["id"],
                        "apply_ids": [str(uuid4())],
                        "reason": "核对",
                    },
                    "impact": "采用当前任务上的一组输入",
                },
            }
        )

    app, live = _live(settings, client, responder)
    try:
        asked = _post(
            live,
            auth,
            f"/api/v1/tasks/{task['id']}/dialogue",
            {"text": "采用刚才的答复"},
            "live-stale",
        )
        assert asked.status_code == 200, asked.text
        turn = asked.json()["turns"][1]
        assert turn["basis"]["pending_action"]["expected_revision"] == task["revision"]
        bumped = client.post(
            f"/api/v1/tasks/{task['id']}/inputs",
            json={
                "expected_revision": task["revision"],
                "kind": "clarification",
                "text": "补充一条范围说明",
                "evidence_artifact_ids": [],
            },
            headers={**auth, "Idempotency-Key": "live-bump"},
        )
        assert bumped.status_code == 201, bumped.text
        refused = live.post(
            f"/api/v1/dialogue/turns/{turn['id']}/decision",
            json={"decision": "confirm"},
            headers={**auth, "Idempotency-Key": "live-stale-confirm"},
        )
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "STAFF_OBJECT_STALE"
    finally:
        _close(app, live)


def test_knowledge_live_mode_still_uses_the_catalog(settings, client, auth):
    def responder(role, question, context):
        raise AssertionError("knowledge dialogue must not call the staff model")

    app, live = _live(settings, client, responder)
    try:
        asked = _post(
            live,
            auth,
            "/api/v1/knowledge/dialogue",
            {"text": "报价", "caller_role": "fde", "purpose": "delivery"},
            "live-knowledge",
        )
    finally:
        _close(app, live)
    assert asked.status_code == 200, asked.text
    reply = asked.json()["turns"][1]
    assert reply["adapter"] == "scripted"
    assert "fresh-quote-compare-csv@1.1.0" in reply["text"]
