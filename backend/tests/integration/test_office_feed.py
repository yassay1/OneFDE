"""G6 Office actionable / activity feeds — derived views, no notification store."""

from uuid import uuid4

from sqlalchemy.orm import Session

from onefde.modules.tasks import models
from tests.support.factories import create_engagement, create_task, task_payload


def test_review_activity_preserves_project_context(client, auth, app):
    engagement = create_engagement(client, auth, key=str(uuid4()))
    task = create_task(client, auth, engagement["id"], key=str(uuid4())).json()
    with Session(app.state.engine) as db, db.begin():
        run = models.Run(
            task_id=task["id"],
            task_spec_version=1,
            attempt=1,
            state="completed",
            outcome="submitted",
            applied_input_ids=[],
            snapshot={},
        )
        db.add(run)
        db.flush()
        review = models.TaskReview(
            task_id=task["id"],
            run_id=run.id,
            task_spec_version=1,
            artifact_ids=[str(uuid4())],
            verdict="accept",
            reason="测试项目上下文",
            check_evidence=["仅用于动态投影测试的固定依据"],
            reviewer="founder",
        )
        db.add(review)
        db.flush()
        review_id = str(review.id)
    items = client.get("/api/v1/office/activity?limit=100").json()["items"]
    item = next(i for i in items if i["id"] == f"review:{review_id}")
    assert item["engagement_id"] == engagement["id"]
    assert f"project={engagement['id']}" in item["href"]
    assert item["title"] == "评审 · accept"


def test_draft_with_pending_input_is_actionable(client, auth):
    engagement = create_engagement(client, auth, key=str(uuid4()))
    task = create_task(client, auth, engagement["id"], key=str(uuid4())).json()
    response = client.post(
        f"/api/v1/tasks/{task['id']}/inputs",
        json={
            "expected_revision": task["revision"],
            "kind": "clarification",
            "text": "需要所有者决定的范围澄清",
            "evidence_artifact_ids": [],
        },
        headers={**auth, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201, response.text
    items = client.get("/api/v1/office/actionable?limit=100").json()["items"]
    item = next(item for item in items if item["object_id"] == task["id"])
    assert item["state"] == "draft"
    assert "待处理输入 1 条" in item["reason"]


def test_office_actionable_and_activity_cursor(client, auth):
    engagement = create_engagement(client, auth, key=str(uuid4()))
    created = create_task(
        client,
        auth,
        engagement["id"],
        data={**task_payload(), "task_key": "office-feed"},
        key=str(uuid4()),
    )
    assert created.status_code == 201, created.text
    task = created.json()
    queued = client.post(
        f"/api/v1/tasks/{task['id']}/actions",
        json={
            "command": "queue",
            "expected_revision": task["revision"],
            "expected_run_id": None,
        },
        headers={**auth, "Idempotency-Key": str(uuid4())},
    )
    assert queued.status_code == 202, queued.text

    actionable = client.get("/api/v1/office/actionable?limit=20")
    assert actionable.status_code == 200, actionable.text
    body = actionable.json()
    assert "totalCount" not in body and "total_count" not in body
    assert body["coverage"]["description"]
    assert body["read_at"]
    ids = {item["id"] for item in body["items"]}
    assert f"task:{task['id']}" in ids
    task_item = next(item for item in body["items"] if item["object_id"] == task["id"])
    assert task_item["kind"] == "task"
    assert task_item["role"] == "engineering"
    assert task_item["engagement_id"] == engagement["id"]
    assert f"project={engagement['id']}" in task_item["href"]

    cancelled = client.post(
        f"/api/v1/tasks/{task['id']}/actions",
        json={
            "command": "cancel",
            "expected_revision": queued.json()["task"]["revision"],
            "expected_run_id": None,
        },
        headers={**auth, "Idempotency-Key": str(uuid4())},
    )
    assert cancelled.status_code in {200, 202}, cancelled.text
    after = client.get("/api/v1/office/actionable?limit=50").json()
    assert f"task:{task['id']}" not in {item["id"] for item in after["items"]}

    activity = client.get("/api/v1/office/activity?limit=5")
    assert activity.status_code == 200, activity.text
    page = activity.json()
    assert isinstance(page["items"], list)
    assert page["coverage"]["scanned_runs"] >= 0
    if page["next_cursor"]:
        more = client.get(
            f"/api/v1/office/activity?limit=5&cursor={page['next_cursor']}"
        )
        assert more.status_code == 200, more.text
        first_ids = {item["id"] for item in page["items"]}
        second_ids = {item["id"] for item in more.json()["items"]}
        assert first_ids.isdisjoint(second_ids) or not second_ids

    bad = client.get("/api/v1/office/actionable?cursor=not-a-cursor")
    assert bad.status_code == 422
