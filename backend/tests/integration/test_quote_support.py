"""Quote support pilot with real PostgreSQL and explicit simulated execution."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from secrets import token_hex
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from onefde.core.clock import now
from onefde.modules.fde import quote_support as support
from onefde.modules.fde.support_models import QuoteSupport
from onefde.modules.tasks import models as m
from onefde.modules.tasks import schemas as s
from onefde.modules.tasks import service as tasks
from tests.support.factories import create_engagement

ORIGIN = "http://127.0.0.1:8765"


def setup_case(
    client, auth, app, profile, *, enroll=True, version=None, name_fixture=True
):
    case = uuid4()
    url = f"/api/v1/public/business/conversations/{case}"
    headers = {"Origin": ORIGIN, "Authorization": f"Bearer {token_hex(32)}"}
    response = client.put(
        url,
        headers=headers,
        json={
            "request_id": str(uuid4()),
            "text": "CSV 导入报错",
            "version_hint": version,
        },
    )
    assert response.status_code == 200, response.text
    if enroll:
        engagement = create_engagement(client, auth)["id"]
        with Session(app.state.engine) as db, db.begin():
            support.enroll(
                db,
                case,
                UUID(engagement),
                UUID(profile),
                now() + timedelta(minutes=5),
                {
                    "sha256": "1" * 64,
                    "object_key": "SIMULATED",
                    "size_bytes": 0,
                    "allowed_paths": [],
                },
                max_runs=3,
            )
    fixture = support.FIXTURE if name_fixture else ""
    send(
        client,
        url,
        headers,
        f"选择 CSV {fixture} 后点击比较，提示缺少 unit_price",
    )
    return case, url, headers


def send(client, url, headers, message):
    response = client.post(
        url + "/messages",
        headers=headers,
        json={
            "request_id": str(uuid4()),
            "text": message,
        },
    )
    assert response.status_code == 200, response.text


def advance(app, case):
    with Session(app.state.engine) as db, db.begin():
        return support.advance(db, case)


def progress(app, case):
    with Session(app.state.engine) as db:
        row = db.get(QuoteSupport, case)
        return row.stage, row.progress


def finish(app, *, question=False):
    with Session(app.state.engine) as db, db.begin():
        claim = tasks.claim_next(db, "deterministic", 30, support.claim_allowed)
        assert claim
    with Session(app.state.engine) as db, db.begin():
        result = {
            "state": "completed",
            "outcome": "needs_input" if question else "submitted",
            "summary": "SIMULATED",
            "stopped": True,
        }
        keys = []
        if question:
            result["question"] = support.QUESTION
        else:
            result["artifacts"] = [
                {
                    "name": "fixture",
                    "kind": "source-snapshot",
                    "sha256": "2" * 64,
                    "size_bytes": 0,
                }
            ]
            keys = [
                f"engagements/{claim['engagement_id']}/runs/{claim['run_id']}/fixture"
            ]
        tasks.complete_claim(
            db,
            claim["operation_id"],
            "deterministic",
            claim["claim_token"],
            result,
            keys,
            {"stopped": True, "simulated": True},
        )
    return claim


@pytest.mark.parametrize("passed", [True, False])
def test_quote_support_accept_answer_resume_review_and_retest(
    client, auth, app, profile, passed
):
    case, url, headers = setup_case(client, auth, app, profile)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: advance(app, case), range(2)))
    assert progress(app, case)[0] == "queued"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: advance(app, case), range(2))) == [False, True]
    first = finish(app, question=True)
    assert advance(app, case)
    assert progress(app, case)[0] == "waiting_answer"
    send(client, url, headers, support.ANSWER)
    assert advance(app, case)
    stage, receipt = progress(app, case)
    assert stage == "answer_saved"
    with Session(app.state.engine) as db:
        item = db.get(m.TaskInput, UUID(receipt["input_id"]))
        assert item.status == "pending" and item.reply_to_input_id
    assert advance(app, case)
    assert advance(app, case)
    second = finish(app)
    assert second["run_id"] != first["run_id"] and second["task_id"] == first["task_id"]
    assert second["snapshot"]["spec_version"] == 2
    with Session(app.state.engine) as db:
        assert db.get(m.Run, first["run_id"]).snapshot == first["snapshot"]
        assert db.scalar(select(func.count()).select_from(m.Task)) == 1
        assert db.scalar(select(func.count()).select_from(m.DispatchJob)) == 2
    assert advance(app, case)
    stage, receipt = progress(app, case)
    assert stage == "review" and receipt["review"]["check_result"]["simulated"]
    assert not advance(app, case)
    with Session(app.state.engine) as db, db.begin():
        task = db.get(m.Task, second["task_id"])
        artifact = db.scalar(
            select(m.Artifact).where(m.Artifact.run_id == second["run_id"])
        )
        artifact_id = artifact.id
        tasks.review(
            db,
            task.id,
            s.TaskReviewCreate(
                expected_revision=task.revision,
                run_id=second["run_id"],
                task_spec_version=2,
                artifact_ids=[artifact.id],
                verdict="accept",
                reason="SIMULATED",
                check_evidence=["SIMULATED"],
            ),
            "founder",
        )
    assert advance(app, case)
    assert client.get(url, headers=headers).json()["retest_notice_id"] is None
    with Session(app.state.engine) as db, db.begin():
        support.register_verified_preview(
            db,
            case,
            artifact_id,
            "http://127.0.0.1:8766/",
            now() + timedelta(seconds=60),
        )
    assert advance(app, case)
    assert not advance(app, case)
    view = client.get(url, headers=headers).json()
    result = client.post(
        url + "/retest",
        headers=headers,
        json={
            "request_id": str(uuid4()),
            "notice_id": view["retest_notice_id"],
            "passed": passed,
            "text": "确认可用"
            if passed
            else f"用 {support.FIXTURE} 仍提示缺少 unit_price",
        },
    )
    assert result.status_code == 200, result.text
    assert advance(app, case)
    if passed:
        assert result.json()["state"] == "closed"
        assert progress(app, case)[0] == "closed"
    else:
        stage, receipt = progress(app, case)
        assert (
            stage == "accepted"
            and receipt["previous_notice_id"] == view["retest_notice_id"]
        )
        with Session(app.state.engine) as db:
            follow_up = db.get(m.Task, UUID(receipt["task_id"]))
            assert follow_up.related_task_id == second["task_id"]
            assert db.get(m.Task, second["task_id"]).state == "succeeded"


def test_quote_support_requires_enrollment_and_matching_report(
    client, auth, app, profile
):
    case, _, _ = setup_case(client, auth, app, profile, enroll=False)
    assert not advance(app, case)
    case, _, _ = setup_case(client, auth, app, profile, version="v2.0")
    assert advance(app, case)
    assert progress(app, case)[0] == "manual"
    with Session(app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(m.Run)) == 0


def test_quote_support_human_request_blocks_queued_claim(client, auth, app, profile):
    case, url, headers = setup_case(client, auth, app, profile)
    for _ in range(3):
        assert advance(app, case)
    send(client, url, headers, "请转人工")
    with Session(app.state.engine) as db, db.begin():
        assert tasks.claim_next(db, "deterministic", 30, support.claim_allowed) is None
    assert advance(app, case)
    assert progress(app, case)[0] == "manual"
    with Session(app.state.engine) as db:
        run = db.scalar(select(m.Run))
        assert run.outcome == "superseded"


def test_quote_support_asks_for_missing_fixture_before_accepting(
    client, auth, app, profile
):
    case, url, headers = setup_case(client, auth, app, profile, name_fixture=False)
    assert advance(app, case)
    assert not advance(app, case)
    assert (
        support.QUESTION
        in client.get(url, headers=headers).json()["messages"][-1]["text"]
    )
    with Session(app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(m.Task)) == 0
    send(client, url, headers, support.ANSWER)
    assert advance(app, case)
    assert progress(app, case)[0] == "accepted"
