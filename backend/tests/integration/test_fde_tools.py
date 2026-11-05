"""P1 thin FDE controlled tools and delivery detail over real PostgreSQL."""

from uuid import uuid4

from tests.support.factories import create_engagement, task_payload


def _invoke(client, auth, engagement_id, tool, arguments, key):
    return client.post(
        f"/api/v1/engagements/{engagement_id}/fde/tools",
        json={"tool": tool, "arguments": arguments},
        headers={**auth, "Idempotency-Key": key},
    )


def test_fde_tools_create_task_and_delivery(client, auth):
    engagement = create_engagement(client, auth, key="fde-eng")
    eid = engagement["id"]

    empty = client.get(f"/api/v1/engagements/{eid}/delivery", headers=auth)
    assert empty.status_code == 200, empty.text
    body = empty.json()
    assert body["engagement"]["id"] == eid
    assert body["engagement"]["is_demo"] is True
    assert body["tasks"] == []
    assert "模拟" in body["sources_note"]

    created = _invoke(
        client,
        auth,
        eid,
        "create_task",
        {
            "request_id": str(uuid4()),
            "task_key": "quote-clarify",
            "original_request": "按 P0 CSV 澄清可比条件",
            "spec": task_payload()["spec"]
            | {
                "title": "报价澄清",
                "objective": "形成有范围和检查条件的 Task",
                "scope": "demo-supplier-quotes P0 样例",
                "confirmed_rules": ["R01", "R05"],
                "completion_criteria": ["规格含完成条件", "可请求工程执行"],
            },
        },
        key="fde-create",
    )
    assert created.status_code == 200, created.text
    result = created.json()
    assert result["tool"] == "create_task"
    assert result["role_revision"].startswith("fde-role-")
    assert result["engagement_id"] == eid
    task = result["result"]["task"]
    assert task["owner_role"] == "fde"
    assert task["executor_role"] == "engineering"
    assert task["state"] == "draft"
    tid = task["id"]

    saved = _invoke(
        client,
        auth,
        eid,
        "save_input",
        {
            "task_id": tid,
            "expected_revision": task["revision"],
            "kind": "clarification",
            "text": "盒装净重是否提供？",
            "evidence_artifact_ids": [],
        },
        key="fde-save",
    )
    assert saved.status_code == 200, saved.text
    pending = saved.json()["result"]["input"]
    task = saved.json()["result"]["task"]
    assert pending["status"] == "pending"

    adopted = _invoke(
        client,
        auth,
        eid,
        "adopt_inputs",
        {
            "task_id": tid,
            "expected_revision": task["revision"],
            "apply_ids": [pending["id"]],
            "reject_ids": [],
            "reason": "采用澄清并写入规格",
            "spec": task["spec"]
            | {
                "inputs": ["P0 CSV", "盒装净重待核对"],
                "completion_criteria": ["缺净重标记待核对", "不自动定供应商"],
            },
        },
        key="fde-adopt",
    )
    assert adopted.status_code == 200, adopted.text
    task = adopted.json()["result"]["task"]
    assert task["spec_version"] >= 2
    assert task["pending_input_count"] == 0

    delivery = client.get(f"/api/v1/engagements/{eid}/delivery", headers=auth)
    assert delivery.status_code == 200
    detail = delivery.json()
    assert len(detail["tasks"]) == 1
    assert detail["tasks"][0]["id"] == tid
    assert detail["scheme_summary"]


def test_fde_rejects_forbidden_and_cross_engagement(client, auth):
    first = create_engagement(client, auth, key="fde-a")
    second = create_engagement(client, auth, key="fde-b")
    created = _invoke(
        client,
        auth,
        first["id"],
        "create_task",
        {
            "request_id": str(uuid4()),
            "task_key": "scoped",
            "original_request": "范围检查",
            "spec": task_payload()["spec"],
        },
        key="fde-scoped",
    )
    tid = created.json()["result"]["task"]["id"]

    denied = _invoke(
        client,
        auth,
        first["id"],
        "claim_job",
        {},
        key="fde-deny",
    )
    # Unknown tool name fails schema validation before handler.
    assert denied.status_code == 422, denied.text

    leaked = _invoke(
        client,
        auth,
        second["id"],
        "get_task",
        {"task_id": tid},
        key="fde-leak",
    )
    assert leaked.status_code == 403, leaked.text
    assert leaked.json()["code"] == "FDE_SCOPE_DENIED"

    read = _invoke(
        client,
        auth,
        first["id"],
        "read_project",
        {},
        key="fde-read",
    )
    assert read.status_code == 200, read.text
    assert read.json()["result"]["engagement"]["id"] == first["id"]
