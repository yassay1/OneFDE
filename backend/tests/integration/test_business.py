from concurrent.futures import ThreadPoolExecutor
from secrets import token_hex
from uuid import uuid4

import pytest

from tests.support.factories import create_engagement, task_payload

CUSTOMER_ORIGIN = "http://127.0.0.1:8765"
PUBLIC = "/api/v1/public/business/conversations"
STAFF = "/api/v1/business"


def customer(text, **fields):
    return {"request_id": str(uuid4()), "text": text, **fields}


def start_case(client, data):
    url = f"{PUBLIC}/{uuid4()}"
    headers = {"Authorization": f"Bearer {token_hex(32)}", "Origin": CUSTOMER_ORIGIN}
    response = client.put(url, json=data, headers=headers)
    assert response.status_code == 200, response.text
    return url, headers, response.json()


def test_faq_scope_replay_and_separate_credentials(client):
    first = customer("CSV 格式是什么？", project_hint=str(uuid4()))
    url, headers, conversation = start_case(client, first)
    assert [item["kind"] for item in conversation["messages"]] == ["customer", "reply"]
    assert "unit_price,currency" in conversation["messages"][-1]["text"]
    assert client.put(url, json=first, headers=headers).json() == conversation
    assert client.get(url, headers=headers).json() == conversation
    assert client.get(url).status_code == 404
    another, other_headers, _ = start_case(
        client, customer("怎么导出？", version_hint="v2")
    )
    assert client.get(another, headers=headers).status_code == 404
    assert (
        client.post(
            f"{url}/messages", headers=other_headers, json=customer("你好")
        ).status_code
        == 404
    )
    assert (
        "请说明"
        in client.get(another, headers=other_headers).json()["messages"][-1]["text"]
    )
    assert (
        client.post(
            f"{url}/messages",
            headers=headers | {"Origin": "https://example.invalid"},
            json=customer("怎么导出？"),
        ).status_code
        == 403
    )
    second = customer("怎么导出？")
    response = client.post(f"{url}/messages", headers=headers, json=second)
    assert "导出全部结果 CSV" in response.json()["messages"][-1]["text"]
    assert (
        client.post(f"{url}/messages", headers=headers, json=second).json()
        == response.json()
    )
    assert (
        client.post(
            f"{url}/messages", headers=headers, json=second | {"text": "不同消息"}
        ).status_code
        == 409
    )


def test_public_preflight_does_not_allow_cookies(client):
    response = client.options(
        f"{PUBLIC}/{uuid4()}",
        headers={
            "Origin": CUSTOMER_ORIGIN,
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == CUSTOMER_ORIGIN
    assert "Access-Control-Allow-Credentials" not in response.headers


def act(client, auth, case, action, *, status=200, key=None, **values):
    response = client.post(
        f"{STAFF}/cases/{case}/actions",
        json={"action": action, **values},
        headers={**auth, "Idempotency-Key": key or str(uuid4())},
    )
    assert response.status_code == status, response.text
    return response.json()


def send(client, url, headers, data):
    response = client.post(f"{url}/messages", json=data, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_clarification_preview_is_private_and_stale_send_conflicts(client, auth):
    url, token, public = start_case(client, customer("希望做个工具"))
    case = public["id"]
    updated = send(client, url, token, customer("希望显示项目的记录"))
    source = next(
        row["id"] for row in updated["messages"] if row["text"] == "希望显示项目的记录"
    )
    project = create_engagement(client, auth)
    act(
        client,
        auth,
        case,
        "accept_handoff",
        engagement_id=project["id"],
        spec=task_payload()["spec"],
    )
    draft_url = f"{STAFF}/cases/{case}/clarification-draft"
    request = {
        "source_message_id": source,
        "understanding": "查看项目记录",
        "question": "谁可以查看？",
        "kind": "clarify",
    }
    response = client.post(draft_url, headers=auth, json=request)
    assert response.status_code == 200, response.text
    preview = response.json()
    assert "business:" in preview["internal_summary"]
    assert "business:" not in preview["public_reply"]
    assert "谁可以查看？" not in client.get(url, headers=token).text
    send(client, url, token, customer("只让店长查看"))
    values = {
        "text": preview["public_reply"],
        "source_message_id": source,
        "expected_last_public_message_id": preview["last_public_message_id"],
    }
    act(client, auth, case, "send_clarification", status=409, **values)
    fresh = client.post(draft_url, headers=auth, json=request).json()
    values["expected_last_public_message_id"] = fresh["last_public_message_id"]
    saved = act(client, auth, case, "send_clarification", **values)
    assert saved["messages"][-1]["reference"] == {"draft_from_message_id": source}
    assert (
        client.get(url, headers=token).json()["messages"][-1]["text"]
        == preview["public_reply"]
    )


@pytest.mark.parametrize("text", ["请转人工", "项目报价多少钱，多久交付？"])
def test_founder_takeover_keeps_auto_reply_paused(client, auth, text):
    url, token, public = start_case(client, customer(text))
    case = public["id"]
    detail_url = f"{STAFF}/cases/{case}"
    assert client.get(detail_url).json()["state"] == "founder_queue"
    assert (
        client.post(f"{detail_url}/actions", json={"action": "take_over"}).status_code
        == 403
    )
    act(client, auth, case, "take_over")
    updated = send(client, url, token, customer("CSV 格式是什么？"))
    assert [item["kind"] for item in updated["messages"]] == [
        "customer",
        "reply",
        "customer",
    ]
    act(client, auth, case, "note", text="内部成本信息")
    act(client, auth, case, "reply", text="人工回复")
    detail = client.get(detail_url).json()
    assert detail["handler"] == "founder"
    assert detail["messages"][-2]["kind"] == "note"
    assert client.get(url, headers=token).json()["messages"][-1]["text"] == "人工回复"
    assert "内部成本" not in client.get(url, headers=token).text


def fault_case(client, auth):
    url, token, public = start_case(
        client,
        customer(
            "CSV 格式没问题，但今天导入报错",
            project_hint=str(uuid4()),
            version_hint="客户猜测 v2",
        ),
    )
    case = public["id"]
    assert "触发问题" in public["messages"][-1]["text"]
    second = customer("选择 CSV 后点击比较，提示缺少 unit_price")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: send(client, url, token, second), range(2)))
    assert results[0] == results[1]
    detail = client.get(f"{STAFF}/cases/{case}").json()
    assert detail["state"] == "fde_queue"
    assert detail["engagement_id"] is None and detail["reported_version"] is None
    assert len(detail["messages"]) == 4
    assert len(detail["handoff"]["sources"]) == 2
    assert detail["handoff"]["reproduction"] == second["text"]
    return url, token, detail


def test_fault_priority_handoff_and_task_input(client, auth):
    url, token, detail = fault_case(client, auth)
    case = detail["id"]
    replay = act(
        client,
        auth,
        case,
        "handoff",
        title="重复转交",
        goal="核实",
        confirmed_facts=[],
        unknowns=[],
    )
    assert replay["handoff"] == detail["handoff"]
    eid = create_engagement(client, auth)["id"]
    confirmed = act(
        client,
        auth,
        case,
        "accept_handoff",
        engagement_id=eid,
        reported_version="demo-supplier-quotes@1.1.0",
        spec=task_payload()["spec"],
    )
    task = client.get(f"/api/v1/tasks/{confirmed['task_id']}").json()
    assert task["owner_role"] == "fde" and task["state"] == "draft"
    assert task["engagement_id"] == eid
    update = send(client, url, token, customer("还需要支持导入时保留备注。"))
    message_id = update["messages"][-1]["id"]
    act(client, auth, case, "record_input", message_id=message_id)
    act(client, auth, case, "record_input", message_id=message_id)
    inputs = client.get(f"/api/v1/tasks/{task['id']}/inputs").json()["items"]
    assert len(inputs) == 1 and inputs[0]["status"] == "pending"
    assert "保留备注" in inputs[0]["text"]
    assert client.get(f"/api/v1/tasks/{task['id']}").json()["spec_version"] == 1


@pytest.mark.parametrize("passed", [True, False])
def test_retest_keeps_fixed_version_and_customer_confirmation(
    client, auth, control, passed
):
    url, token, detail = fault_case(client, auth)
    case = detail["id"]
    act(
        client,
        auth,
        case,
        "accept_handoff",
        engagement_id=control.eid,
        reported_version="demo-supplier-quotes@1.1.0",
        task_id=control.tid,
    )
    run = control.start()
    control.claim(run)
    control.finish(run)
    artifact_id = control.artifact(run)
    notice = dict(
        artifact_id=artifact_id,
        version="quote-repair-fixture",
        access_url="http://127.0.0.1:8765/",
        steps="导入 S01 并点击比较",
        access_evidence="模拟验收：fixture 固定产物与本地地址",
    )
    act(client, auth, case, "notify_retest", status=409, **notice)
    control.review(run)
    pending = act(client, auth, case, "notify_retest", **notice)
    assert pending["state"] == "awaiting_retest"
    assert pending["retest"]["run_id"] == run["id"]
    view = client.get(url, headers=token).json()
    assert view["retest_notice_id"] == pending["retest"]["notice_id"]
    result = customer(
        "可用" if passed else "点击比较后仍报错",
        passed=passed,
        notice_id=view["retest_notice_id"],
    )
    assert (
        client.post(
            f"{url}/retest", json=result | {"notice_id": 999}, headers=token
        ).status_code
        == 409
    )
    response = client.post(f"{url}/retest", json=result, headers=token)
    assert response.status_code == 200, response.text
    assert (
        client.post(f"{url}/retest", json=result, headers=token).json()
        == response.json()
    )
    finished = client.get(f"{STAFF}/cases/{case}").json()
    assert finished["state"] == ("closed" if passed else "fde_queue")
    assert finished["retest"]["passed"] is passed
    assert (
        finished["retest"]["result_message_id"] == response.json()["messages"][-2]["id"]
    )
    assert finished["task_id"] == control.tid
    if not passed:
        continued = act(
            client,
            auth,
            case,
            "accept_handoff",
            engagement_id=control.eid,
            spec=task_payload()["spec"],
        )
        new_task = client.get(f"/api/v1/tasks/{continued['task_id']}").json()
        assert new_task["related_task_id"] == control.tid


def test_candidate_sample_invitation_and_customer_consent(client, auth):
    data = {"adcode": "440106", "sample": True}
    headers = auth | {"Idempotency-Key": "candidate-search"}
    response = client.post(f"{STAFF}/candidate-search", json=data, headers=headers)
    assert response.status_code == 200, response.text
    assert (
        client.post(f"{STAFF}/candidate-search", json=data, headers=headers).json()
        == response.json()
    )
    candidates = response.json()["items"]
    assert len(candidates) == 2
    assert all(
        item["source"] == "sample" and item["reason"] and item["queried_at"]
        for item in candidates
    )
    invitation = candidates[0]["id"]
    invited = client.post(
        f"{STAFF}/candidates/{invitation}/invite", json={}, headers=auth
    )
    assert invited.status_code == 200 and invited.json()["invited_by"] == "founder"
    url, token, conversation = start_case(
        client, customer("希望加供应商筛选", invitation_id=invitation)
    )
    case = conversation["id"]
    send(client, url, token, customer("希望比较页面增加按供应商筛选"))
    act(
        client,
        auth,
        case,
        "handoff",
        status=409,
        title="需求",
        goal="筛选",
        confirmed_facts=[],
        unknowns=[],
    )
    assert client.get(f"{STAFF}/cases/{case}").json()["state"] == "clarifying"
    send(
        client, url, token, customer("希望你们帮我们处理一下", willing_to_continue=True)
    )
    assert client.get(f"{STAFF}/cases/{case}").json()["state"] == "clarifying"
    send(
        client,
        url,
        token,
        customer("希望比较页面增加按供应商筛选", willing_to_continue=True),
    )
    detail = client.get(f"{STAFF}/cases/{case}").json()
    assert (detail["source"], detail["workflow"], detail["state"]) == (
        "invitation",
        "outreach",
        "fde_queue",
    )
    assert detail["invitation_id"] == invitation
