"""P3 Knowledge tools: search, permission denial, business handoff."""

from pathlib import Path

import onefde.modules.knowledge.tools as knowledge_tools
from onefde.modules.knowledge import catalog


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
    assert "fixture-restricted" not in denied.text or denied.json()["code"] == "NOT_FOUND"

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
