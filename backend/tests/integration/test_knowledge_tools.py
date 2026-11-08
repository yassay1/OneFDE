"""P3 Knowledge tools: search, permission denial, business handoff."""

from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

import onefde.modules.knowledge.tools as knowledge_tools
from onefde.modules.knowledge import catalog
from onefde.modules.tasks.models import Run, Task, TaskReview
from tests.support.factories import create_engagement, create_task


def _invoke(client, auth, payload, key):
    return client.post(
        "/api/v1/knowledge/tools",
        json=payload,
        headers={**auth, "Idempotency-Key": key},
    )


def test_knowledge_search_get_and_permission(client, auth, tmp_path, monkeypatch):
    catalog.clear_cache()
    monkeypatch.setattr(
        knowledge_tools, "handoff_root", lambda: Path(tmp_path) / "handoffs"
    )

    found = _invoke(
        client,
        auth,
        {
            "tool": "search_assets",
            "caller_role": "fde",
            "purpose": "delivery",
            "arguments": {"query": "报价 CSV"},
        },
        key="k-search",
    )
    assert found.status_code == 200, found.text
    ids = {i["id"] for i in found.json()["result"]["items"]}
    assert "fresh-quote-compare-csv" in ids
    assert "fixture-restricted-supplier-notes" not in ids

    public = _invoke(
        client,
        auth,
        {
            "tool": "search_assets",
            "caller_role": "business",
            "purpose": "public_marketing",
            "arguments": {"query": "报价"},
        },
        key="k-public",
    )
    assert public.status_code == 200, public.text
    item = next(
        i
        for i in public.json()["result"]["items"]
        if i["id"] == "fresh-quote-compare-csv"
    )
    assert "public_summary" in item
    assert "implementation_ref" not in item

    denied = _invoke(
        client,
        auth,
        {
            "tool": "get_asset",
            "caller_role": "business",
            "purpose": "public_marketing",
            "arguments": {"asset_id": "fixture-restricted-supplier-notes"},
        },
        key="k-deny",
    )
    assert denied.status_code == 404, denied.text
    assert "RESTRICTED_BODY" not in denied.text
    assert (
        "fixture-restricted" not in denied.text or denied.json()["code"] == "NOT_FOUND"
    )

    got = _invoke(
        client,
        auth,
        {
            "tool": "get_asset",
            "caller_role": "engineering",
            "purpose": "delivery",
            "arguments": {"asset_id": "fresh-quote-compare-csv"},
        },
        key="k-get",
    )
    assert got.status_code == 200, got.text
    assert got.json()["result"]["asset"]["version"] == "1.1.0"

    bad_role = _invoke(
        client,
        auth,
        {
            "tool": "record_business_handoff",
            "caller_role": "engineering",
            "purpose": "delivery",
            "arguments": {
                "title": "不应成功",
                "goal": "x",
                "sources": ["y"],
                "is_demo": True,
            },
        },
        key="k-eng-handoff",
    )
    assert bad_role.status_code == 403
    assert bad_role.json()["code"] == "KNOWLEDGE_ROLE_DENIED"

    handoff = _invoke(
        client,
        auth,
        {
            "tool": "record_business_handoff",
            "caller_role": "business",
            "purpose": "delivery",
            "arguments": {
                "title": "模拟门店报价需求交接",
                "goal": "整理可比报价并标待核对",
                "sources": [
                    "engagements/demo-supplier-quotes/brief.md",
                    "capability fresh-quote-compare-csv@1.1.0",
                ],
                "unknowns": ["换算表未确认"],
                "is_demo": True,
                "notes": "不承诺价格；不派工程",
            },
        },
        key="k-handoff",
    )
    assert handoff.status_code == 200, handoff.text
    meta = handoff.json()["result"]
    assert meta["dispatched_engineering"] is False
    assert meta["is_demo"] is True
    assert (Path(tmp_path) / "handoffs" / f"{meta['id']}.md").is_file()


def test_delivery_feedback_requires_acceptance_and_stays_internal(
    client, auth, app, tmp_path, monkeypatch
):
    library = tmp_path / "library"
    library.mkdir()
    catalog.clear_cache()
    monkeypatch.setattr(catalog, "library_root", lambda: library)
    monkeypatch.setattr(catalog, "repo_root", lambda: tmp_path)
    project = create_engagement(client, auth, key="feedback")
    created = create_task(client, auth, project["id"], key="feedback-task")
    assert created.status_code == 201, created.text
    task = created.json()
    arguments = {
        "task_id": task["id"],
        "engagement_id": project["id"],
        "summary": "模拟报价比较只覆盖同口径公斤价，运费仍待核对。",
        "sources": ["task review"],
    }
    denied = _invoke(
        client,
        auth,
        {
            "tool": "record_delivery_feedback",
            "caller_role": "fde",
            "purpose": "delivery",
            "arguments": arguments,
        },
        key="feedback-early",
    )
    assert denied.status_code == 409, denied.text
    assert denied.json()["code"] == "KNOWLEDGE_FEEDBACK_UNVERIFIED"
    with Session(app.state.engine) as db, db.begin():
        row = db.get(Task, UUID(task["id"]))
        run = Run(
            task_id=row.id,
            task_spec_version=row.spec_version,
            attempt=1,
            state="completed",
            outcome="submitted",
            applied_input_ids=[],
            snapshot={"actor": "founder"},
        )
        db.add(run)
        db.flush()
        row.state = "succeeded"
        row.latest_run_id = run.id
        db.add(
            TaskReview(
                task_id=row.id,
                run_id=run.id,
                task_spec_version=row.spec_version,
                artifact_ids=[str(uuid4())],
                verdict="accept",
                reason="固定检查通过",
                check_evidence=["sample check passed"],
                reviewer="founder",
            )
        )
    recorded = _invoke(
        client,
        auth,
        {
            "tool": "record_delivery_feedback",
            "caller_role": "fde",
            "purpose": "delivery",
            "arguments": arguments,
        },
        key="feedback-ok",
    )
    assert recorded.status_code == 200, recorded.text
    asset_id = recorded.json()["result"]["id"]
    assert (library / "candidates" / asset_id / "manifest.json").is_file()
    catalog.clear_cache()
    visible = _invoke(
        client,
        auth,
        {
            "tool": "search_assets",
            "caller_role": "fde",
            "purpose": "delivery",
            "arguments": {"query": "候选"},
        },
        key="feedback-see",
    )
    assert asset_id in {item["id"] for item in visible.json()["result"]["items"]}
    hidden = _invoke(
        client,
        auth,
        {
            "tool": "search_assets",
            "caller_role": "business",
            "purpose": "public_marketing",
            "arguments": {"query": "候选"},
        },
        key="feedback-public",
    )
    assert hidden.status_code == 200, hidden.text
    assert asset_id not in {item["id"] for item in hidden.json()["result"]["items"]}
    catalog.clear_cache()
