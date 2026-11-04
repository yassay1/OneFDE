from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from pydantic import SecretStr as SettingsSecret
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from onefde.core.security import digest
from onefde.entrypoints.api import create_app
from onefde.modules.engagements import service as services
from tests.support import models
from tests.support.constants import ORIGIN, PASSWORD
from tests.support.factories import (
    ENGAGEMENT,
    create_engagement,
    create_task,
    task_payload,
)


def test_authentication_and_csrf(client, auth):
    assert client.get("/api/v1/auth/session").json()["username"] == "founder"
    assert client.get("/api/v1/auth/session").headers["cache-control"] == "no-store"
    for headers in [
        {},
        {"Origin": ORIGIN},
        {**auth, "Origin": "https://untrusted.example"},
        {**auth, "X-CSRF-Token": "wrong"},
        {**auth, "X-CSRF-Token": ""},
    ]:
        assert (
            client.post(
                "/api/v1/engagements", json=ENGAGEMENT, headers=headers
            ).status_code
            == 403
        )
    assert (
        client.post(
            "/api/v1/engagements",
            content="{}",
            headers={**auth, "Content-Type": "text/plain"},
        ).status_code
        == 400
    )
    old_cookie = client.cookies.get("onefde_dev_session")
    assert (
        client.post(
            "/api/v1/auth/logout", headers={**auth, "Content-Type": "application/json"}
        ).status_code
        == 204
    )
    assert client.get("/api/v1/auth/session").status_code == 401
    client.cookies.set("onefde_dev_session", old_cookie)
    assert client.get("/api/v1/auth/session").status_code == 401


def test_cookie_rotation_and_hash_storage(client, app, auth):
    old = client.cookies.get("onefde_dev_session")
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "founder", "password": PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 200
    assert (
        "HttpOnly" in response.headers["set-cookie"]
        and "SameSite=lax" in response.headers["set-cookie"]
    )
    assert "Domain=" not in response.headers["set-cookie"]
    token = client.cookies.get("onefde_dev_session")
    assert token != old
    with Session(app.state.engine) as db:
        assert db.get(models.AuthSession, digest(old)) is None
        row = db.get(models.AuthSession, digest(token))
        assert row and token not in row.token_hash
    client.cookies.set("onefde_dev_session", old, domain="testserver.local", path="/")
    assert client.get("/api/v1/auth/session").status_code == 401


def test_session_expiry(client, app, auth):
    with Session(app.state.engine) as db:
        row = db.scalar(select(models.AuthSession))
        row.expires_at = models.now() - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/v1/auth/session").status_code == 401


def test_credentials_rotation_revokes_sessions(client, settings, auth):
    changed = settings.model_copy(
        update={
            "owner_password_hash": SettingsSecret(
                PasswordHasher().hash("changed-credentials")
            )
        }
    )
    with TestClient(create_app(changed)) as other:
        other.cookies.update(client.cookies)
        assert other.get("/api/v1/auth/session").status_code == 401


def test_login_origin_invalid_credentials_and_rate_limit(client):
    payload = {"username": "unknown", "password": "wrong-password"}
    assert client.post("/api/v1/auth/login", json=payload).status_code == 403
    for _ in range(10):
        r = client.post("/api/v1/auth/login", json=payload, headers={"Origin": ORIGIN})
        assert r.status_code == 401
        assert "unknown" not in r.text and "wrong-password" not in r.text
    assert (
        client.post(
            "/api/v1/auth/login", json=payload, headers={"Origin": ORIGIN}
        ).status_code
        == 429
    )


def test_unauthenticated_and_missing_resources(client):
    assert client.get("/api/v1/engagements").status_code == 401
    assert client.get(f"/api/v1/tasks/{uuid4()}").status_code == 401


def test_creation_queries_and_app_restart(client, settings, auth):
    engagement = create_engagement(client, auth)
    response = create_task(client, auth, engagement["id"])
    assert response.status_code == 201, response.text
    task = response.json()
    assert task["state"] == "draft" and task["revision"] == task["spec_version"] == 1
    assert (
        task["active_run_id"] is None
        and task["latest_run_id"] is None
        and task["pending_input_count"] == 0
    )
    assert task["owner_role"] == "fde" and task["executor_role"] == "engineering"
    with TestClient(create_app(settings)) as restarted:
        restarted.cookies.update(client.cookies)
        assert (
            restarted.get(f"/api/v1/engagements/{engagement['id']}").json()
            == engagement
        )
        assert restarted.get(f"/api/v1/tasks/{task['id']}").json() == task
        assert restarted.get(f"/api/v1/engagements/{engagement['id']}/tasks").json()[
            "items"
        ] == [task]
        assert restarted.get("/api/v1/engagements").json()["items"] == [engagement]


def test_engagement_and_task_idempotency(client, app, auth):
    engagement = create_engagement(client, auth)
    assert create_engagement(client, auth) == engagement
    response = client.post(
        "/api/v1/engagements",
        json={**ENGAGEMENT, "goal": "different"},
        headers={**auth, "Idempotency-Key": "engagement"},
    )
    assert (
        response.status_code == 409
        and response.json()["code"] == "IDEMPOTENCY_CONFLICT"
    )
    data = task_payload()
    first = create_task(client, auth, engagement["id"], data)
    assert first.status_code == 201
    assert create_task(client, auth, engagement["id"], data).json() == first.json()
    assert (
        create_task(
            client, auth, engagement["id"], {**data, "original_request": "different"}
        ).status_code
        == 409
    )
    # A new HTTP key still respects durable task request/task_key uniqueness.
    assert (
        create_task(client, auth, engagement["id"], data, key="another").status_code
        == 409
    )
    with Session(app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(models.Engagement)) == 1
        assert db.scalar(select(func.count()).select_from(models.Task)) == 1
        assert (
            db.scalar(select(func.count()).select_from(models.IdempotencyRecord)) == 2
        )


@pytest.mark.parametrize("resource", ["engagement", "task"])
def test_concurrent_idempotency_across_sessions(client, app, auth, resource):
    # Different sessions ensure the idempotency lock, not the auth row lock, serializes.
    eid = create_engagement(client, auth)["id"] if resource == "task" else None
    path = f"/api/v1/engagements/{eid}/tasks" if eid else "/api/v1/engagements"
    payload = task_payload() if eid else ENGAGEMENT
    clients = []
    for _ in range(4):
        c = TestClient(app)
        r = c.post(
            "/api/v1/auth/login",
            json={"username": "founder", "password": PASSWORD},
            headers={"Origin": ORIGIN},
        )
        assert r.status_code == 200
        clients.append((c, {**auth, "X-CSRF-Token": r.json()["csrf_token"]}))
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(
                pool.map(
                    lambda pair: pair[0].post(path, json=payload, headers=pair[1]),
                    clients,
                )
            )
        assert [r.status_code for r in results] == [201] * 4
        assert len({r.json()["id"] for r in results}) == 1
    finally:
        for c, _ in clients:
            c.close()


def test_failed_transaction_does_not_leave_business_or_idempotency_row(
    client, app, auth, monkeypatch
):
    real_create = services.create_engagement

    def fail_after_insert(db, data):
        real_create(db, data)
        raise RuntimeError("simulated failure before idempotency commit")

    monkeypatch.setattr(services, "create_engagement", fail_after_insert)
    response = client.post("/api/v1/engagements", json=ENGAGEMENT, headers=auth)
    assert response.status_code == 500
    with Session(app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(models.Engagement)) == 0
        assert (
            db.scalar(select(func.count()).select_from(models.IdempotencyRecord)) == 0
        )
    monkeypatch.setattr(services, "create_engagement", real_create)
    assert (
        client.post("/api/v1/engagements", json=ENGAGEMENT, headers=auth).status_code
        == 201
    )


def test_references_and_unsupported_dependencies(client, auth):
    first, second = (
        create_engagement(client, auth, "first"),
        create_engagement(client, auth, "second"),
    )
    task = create_task(client, auth, first["id"]).json()
    data = task_payload()
    data["related_task_id"] = task["id"]
    assert (
        create_task(client, auth, second["id"], data).json()["code"]
        == "CROSS_ENGAGEMENT_REFERENCE"
    )
    data["related_task_id"] = str(uuid4())
    assert create_task(client, auth, second["id"], data).status_code == 404
    data["related_task_id"] = task["id"]
    data["spec"]["dependencies"] = [
        {"task_id": task["id"], "spec_version": 1, "artifact_ids": []}
    ]
    assert (
        create_task(client, auth, first["id"], data, "deps").json()["code"]
        == "DEPENDENCIES_NOT_SUPPORTED"
    )
    data["spec"]["dependencies"] = []
    assert create_task(client, auth, first["id"], data, "related").status_code == 201
    assert create_task(client, auth, str(uuid4())).status_code == 404
    assert client.get(f"/api/v1/tasks/{uuid4()}").status_code == 404
    assert client.get(f"/api/v1/engagements/{uuid4()}/tasks").status_code == 404


@pytest.mark.parametrize(
    "patch",
    [
        {"title": ""},
        {"goal": "   "},
        {"title": "x" * 201},
        {"is_demo": "true"},
        {"unexpected": "secret"},
    ],
)
def test_input_validation(client, auth, patch):
    response = client.post(
        "/api/v1/engagements", json={**ENGAGEMENT, **patch}, headers=auth
    )
    assert response.status_code == 422
    body = response.json()
    assert {"code", "message", "request_id", "details"} <= body.keys()
    assert body["request_id"] == response.headers["x-request-id"]
    assert "secret" not in response.text


def test_task_role_validation_and_request_errors(client, auth):
    eid = create_engagement(client, auth)["id"]
    data = task_payload()
    data["owner_role"] = "engineering"
    assert create_task(client, auth, eid, data).status_code == 422
    data = task_payload()
    data["spec"]["completion_criteria"] = []
    assert create_task(client, auth, eid, data).status_code == 422
    assert (
        client.post(
            "/api/v1/engagements",
            content="{bad",
            headers={**auth, "Content-Type": "application/json"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/engagements",
            json=ENGAGEMENT,
            headers={k: v for k, v in auth.items() if k != "Idempotency-Key"},
        ).status_code
        == 422
    )
    assert client.get("/api/v1/engagements/not-a-uuid").status_code == 422
    assert client.get("/api/v1/engagements?cursor=invalid").status_code == 422
    assert client.get("/api/v1/engagements?limit=101").status_code == 422
    assert client.get("/missing").json()["code"] == "HTTP_ERROR"


def test_stable_pagination(client, app, auth):
    ids = [create_engagement(client, auth, f"page-{i}")["id"] for i in range(4)]
    # All timestamps equal: UUID tie-breaker still returns each record once.
    with app.state.engine.begin() as conn:
        conn.execute(text("UPDATE engagements SET created_at = '2026-11-04T00:00:00Z'"))
    seen, cursor = [], None
    while True:
        page = client.get(
            "/api/v1/engagements",
            params={"limit": 1, **({"cursor": cursor} if cursor else {})},
        ).json()
        seen.extend(item["id"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == sorted(ids)


def test_task_pagination_scope_and_request_decomposition(client, auth):
    first = create_engagement(client, auth, "first")["id"]
    second = create_engagement(client, auth, "second")["id"]
    data = task_payload()
    t1 = create_task(client, auth, first, data, "one").json()
    data["task_key"] = "another-task-in-same-request"
    t2 = create_task(client, auth, first, data, "two").json()
    assert t1["id"] != t2["id"]
    page1 = client.get(f"/api/v1/engagements/{first}/tasks?limit=1").json()
    cursor = page1["next_cursor"]
    page2 = client.get(
        f"/api/v1/engagements/{first}/tasks", params={"limit": 1, "cursor": cursor}
    ).json()
    assert {page1["items"][0]["id"], page2["items"][0]["id"]} == {t1["id"], t2["id"]}
    assert page2["next_cursor"] is None
    assert (
        client.get(
            f"/api/v1/engagements/{second}/tasks", params={"cursor": cursor}
        ).status_code
        == 422
    )
    assert client.get(f"/api/v1/engagements/{second}/tasks").json()["items"] == []


def test_database_unavailable_has_sanitized_error(client, app, monkeypatch):
    from sqlalchemy.exc import OperationalError

    def unavailable(*args, **kwargs):
        raise OperationalError(
            "secret database URL", {}, Exception("secret credentials")
        )

    monkeypatch.setattr(app.state.engine, "connect", unavailable)
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "founder", "password": PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_UNAVAILABLE"
    assert "secret" not in response.text
    assert response.json()["request_id"] == response.headers["x-request-id"]


def test_idempotency_expiry_and_task_durable_uniqueness(client, app, auth):
    eid = create_engagement(client, auth)["id"]
    data = task_payload()
    assert create_task(client, auth, eid, data).status_code == 201
    with Session(app.state.engine) as db:
        for record in db.scalars(select(models.IdempotencyRecord)):
            record.expires_at = models.now() - timedelta(seconds=1)
        db.commit()
    assert create_task(client, auth, eid, data).status_code == 409
    assert create_engagement(client, auth)["id"] != eid


def test_secure_cookie_and_configuration(settings):
    from pydantic import ValidationError

    from onefde.core.config import Settings

    values = settings.model_dump()
    with pytest.raises(ValidationError):
        Settings(**{**values, "environment": "production"})
    with pytest.raises(ValidationError):
        Settings(**{**values, "database_url": "sqlite:///ignored"})
    secure = Settings(
        **{
            **values,
            "environment": "production",
            "cookie_secure": True,
            "trusted_origin": "https://onefde.example",
        }
    )
    with TestClient(create_app(secure), base_url="https://onefde.example") as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "founder", "password": PASSWORD},
            headers={"Origin": "https://onefde.example"},
        )
        assert response.status_code == 200
        cookie = response.headers["set-cookie"]
        assert (
            cookie.startswith("__Host-onefde_session=")
            and "Secure" in cookie
            and "Path=/" in cookie
        )
        assert client.get("/api/v1/auth/session").status_code == 200
