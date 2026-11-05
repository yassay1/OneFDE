"""PostgreSQL control tests. All runtime results/artifacts are deterministic fixtures."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from onefde.core.errors import ApiException
from onefde.entrypoints.api import create_app
from onefde.modules.tasks import events
from onefde.modules.tasks import schemas as s
from onefde.modules.tasks import service as tasks
from onefde.modules.tasks.commands.runs import trusted_prior_source
from tests.support import models as m
from tests.support.constants import ORIGIN, PASSWORD
from tests.support.factories import create_task


def test_three_runs_answers_changes_and_acceptance(control, settings):
    c = control
    first = c.start()
    c.claim(first)
    c.finish(first, outcome="needs_input")
    task = c.get()
    assert task["state"] == "waiting_input" and task["active_run_id"] is None
    question = c.client.get(f"/api/v1/tasks/{c.tid}/inputs").json()["items"][0]
    assert question["origin_run_id"] == first["id"] and question["author"].startswith(
        "engineering:run:"
    )
    answer = c.input("answer", reply_to_input_id=question["id"])["input"]
    before = c.get()
    adopted = c.adopt([answer["id"]])
    assert (
        adopted["spec_version"] == 2 and adopted["revision"] == before["revision"] + 1
    )
    assert adopted["state"] == "waiting_input" and adopted["pending_input_count"] == 0
    inputs = c.client.get(f"/api/v1/tasks/{c.tid}/inputs").json()["items"]
    assert [i["status"] for i in inputs] == ["applied", "applied"]
    assert inputs[0]["resolved_by_input_id"] == answer["id"]
    assert all(
        i["processing_reason"] == "明确处理模拟输入" and i["processed_by"] == "founder"
        for i in inputs
    )
    second = c.action("continue", expected_run_id=first["id"])["run"]
    assert second["id"] != first["id"] and second["attempt"] == 2
    assert set(second["applied_input_ids"]) == {question["id"], answer["id"]}
    c.claim(second)
    c.finish(second)
    assert c.get()["state"] == "review"  # Not business success.
    response = c.review(second, "request_changes")
    assert (
        response["task"]["state"] == "draft"
        and response["task"]["pending_input_count"] == 1
    )
    changes = c.client.get(f"/api/v1/tasks/{c.tid}/inputs").json()["items"][-1]
    spec = c.get()["spec"] | {"scope": "SIMULATED revised scope"}
    assert c.adopt([changes["id"]], spec=spec)["spec_version"] == 3
    third = c.start()
    c.claim(third)
    c.finish(third)
    response = c.review(third)
    assert response["task"]["state"] == "succeeded"
    versions = c.client.get(f"/api/v1/tasks/{c.tid}/versions").json()["items"]
    assert [v["spec_version"] for v in versions] == [1, 2, 3]
    assert versions[0]["spec"]["scope"] != versions[2]["spec"]["scope"]
    runs = c.client.get(f"/api/v1/tasks/{c.tid}/runs").json()["items"]
    assert [r["attempt"] for r in runs] == [1, 2, 3]
    reviews = c.client.get(f"/api/v1/tasks/{c.tid}/reviews").json()["items"]
    assert [r["verdict"] for r in reviews] == ["request_changes", "accept"]
    events = c.client.get(f"/api/v1/tasks/{c.tid}/events?limit=100").json()["items"]
    assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))
    assert c.input(status=409)["code"] == "TASK_CLOSED"
    with Session(c.app.state.engine) as db:
        snapshot = db.get(m.Run, UUID(first["id"])).snapshot
        assert snapshot["inputs"] == [] and snapshot["spec"] != spec
        assert list(db.scalars(select(m.DispatchJob.state))) == ["completed"] * 3
    with TestClient(create_app(settings)) as restarted:
        restarted.cookies.update(c.client.cookies)
        assert restarted.get(f"/api/v1/tasks/{c.tid}").json() == response["task"]
        assert (
            restarted.get(f"/api/v1/tasks/{c.tid}/reviews").json()["items"] == reviews
        )


def test_pending_input_never_changes_running_snapshot(control):
    c = control
    run = c.start()
    c.claim(run)
    original = c.get()
    change = c.input("change_request")["input"]
    assert c.get()["spec_version"] == original["spec_version"]
    assert (
        c.adopt([change["id"]], spec=original["spec"], status=409)["code"]
        == "RUN_NOT_STOPPED"
    )
    c.write(
        "",
        {"expected_revision": c.get()["revision"], "spec": original["spec"]},
        409,
        method="patch",
    )
    c.finish(run)
    assert c.get()["state"] == "draft" and c.get()["pending_input_count"] == 1
    assert c.review(run, status=409)["code"] == "INVALID_TRANSITION"
    version = c.get()["spec_version"]
    c.adopt(reject=[change["id"]])
    assert c.get()["spec_version"] == version
    next_run = c.start()
    assert change["id"] not in next_run["applied_input_ids"]
    with Session(c.app.state.engine) as db:
        assert db.get(m.Run, UUID(run["id"])).snapshot["inputs"] == []


def test_spec_version_and_input_decisions_idempotent_before_revision(control):
    c = control
    data = {"expected_revision": 1, "spec": c.get()["spec"] | {"title": "version two"}}
    first = c.write("", data, key="spec", method="patch")
    assert first["revision"] == first["spec_version"] == 2
    assert c.write("", data, key="spec", method="patch") == first
    assert c.write("", data, status=409, method="patch")["code"] == "REVISION_CONFLICT"
    saved = c.input("change_request")["input"]
    assert c.adopt([saved["id"]], status=409)["code"] == "SPEC_REQUIRED"
    original = c.get()
    c.adopt(reject=[saved["id"]])
    assert (
        c.get()["revision"] == original["revision"] + 1 and c.get()["spec_version"] == 2
    )
    assert (
        c.adopt([saved["id"]], spec=c.get()["spec"], status=409)["code"]
        == "INPUT_SCOPE_CONFLICT"
    )
    assert (
        c.client.get(f"/api/v1/tasks/{c.tid}/versions/1").json()["spec"]["title"]
        != "version two"
    )


def test_reply_scope_and_processing_validation(control):
    c = control
    q = c.input("question")["input"]
    assert c.adopt([q["id"]], status=409)["code"] == "QUESTION_REQUIRES_ANSWER"
    other = create_task(c.client, c.auth, c.eid, key="other").json()["id"]
    path = f"/api/v1/tasks/{other}/inputs"
    body = {
        "expected_revision": 1,
        "kind": "answer",
        "text": "answer",
        "evidence_artifact_ids": [],
        "reply_to_input_id": q["id"],
    }
    r = c.client.post(path, json=body, headers=c.auth)
    assert r.status_code == 409 and r.json()["code"] == "INVALID_REPLY"
    c.input("answer", status=422)
    c.input("clarification", status=422, reply_to_input_id=q["id"])
    c.input("answer", status=409, reply_to_input_id=str(uuid4()))
    c.input(status=422, author="engineering")
    c.input(status=422, origin_run_id=str(uuid4()))
    a = c.input("answer", reply_to_input_id=q["id"])["input"]
    c.adopt([a["id"], q["id"]], [q["id"]], status=422)
    c.adopt([a["id"], a["id"]], status=422)
    c.adopt(status=422)
    c.adopt([str(uuid4())], status=409)
    c.adopt([q["id"], a["id"]])
    c.input("answer", status=409, reply_to_input_id=q["id"])
    assert c.get()["pending_input_count"] == 0


def test_unclaimed_cancel_and_stop_are_provably_stopped(control):
    c = control
    first = c.start()
    response = c.action("stop_for_update", expected_run_id=first["id"])
    assert (
        response["run"]["state"] == "completed"
        and response["run"]["outcome"] == "superseded"
    )
    assert (
        response["task"]["state"] == "draft"
        and response["task"]["active_run_id"] is None
    )
    second = c.start()
    response = c.action("cancel", expected_run_id=second["id"])
    assert (
        response["task"]["state"] == "cancelled"
        and response["run"]["state"] == "cancelled"
    )
    with Session(c.app.state.engine) as db:
        assert (
            db.scalar(
                select(m.DispatchJob.state).where(
                    m.DispatchJob.run_id == UUID(second["id"])
                )
            )
            == "cancelled"
        )


@pytest.mark.parametrize(
    "command,outcome,state",
    [("stop_for_update", "superseded", "completed"), ("cancel", None, "cancelled")],
)
def test_claimed_stop_waits_for_confirmation(control, command, outcome, state):
    c = control
    run = c.start()
    c.claim(run)
    response = c.action(command, expected_run_id=run["id"])
    assert (
        response["task"]["active_run_id"] == run["id"]
        and response["run"]["state"] == "cancel_requested"
    )
    change = c.input()["input"]
    assert (
        c.adopt([change["id"]], spec=c.get()["spec"], status=409)["code"]
        == "RUN_NOT_STOPPED"
    )
    with pytest.raises(ApiException) as error:
        c.finish(run)
    assert error.value.code == "RUN_STOP_MISMATCH"
    c.finish(run, state=state, outcome=outcome)
    assert c.get()["state"] == ("cancelled" if command == "cancel" else "draft")
    assert c.get()["active_run_id"] is None


def test_interrupted_holds_global_slot_and_retry_is_not_recovery(control):
    c = control
    run = c.start()
    c.claim(run)
    c.finish(run, state="interrupted", outcome=None)
    assert c.get()["active_run_id"] == run["id"] and c.get()["state"] == "blocked"
    assert (
        c.action("retry", expected_run_id=run["id"], status=409)["code"]
        == "RUN_NOT_STOPPED"
    )
    assert (
        c.action("cancel", expected_run_id=run["id"], status=409)["code"]
        == "RUN_NOT_STOPPED"
    )
    c.action("queue", status=409)
    other = create_task(c.client, c.auth, c.eid, key="other").json()["id"]
    c.tid = other
    c.action("queue")
    assert c.action("start", status=409)["code"] == "ACTIVE_RUN_EXISTS"


def test_failed_run_retry_and_late_results_cannot_overwrite(control):
    c = control
    first = c.start()
    c.claim(first)
    old, result = c.finish(
        first, state="failed", outcome=None, error_code="SIMULATED_FAILURE"
    )
    assert c.get()["state"] == "blocked" and c.get()["active_run_id"] is None
    second = c.action("retry", expected_run_id=first["id"])["run"]
    task_before = c.get()
    with Session(c.app.state.engine) as db:
        assert tasks.record_run_result(db, UUID(first["id"]), result) == old
        db.commit()
    assert c.get() == task_before
    with pytest.raises(ApiException) as error:
        c.finish(first, state="failed", outcome=None, error_code="DIFFERENT")
    assert error.value.code == "RUN_RESULT_CONFLICT"
    assert c.get()["active_run_id"] == second["id"]


def test_review_version_artifacts_pending_and_role(control):
    c = control
    first = c.start()
    c.claim(first)
    c.finish(first)
    artifact = c.artifact(first)
    c.review(first, status=409, task_spec_version=999)
    c.review(first, status=422, check_evidence=[])
    c.review(first, status=422, reviewer="engineering")
    change = c.input()["input"]
    assert c.review(first, status=409)["code"] == "INPUTS_PENDING"
    # Rejecting without adopting never bumps the spec, but returns to draft.
    c.adopt(reject=[change["id"]])
    second = c.start()
    c.claim(second)
    c.finish(second)
    assert (
        c.review(second, status=409, artifact_ids=[artifact])["code"]
        == "ARTIFACT_SCOPE_CONFLICT"
    )
    assert c.review(first, status=409)["code"] == "REVIEW_VERSION_MISMATCH"
    body = s.TaskReviewCreate(
        expected_revision=c.get()["revision"],
        run_id=second["id"],
        task_spec_version=c.get()["spec_version"],
        artifact_ids=[c.artifact(second)],
        verdict="accept",
        reason="SIMULATED",
        check_evidence=["SIMULATED"],
    )
    with Session(c.app.state.engine) as db, pytest.raises(ApiException) as error:
        tasks.review(db, UUID(c.tid), body, "engineering", role="engineering")
    assert error.value.status == 403
    result = c.review(second, key="review")
    assert result["task"]["state"] == "succeeded"
    # Replaying original accepted review is allowed even though Task is now closed.
    result2 = c.write(
        "/reviews",
        body.model_dump(mode="json")
        | {
            "reason": "SIMULATED review",
            "check_evidence": ["deterministic control check"],
        },
        key="review",
        status=201,
    )
    assert result2 == result


def login_pair(app, auth):
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "founder", "password": PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 200
    return client, {**auth, "X-CSRF-Token": response.json()["csrf_token"]}


@pytest.mark.parametrize("same_key", [False, True])
def test_concurrent_input_sequence_and_idempotency(control, same_key):
    c = control
    pairs = [login_pair(c.app, c.auth) for _ in range(2)]
    payload = {
        "expected_revision": 1,
        "kind": "clarification",
        "text": "SIMULATED",
        "evidence_artifact_ids": [],
    }
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda pair: pair[0].post(
                        f"/api/v1/tasks/{c.tid}/inputs",
                        json=payload,
                        headers={
                            **pair[1],
                            "Idempotency-Key": "shared" if same_key else str(uuid4()),
                        },
                    ),
                    pairs,
                )
            )
        assert sorted(r.status_code for r in responses) == (
            [201, 201] if same_key else [201, 409]
        )
        inputs = c.client.get(f"/api/v1/tasks/{c.tid}/inputs").json()["items"]
        assert len(inputs) == 1 and inputs[0]["sequence"] == 1
        assert c.get()["revision"] == 2 and c.get()["pending_input_count"] == 1
        if same_key:
            assert responses[0].json() == responses[1].json()
    finally:
        for client, _ in pairs:
            client.close()


def test_concurrent_different_tasks_only_one_global_run(control):
    c = control
    c.action("queue")
    other = create_task(c.client, c.auth, c.eid, key="other").json()["id"]
    first = c.tid
    c.tid = other
    c.action("queue")
    c.tid = first
    pairs = [login_pair(c.app, c.auth) for _ in range(2)]
    try:
        payload = {
            "command": "start",
            "expected_revision": 2,
            "expected_run_id": None,
            "model_profile_revision_id": c.profile,
        }
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda args: args[0][0].post(
                        f"/api/v1/tasks/{args[1]}/actions",
                        json=payload,
                        headers={**args[0][1], "Idempotency-Key": str(uuid4())},
                    ),
                    zip(pairs, [first, other]),
                )
            )
        assert sorted(r.status_code for r in responses) == [202, 409]
        assert (
            next(r for r in responses if r.status_code == 409).json()["code"]
            == "ACTIVE_RUN_EXISTS"
        )
        with Session(c.app.state.engine) as db:
            assert db.scalar(select(func.count()).select_from(m.Run)) == 1
            assert db.scalar(select(func.count()).select_from(m.DispatchJob)) == 1
            existing = db.scalar(select(m.Run))
            target = UUID(other) if existing.task_id == UUID(first) else UUID(first)
            db.add(
                m.Run(
                    task_id=target,
                    task_spec_version=1,
                    attempt=1,
                    model_profile_revision_id=UUID(c.profile),
                    applied_input_ids=[],
                    snapshot={},
                )
            )
            with pytest.raises(IntegrityError) as error:
                db.flush()
            assert error.value.orig.diag.constraint_name == "uq_run_global_active"
    finally:
        for client, _ in pairs:
            client.close()


def test_start_and_adoption_roll_back_every_record(control, monkeypatch):
    c = control
    event = events.task_event
    c.action("queue")
    before = c.get()

    def fail(db, task, kind, *args, **kwargs):
        if kind == "run_created":
            raise RuntimeError("injected failure after run/job insert")
        return event(db, task, kind, *args, **kwargs)

    monkeypatch.setattr(events, "task_event", fail)
    c.action("start", status=500)
    assert c.get() == before
    with Session(c.app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(m.Run)) == 0
        assert db.scalar(select(func.count()).select_from(m.DispatchJob)) == 0
    monkeypatch.setattr(events, "task_event", event)
    item = c.input()["input"]
    before = c.get()

    def fail_after_adoption(*args, **kwargs):
        raise RuntimeError("injected failure after version and decision flush")

    monkeypatch.setattr(events, "task_event", fail_after_adoption)
    c.adopt([item["id"]], spec=before["spec"], status=500)
    assert c.get() == before
    with Session(c.app.state.engine) as db:
        assert db.get(m.TaskInput, UUID(item["id"])).status == "pending"
        assert db.scalar(select(func.count()).select_from(m.TaskVersion)) == 1


def test_result_artifacts_and_state_rollback_together(control, monkeypatch):
    c = control
    run = c.start()
    c.claim(run)
    before = c.get()

    def fail(*args, **kwargs):
        raise RuntimeError("injected result event failure")

    monkeypatch.setattr(events, "run_event", fail)
    with pytest.raises(RuntimeError):
        c.finish(run)
    assert c.get() == before
    with Session(c.app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(m.Artifact)) == 0
        assert db.get(m.Run, UUID(run["id"])).state == "running"
        assert db.scalar(select(m.DispatchJob.state)) == "running"


def test_database_protects_historical_evidence(control):
    c = control
    item = c.input()["input"]
    c.adopt([item["id"]], spec=c.get()["spec"])
    run = c.start()
    c.claim(run)
    c.finish(run)
    review = c.review(run)
    statements = [
        (
            "UPDATE task_reviews SET reason = 'tamper' WHERE id=:id",
            review["review"]["id"],
        ),
        ("UPDATE task_versions SET spec='{}'::jsonb WHERE task_id=:id", c.tid),
        ("UPDATE runs SET snapshot='{}'::jsonb WHERE id=:id", run["id"]),
        ("UPDATE task_inputs SET text='tamper' WHERE id=:id", item["id"]),
        ("DELETE FROM task_events WHERE task_id=:id", c.tid),
    ]
    for statement, identifier in statements:
        with Session(c.app.state.engine) as db, pytest.raises(IntegrityError):
            db.execute(text(statement), {"id": UUID(identifier)})


def test_sequence_pagination_versions_auth_and_missing(control):
    c = control
    for _ in range(3):
        c.input()
    first = c.client.get(f"/api/v1/tasks/{c.tid}/inputs?limit=2").json()
    second = c.client.get(
        f"/api/v1/tasks/{c.tid}/inputs",
        params={"after_sequence": first["last_sequence"], "limit": 2},
    ).json()
    assert first["has_more"] and not second["has_more"]
    assert [i["sequence"] for i in first["items"] + second["items"]] == [1, 2, 3]
    empty = c.client.get(f"/api/v1/tasks/{c.tid}/inputs?after_sequence=99").json()
    assert empty == {"items": [], "last_sequence": 99, "has_more": False}
    for path in [
        f"/api/v1/tasks/{uuid4()}/inputs",
        f"/api/v1/tasks/{uuid4()}/reviews",
        f"/api/v1/runs/{uuid4()}",
        f"/api/v1/tasks/{c.tid}/versions/99",
    ]:
        assert c.client.get(path).status_code == 404
    assert (
        c.client.get(f"/api/v1/tasks/{c.tid}/inputs?after_sequence=-1").status_code
        == 422
    )
    with TestClient(c.app) as anonymous:
        assert anonymous.get(f"/api/v1/tasks/{c.tid}/inputs").status_code == 401
    assert (
        c.client.post(
            f"/api/v1/tasks/{c.tid}/apply-inputs", json={}, headers={"Origin": ORIGIN}
        ).status_code
        == 403
    )


def _source_artifact(payload: bytes):
    return {
        "name": "workspace.tar.gz",
        "kind": "source-snapshot",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }


def test_run_snapshot_records_the_fixed_spec_version(control):
    c = control
    run = c.start()
    with Session(c.app.state.engine) as db:
        snapshot = db.get(m.Run, UUID(run["id"])).snapshot
    assert (
        snapshot["spec_version"] == run["task_spec_version"] == c.get()["spec_version"]
    )
    assert snapshot["spec"]["inputs"] == ["明确标注的模拟输入"]


def test_retry_uses_confirmed_failed_source_instead_of_older_completed(control):
    c = control
    first = c.start()
    c.claim(first)
    c.finish(
        first, outcome="needs_input", artifacts=[_source_artifact(b"completed-v1")]
    )
    question = c.client.get(f"/api/v1/tasks/{c.tid}/inputs").json()["items"][0]
    answer = c.input("answer", reply_to_input_id=question["id"])["input"]
    c.adopt([answer["id"]])
    second = c.action("continue", expected_run_id=first["id"])["run"]
    with Session(c.app.state.engine) as db:
        continued = db.get(m.Run, UUID(second["id"])).snapshot["engineering"][
            "prior_source"
        ]
    assert continued["artifact_id"] == c.artifact(first)
    assert continued["run_id"] == first["id"]
    c.claim(second)
    c.finish(
        second,
        state="failed",
        outcome=None,
        error_code="SIMULATED_FAILURE",
        artifacts=[_source_artifact(b"failed-v2")],
    )
    third = c.action("retry", expected_run_id=second["id"])["run"]
    with Session(c.app.state.engine) as db:
        repair = db.get(m.Run, UUID(third["id"])).snapshot["engineering"][
            "prior_source"
        ]
    assert repair["artifact_id"] == c.artifact(second)
    assert repair["run_id"] == second["id"]
    assert repair["artifact_id"] != c.artifact(first)


def test_interrupted_source_is_not_a_repair_baseline(control):
    c = control
    run = c.start()
    c.claim(run)
    c.finish(
        run,
        state="interrupted",
        outcome=None,
        error_code="STOP_UNCONFIRMED",
        artifacts=[_source_artifact(b"unknown-stop")],
    )
    assert c.get()["active_run_id"] == run["id"]
    assert c.artifact(run)
    with Session(c.app.state.engine) as db:
        assert trusted_prior_source(db, UUID(c.tid)) is None
    assert (
        c.action("retry", expected_run_id=run["id"], status=409)["code"]
        == "RUN_NOT_STOPPED"
    )
