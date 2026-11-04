"""Additional concurrency, migration and atomicity boundaries for C1b."""

import json
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from onefde.modules.tasks import events
from tests.support import models as m
from tests.support.factories import task_payload


def test_rejecting_question_does_not_imply_answer_or_allow_continue(control):
    c = control
    run = c.start()
    c.claim(run)
    c.finish(run, outcome="needs_input")
    question = c.client.get(f"/api/v1/tasks/{c.tid}/inputs").json()["items"][-1]
    c.adopt(reject=[question["id"]])
    assert (
        c.action("continue", expected_run_id=run["id"], status=409)["code"]
        == "QUESTION_UNRESOLVED"
    )


def test_review_failure_rolls_back_review_and_generated_change_input(
    control, monkeypatch
):
    c = control
    run = c.start()
    c.claim(run)
    c.finish(run)
    before = c.get()
    event = events.task_event

    def fail(db, task, kind, *args, **kwargs):
        if kind == "review_recorded":
            raise RuntimeError(
                "injected failure after immutable review and change input"
            )
        return event(db, task, kind, *args, **kwargs)

    monkeypatch.setattr(events, "task_event", fail)
    c.review(run, "request_changes", status=500)
    assert c.get() == before
    with Session(c.app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(m.TaskReview)) == 0
        assert db.scalar(select(func.count()).select_from(m.TaskInput)) == 0


def test_model_config_pending_inputs_and_expected_run_checks(control):
    c = control
    pending = c.input()["input"]
    assert c.action("queue", status=409)["code"] == "INPUTS_PENDING"
    c.adopt(reject=[pending["id"]])
    c.action("queue")
    original = c.profile
    c.profile = str(uuid4())
    assert c.action("start", status=409)["code"] == "MODEL_PROFILE_UNAVAILABLE"
    c.profile = original
    run = c.action("start")["run"]
    assert (
        c.action("cancel", expected_run_id=str(uuid4()), status=409)["code"]
        == "RUN_MISMATCH"
    )
    assert c.action("stop_for_update", status=422)["code"] == "VALIDATION_ERROR"
    with Session(c.app.state.engine) as db:
        assert db.get(m.Run, UUID(run["id"])).snapshot["inputs"] == []
        assert db.scalar(select(func.count()).select_from(m.DispatchJob)) == 1


def test_review_artifact_cannot_be_referenced_as_foreign_engagement_input(control):
    c = control
    run = c.start()
    c.claim(run)
    c.finish(run)
    artifact = c.artifact(run)
    # Keep only local task under test, create a second Engagement with a second draft.
    from tests.support.factories import create_engagement, create_task

    engagement = create_engagement(c.client, c.auth, "different-engagement")
    other = create_task(c.client, c.auth, engagement["id"], key="different-task").json()
    c.tid = other["id"]
    assert (
        c.input(evidence_artifact_ids=[artifact], status=409)["code"]
        == "ARTIFACT_SCOPE_CONFLICT"
    )


def test_c1a_to_c1b_migration_backfills_and_preserves_old_task(
    settings, app, monkeypatch
):
    assert settings.database_url.get_secret_value().rsplit("/", 1)[-1].endswith("_test")
    monkeypatch.setenv("ONEFDE_DATABASE_URL", settings.database_url.get_secret_value())
    config = Config("alembic.ini")
    command.downgrade(config, "d3a2bfe5f985")
    eid, tid = uuid4(), uuid4()
    payload = task_payload()
    with app.state.engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO engagements(id,title,is_demo,goal,created_at) VALUES(:id,'old C1a',true,'preserve',now())"
            ),
            {"id": eid},
        )
        db.execute(
            text("""INSERT INTO tasks(id,engagement_id,request_id,task_key,original_request,spec,owner_role,executor_role,state,revision,spec_version,created_at)
                         VALUES(:id,:eid,:rid,'old','old original request',CAST(:spec AS jsonb),'fde','engineering','draft',1,1,now())"""),
            {
                "id": tid,
                "eid": eid,
                "rid": uuid4(),
                "spec": json.dumps(payload["spec"]),
            },
        )
    try:
        command.upgrade(config, "head")
        with Session(app.state.engine) as db:
            task = db.get(m.Task, tid)
            version = db.scalar(
                select(m.TaskVersion).where(m.TaskVersion.task_id == tid)
            )
            assert task.original_request == "old original request"
            assert task.spec == version.spec == payload["spec"]
            assert version.spec_version == 1 and version.actor == "migration:c1a"
            assert task.active_run_id is None and task.pending_input_count == 0
        command.check(config)
    finally:
        # Leave schema at head even when an assertion fails.
        command.upgrade(config, "head")


def test_downgrade_refuses_to_discard_c1b_business_history(
    control, settings, monkeypatch
):
    c = control
    c.input()
    monkeypatch.setenv("ONEFDE_DATABASE_URL", settings.database_url.get_secret_value())
    with pytest.raises(RuntimeError, match="history exists"):
        command.downgrade(Config("alembic.ini"), "d3a2bfe5f985")
    with c.app.state.engine.connect() as db:
        assert (
            db.scalar(text("SELECT version_num FROM alembic_version")) == "d5454eda0523"
        )
    assert c.get()["pending_input_count"] == 1
