from uuid import uuid4

from sqlalchemy.orm import Session

from onefde.modules.business import models as business
from onefde.modules.fde import agent_schemas, agent_work
from tests.support.factories import create_engagement


def test_work_history_pages_and_scoped_deep_link(client, auth, app):
    project = create_engagement(client, auth, key="history-project")
    other = create_engagement(client, auth, key="other-project")
    with Session(app.state.engine) as db, db.begin():
        ids = [
            agent_work.start(
                db, project["id"], agent_schemas.StartWork(goal=f"目标 {i}"), "founder"
            )["id"]
            for i in range(53)
        ]
    base = f"/api/v1/engagements/{project['id']}/fde"
    first = client.get(f"{base}/work-history?limit=50")
    assert first.status_code == 200
    body = first.json()
    assert len(body["items"]) == 50 and body["next_cursor"]
    second = client.get(f"{base}/work-history", params={"cursor": body["next_cursor"]})
    assert second.status_code == 200
    all_ids = [w["id"] for w in body["items"] + second.json()["items"]]
    assert len(set(all_ids)) == 53
    deep = client.get(f"{base}/work/{ids[-1]}")
    assert deep.status_code == 200 and deep.json()["created_at"]
    assert (
        client.get(f"/api/v1/engagements/{other['id']}/fde/work/{ids[-1]}").status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/engagements/{other['id']}/fde/work-history",
            params={"cursor": body["next_cursor"]},
        ).status_code
        == 422
    )


def test_case_filters_apply_before_paging_and_cursor_is_scoped(client, auth, app):
    with Session(app.state.engine) as db, db.begin():
        for i in range(5):
            db.add(
                business.Case(
                    id=uuid4(),
                    token_digest="f" * 64,
                    source="quote_page",
                    workflow="inquiry",
                    state="founder_queue" if i % 2 == 0 else "closed",
                    owner="founder" if i % 2 == 0 else "business",
                    next_step="测试过滤",
                )
            )
    first = client.get(
        "/api/v1/business/cases?state=founder_queue&owner=founder&limit=2"
    ).json()
    assert len(first["items"]) == 2 and all(
        i["state"] == "founder_queue" for i in first["items"]
    )
    second = client.get(
        "/api/v1/business/cases",
        params={
            "state": "founder_queue",
            "owner": "founder",
            "cursor": first["next_cursor"],
        },
    )
    assert second.status_code == 200 and len(second.json()["items"]) == 1
    assert (
        client.get(
            "/api/v1/business/cases",
            params={"state": "closed", "cursor": first["next_cursor"]},
        ).status_code
        == 422
    )
    assert client.get("/api/v1/business/cases?state=not-a-state").status_code == 422
