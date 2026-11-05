"""P2 platform control path: FDE tools → deterministic Engineering submit → modify → accept.

Uses PostgreSQL + TestClient. Does not call a model. Product checks remain in
products/demo-supplier-quotes/check.mjs; this test proves Task/Input/Run/Review
wiring for the quote engagement story.
"""

from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from onefde.modules.tasks import schemas as s
from onefde.modules.tasks import service as tasks
from tests.support.factories import create_engagement

PRODUCT_CHECK = (
    Path(__file__).resolve().parents[3]
    / "docs/operations/evidence/p2-quote-product-check.json"
)


QUOTE_SPEC = {
    "title": "模拟报价比较工具",
    "objective": "按 P0 CSV 规则交付可操作比较与导出",
    "scope": "demo-supplier-quotes；CSV only；不含换算/Excel/采购",
    "inputs": [
        "engagements/demo-supplier-quotes/samples/",
        "R01—R05 与 P0 八列字段",
    ],
    "confirmed_rules": ["R01", "R02", "R03", "R04", "R05"],
    "completion_criteria": [
        "S01/S02/S03/S05 确定性检查通过",
        "客户产品可导入 CSV 并导出结果",
        "不自动选定供应商",
    ],
    "dependencies": [],
    "capability_versions": [],
}


def _fde(client, auth, eid, tool, arguments, key):
    response = client.post(
        f"/api/v1/engagements/{eid}/fde/tools",
        json={"tool": tool, "arguments": arguments},
        headers={**auth, "Idempotency-Key": key},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _finish_submitted(app, run_id, summary, blob: bytes):
    digest = sha256(blob).hexdigest()
    result = s.RunResult(
        state="completed",
        outcome="submitted",
        summary=summary,
        stopped=True,
        artifacts=[
            {
                "name": "quote-product-check.json",
                "kind": "check-evidence",
                "sha256": digest,
                "size_bytes": len(blob),
            }
        ],
    )
    with Session(app.state.engine) as db:
        tasks.mark_run_started(db, UUID(run_id))
        db.commit()
    with Session(app.state.engine) as db:
        tasks.record_run_result(db, UUID(run_id), result)
        db.commit()
    return digest


def test_p2_quote_delivery_via_fde_tools(client, auth, app, profile):
    assert PRODUCT_CHECK.is_file(), "P2 product check evidence must exist"
    blob = PRODUCT_CHECK.read_bytes()

    engagement = create_engagement(
        client,
        auth,
        key="p2-quote-eng",
    )
    # Align title/goal with case (factory uses generic demo payload).
    eid = engagement["id"]

    delivery = client.get(f"/api/v1/engagements/{eid}/delivery", headers=auth)
    assert delivery.status_code == 200
    assert delivery.json()["tasks"] == []

    created = _fde(
        client,
        auth,
        eid,
        "create_task",
        {
            "request_id": str(uuid4()),
            "task_key": "demo-supplier-quotes-delivery",
            "original_request": "交付模拟水果店报价比较工具，并支持一次范围内修改",
            "spec": QUOTE_SPEC,
        },
        key="p2-create",
    )
    task = created["result"]["task"]
    tid = task["id"]
    assert task["owner_role"] == "fde"
    assert task["state"] == "draft"

    # Clarify unknown before first engineering pass.
    saved = _fde(
        client,
        auth,
        eid,
        "save_input",
        {
            "task_id": tid,
            "expected_revision": task["revision"],
            "kind": "clarification",
            "text": "P0 仅 kg 可比；box 缺净重一律待核对，不做换算。",
            "evidence_artifact_ids": [],
        },
        key="p2-clarify",
    )
    clarification = saved["result"]["input"]
    task = saved["result"]["task"]
    adopted = _fde(
        client,
        auth,
        eid,
        "adopt_inputs",
        {
            "task_id": tid,
            "expected_revision": task["revision"],
            "apply_ids": [clarification["id"]],
            "reject_ids": [],
            "reason": "采用 P0 可比边界",
            "spec": QUOTE_SPEC
            | {
                "inputs": QUOTE_SPEC["inputs"] + ["澄清：P0 不做 box↔kg 换算"],
            },
        },
        key="p2-adopt-clarify",
    )
    task = adopted["result"]["task"]
    assert task["spec_version"] >= 2

    queued = _fde(
        client,
        auth,
        eid,
        "request_execution",
        {
            "task_id": tid,
            "command": "queue",
            "expected_revision": task["revision"],
            "expected_run_id": None,
        },
        key="p2-queue-1",
    )
    task = queued["result"]["task"]
    started = _fde(
        client,
        auth,
        eid,
        "request_execution",
        {
            "task_id": tid,
            "command": "start",
            "expected_revision": task["revision"],
            "expected_run_id": None,
            "model_profile_revision_id": profile,
        },
        key="p2-start-1",
    )
    run1 = started["result"]["run"]
    digest1 = _finish_submitted(
        app,
        run1["id"],
        "SIMULATED engineering submit: quote product v1.0 + S01—S05 checks",
        blob,
    )
    task = _fde(
        client, auth, eid, "get_task", {"task_id": tid}, key="p2-get-1"
    )["result"]["task"]
    assert task["state"] == "review"

    arts = client.get(f"/api/v1/runs/{run1['id']}/artifacts", headers=auth).json()[
        "items"
    ]
    accepted = _fde(
        client,
        auth,
        eid,
        "propose_review",
        {
            "task_id": tid,
            "expected_revision": task["revision"],
            "run_id": run1["id"],
            "task_spec_version": task["spec_version"],
            "artifact_ids": [arts[0]["id"]],
            "verdict": "request_changes",
            "reason": "同 Task 修改：待核对项需单独导出 CSV",
            "check_evidence": [],
        },
        key="p2-request-changes",
    )
    task = accepted["result"]["task"]
    assert task["state"] == "draft"

    inputs = client.get(f"/api/v1/tasks/{tid}/inputs", headers=auth).json()["items"]
    change = next(i for i in inputs if i["kind"] == "change_request" and i["status"] == "pending")
    modified_spec = QUOTE_SPEC | {
        "scope": QUOTE_SPEC["scope"] + "；含待核对单独导出",
        "completion_criteria": QUOTE_SPEC["completion_criteria"]
        + ["待核对可单独导出 CSV"],
    }
    task = _fde(
        client,
        auth,
        eid,
        "adopt_inputs",
        {
            "task_id": tid,
            "expected_revision": task["revision"],
            "apply_ids": [change["id"]],
            "reject_ids": [],
            "reason": "采用待核对导出修改",
            "spec": modified_spec,
        },
        key="p2-adopt-change",
    )["result"]["task"]

    task = _fde(
        client,
        auth,
        eid,
        "request_execution",
        {
            "task_id": tid,
            "command": "queue",
            "expected_revision": task["revision"],
            "expected_run_id": None,
        },
        key="p2-queue-2",
    )["result"]["task"]
    run2 = _fde(
        client,
        auth,
        eid,
        "request_execution",
        {
            "task_id": tid,
            "command": "start",
            "expected_revision": task["revision"],
            "expected_run_id": None,
            "model_profile_revision_id": profile,
        },
        key="p2-start-2",
    )["result"]["run"]
    digest2 = _finish_submitted(
        app,
        run2["id"],
        "SIMULATED engineering submit: quote product v1.1 pending export",
        blob + b"\nv1.1",
    )
    task = _fde(
        client, auth, eid, "get_task", {"task_id": tid}, key="p2-get-2"
    )["result"]["task"]
    arts2 = client.get(f"/api/v1/runs/{run2['id']}/artifacts", headers=auth).json()[
        "items"
    ]
    final = _fde(
        client,
        auth,
        eid,
        "propose_review",
        {
            "task_id": tid,
            "expected_revision": task["revision"],
            "run_id": run2["id"],
            "task_spec_version": task["spec_version"],
            "artifact_ids": [arts2[0]["id"]],
            "verdict": "accept",
            "reason": "接受 v1.1 固定提交",
            "check_evidence": [
                "products/demo-supplier-quotes check.mjs S01—S05",
                "CHANGELOG v1.1 pending export",
            ],
        },
        key="p2-accept",
    )
    task = final["result"]["task"]
    assert task["state"] == "succeeded"
    assert digest1 != digest2

    detail = client.get(f"/api/v1/engagements/{eid}/delivery", headers=auth).json()
    assert len(detail["tasks"]) == 1
    assert detail["tasks"][0]["state"] == "succeeded"
    assert detail["fixed_version_hint"]

    # Cross-project isolation still holds after delivery.
    other = create_engagement(client, auth, key="p2-other")["id"]
    leaked = client.post(
        f"/api/v1/engagements/{other}/fde/tools",
        json={"tool": "get_task", "arguments": {"task_id": tid}},
        headers={**auth, "Idempotency-Key": "p2-leak"},
    )
    assert leaked.status_code == 403
    assert leaked.json()["code"] == "FDE_SCOPE_DENIED"
