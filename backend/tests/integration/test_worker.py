"""Real PostgreSQL control + explicit fake execution. No Engineering/model claim."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from onefde.core.clock import now
from onefde.core.errors import ApiException
from onefde.core.execution import ExecutionReport, RuntimeUnavailable
from onefde.infrastructure.artifacts import PrivateArtifactStore
from onefde.modules.tasks import models as m
from onefde.modules.tasks import schemas as s
from onefde.modules.tasks import service as tasks
from onefde.worker.config import WorkerSettings
from onefde.worker.controller import Worker


def tx(c, function, *args):
    with Session(c.app.state.engine) as db, db.begin():
        return function(db, *args)


def claim(c, owner="worker-a"):
    return tx(c, tasks.claim_next, owner, 30)


def args(job, owner="worker-a"):
    return job["operation_id"], owner, job["claim_token"]


def report():
    return {
        "state": "failed",
        "summary": "SIMULATED stopped result",
        "error_code": "FIXTURE_FAILURE",
        "stopped": True,
    }


def expire(c):
    with c.app.state.engine.begin() as db:
        db.execute(
            text(
                "UPDATE dispatch_jobs SET lease_until=clock_timestamp()-interval '1 second'"
            )
        )


def test_concurrent_workers_claim_once_and_snapshot_is_frozen(control):
    c = control
    run = c.start()
    barrier = threading.Barrier(2)

    def compete(owner):
        barrier.wait()
        return claim(c, owner)

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(compete, ["worker-a", "worker-b"]))
    jobs = [result for result in results if result]
    assert len(jobs) == 1 and str(jobs[0]["run_id"]) == run["id"]
    assert jobs[0]["snapshot"]["spec"] == c.get()["spec"]
    with Session(c.app.state.engine) as db:
        job = db.scalar(select(m.DispatchJob))
        assert job.attempts == 1 and job.state == "running"
        assert job.lease_until > db.scalar(select(func.clock_timestamp()))
    assert c.get()["active_run_id"] == run["id"]


def test_claim_transaction_rolls_back_all_facts(control):
    c = control
    c.start()
    with pytest.raises(RuntimeError):
        with Session(c.app.state.engine) as db, db.begin():
            assert tasks.claim_next(db, "rolled-back", 30)
            raise RuntimeError("rollback")
    job = claim(c)
    with Session(c.app.state.engine) as db:
        assert db.get(m.DispatchJob, job["operation_id"]).attempts == 1


def test_unadopted_input_prevents_claim(control):
    c = control
    c.start()
    c.input()
    assert claim(c) is None
    with Session(c.app.state.engine) as db:
        job = db.scalar(select(m.DispatchJob))
        assert job.state == "pending" and job.claim_token is None


@pytest.mark.parametrize("wrong", ["owner", "token", "expired"])
def test_lease_fences_heartbeat_and_completion(control, wrong):
    c = control
    c.start()
    job = claim(c)
    identity = list(args(job))
    if wrong == "owner":
        identity[1] = "worker-b"
    if wrong == "token":
        identity[2] = uuid4()
    if wrong == "expired":
        expire(c)
    for function, tail in [
        (tasks.heartbeat_claim, (30,)),
        (tasks.complete_claim, (report(), (), {"stopped": True})),
    ]:
        with pytest.raises(ApiException) as error:
            tx(c, function, *identity, *tail)
        assert error.value.code == "CLAIM_LOST"


def test_expired_claim_freezes_slot_and_never_reexecutes(control):
    c = control
    run = c.start()
    job = claim(c)
    expire(c)
    assert tx(c, tasks.expire_claims) == 1
    assert tx(c, tasks.expire_claims) == 0
    assert claim(c, "replacement") is None
    task = c.get()
    assert (
        task["active_run_id"] == run["id"] and task["block_reason"] == "RUN_INTERRUPTED"
    )
    with pytest.raises(ApiException):
        tx(c, tasks.complete_claim, *args(job), report(), (), {"stopped": True})
    assert c.client.get("/api/v1/runs/" + run["id"]).json()["state"] == "interrupted"


def test_durable_completion_replay_and_conflict(control):
    c = control
    c.start()
    job = claim(c)
    first = tx(c, tasks.complete_claim, *args(job), report(), (), {"stopped": True})
    expire(c)  # Identical acknowledgement remains replayable after lease lifetime.
    second = tx(c, tasks.complete_claim, *args(job), report(), (), {"stopped": True})
    assert first == second
    with pytest.raises(ApiException) as error:
        tx(
            c,
            tasks.complete_claim,
            *args(job),
            {**report(), "summary": "different"},
            (),
            {"stopped": True},
        )
    assert error.value.code == "RUN_RESULT_CONFLICT"
    with Session(c.app.state.engine) as db:
        stored = db.get(m.DispatchJob, job["operation_id"])
        assert stored.result_digest and stored.completed_at and stored.result_payload


@pytest.mark.parametrize("gate", ["authorized", "denied", "pending", "wrong-source"])
def test_iteration_recovery_pins_candidate_and_never_requeues_twice(control, gate):
    c = control
    task_id = UUID(c.tid)
    c.action("queue")
    initial = {
        "assembly_revision": "standard-v1",
        "task_id": c.tid,
        "engagement_id": c.eid if gate != "wrong-source" else str(uuid4()),
        "sha256": "a" * 64,
    }
    with Session(c.app.state.engine) as db, db.begin():
        run = tasks.action(
            db,
            task_id,
            s.TaskAction(
                command="start",
                expected_revision=db.get(m.Task, task_id).revision,
                expected_run_id=None,
                model_profile_revision_id=UUID(c.profile),
            ),
            "founder",
            initial_source=initial,
        ).run
    job = claim(c)
    if gate == "pending":
        c.input()
    result = {
        **report(),
        "error_code": "ITERATION_LIMIT_REACHED",
        "artifacts": [
            {
                "kind": "source-snapshot",
                "name": "workspace.tar.gz",
                "sha256": "b" * 64,
                "size_bytes": 10,
            }
        ],
    }
    proof = {
        "stopped": True,
        "stop_reason": "ITERATION_LIMIT_REACHED",
        "source_digest": "c" * 64,
    }
    authorized = []
    policy = {
        "expires_at": (now() + timedelta(minutes=10)).isoformat(),
        "max_cost_usd": 0.10,
        "max_requests": 9,
    }

    def authorize(db, previous):
        assert previous.id == run.id
        return None if gate == "denied" else (authorized.append, policy)

    completion = (
        *args(job),
        result,
        (f"engagements/{c.eid}/runs/{run.id}/candidate",),
        proof,
        authorize,
    )
    tx(c, tasks.complete_claim, *completion)
    tx(c, tasks.complete_claim, *completion)
    if gate == "authorized":
        assert len(authorized) == 1
        recovered = claim(c, "restarted-worker")
        assert recovered["run_id"] == authorized[0]
        assert recovered["task_id"] == task_id
        assert recovered["snapshot"]["spec_version"] == run.task_spec_version
        engineering = recovered["snapshot"]["engineering"]
        assert engineering["initial_source"] == initial
        assert engineering["recovery_policy"] == policy
        assert engineering["prior_source"]["run_id"] == str(run.id)
        assert engineering["prior_source"]["sha256"] == "b" * 64
        assert claim(c, "duplicate-worker") is None
    else:
        assert not authorized and claim(c, "restarted-worker") is None


def test_recovery_claim_cannot_extend_original_limits():
    clock = now()
    task_id = uuid4()
    settings = WorkerSettings(
        _env_file=None,
        recovery_task_id=task_id,
        recovery_expires_at=clock + timedelta(hours=1),
        recovery_total_cost_usd=0.20,
        max_cost_usd=0.10,
        max_requests=9,
    )
    policy = {
        "expires_at": (clock + timedelta(minutes=1)).isoformat(),
        "max_cost_usd": 0.10,
        "max_requests": 9,
    }
    assert settings.recovery_claim_allowed(task_id, clock, policy)
    assert not settings.recovery_claim_allowed(uuid4(), clock, policy)
    assert not settings.recovery_claim_allowed(
        task_id, clock + timedelta(minutes=2), policy
    )
    assert not settings.recovery_claim_allowed(
        task_id, clock, {**policy, "max_requests": 8}
    )
    assert not settings.recovery_claim_allowed(
        task_id, clock, {**policy, "max_cost_usd": 0.05}
    )


def test_completion_rollback_does_not_release_slot(control):
    c = control
    run = c.start()
    job = claim(c)
    with pytest.raises(RuntimeError):
        with Session(c.app.state.engine) as db, db.begin():
            tasks.complete_claim(db, *args(job), report(), (), {"stopped": True})
            raise RuntimeError("rollback")
    assert c.get()["active_run_id"] == run["id"]
    with Session(c.app.state.engine) as db:
        assert db.get(m.DispatchJob, job["operation_id"]).result_digest is None
    tx(c, tasks.complete_claim, *args(job), report(), (), {"stopped": True})
    assert c.get()["active_run_id"] is None


def test_stop_requires_evidence_and_honors_last_intent(control):
    c = control
    run = c.start()
    job = claim(c)
    c.action("stop_for_update", expected_run_id=run["id"])
    assert tx(c, tasks.heartbeat_claim, *args(job), 30) is True
    assert c.get()["active_run_id"] == run["id"]
    with pytest.raises(ApiException) as error:
        tx(c, tasks.complete_claim, *args(job), report(), (), {"stopped": False})
    assert error.value.code == "STOP_UNCONFIRMED"
    result = tx(c, tasks.complete_claim, *args(job), report(), (), {"stopped": True})
    assert result.state == "completed" and result.outcome == "superseded"
    assert c.get()["active_run_id"] is None and c.get()["state"] == "draft"


class FakeAdapter:
    """Writes a clearly labeled real test blob, never calls SDK/model."""

    def __init__(self, c, root, *, stop=False, corrupt=False):
        self.c, self.root, self.stop, self.corrupt = c, root, stop, corrupt

    def execute(self, request, stop):
        # A fresh connection can read committed claim while execution is in progress.
        with Session(self.c.app.state.engine) as db:
            job = db.get(m.DispatchJob, request.operation_id)
            assert job.state == "running" and job.claim_token
        request.on_resource({"fixture": True, "run_id": str(request.run_id)})
        if self.stop:
            self.c.action("cancel", expected_run_id=str(request.run_id))
            assert stop.wait(5), "heartbeat must observe HTTP cancellation"
            assert self.c.get()["active_run_id"] == str(request.run_id)
        store = PrivateArtifactStore(self.root / "artifacts")
        key = f"engagements/{request.engagement_id}/runs/{request.run_id}/{uuid4()}"
        evidence = store.put(key, b"EXPLICIT TEST FIXTURE - NOT ENGINEERING OUTPUT")
        if self.corrupt:
            evidence["sha256"] = "0" * 64
        return ExecutionReport(
            {
                "state": "completed",
                "outcome": "submitted",
                "summary": "SIMULATED result",
                "stopped": True,
                "artifacts": [
                    {"name": "SIMULATED", "kind": "test-fixture", **evidence}
                ],
            },
            (key,),
            {"stopped": True, "method": "test-fixture"},
        )


@pytest.mark.parametrize("mode", ["submitted", "cancel", "corrupt"])
def test_worker_persists_stop_and_artifacts_via_http(control, tmp_path, mode):
    c = control
    run = c.start()
    settings = WorkerSettings(
        _env_file=None, root=tmp_path, heartbeat_seconds=0.1, lease_seconds=30
    )
    worker = Worker(
        c.app.state.engine,
        settings,
        FakeAdapter(c, tmp_path, stop=mode == "cancel", corrupt=mode == "corrupt"),
    )
    assert worker.run_once(expected_run_id=uuid4()) is False
    assert worker.run_once(expected_run_id=UUID(run["id"])) is True
    assert worker.run_once() is False
    result = c.client.get("/api/v1/runs/" + run["id"]).json()
    assert (
        result["state"]
        == {"submitted": "completed", "cancel": "cancelled", "corrupt": "failed"}[mode]
    )
    assert c.get()["active_run_id"] is None
    assert (
        c.get()["state"]
        == {"submitted": "review", "cancel": "cancelled", "corrupt": "blocked"}[mode]
    )
    with Session(c.app.state.engine) as db:
        artifact = db.scalar(select(m.Artifact))
        job = db.scalar(select(m.DispatchJob))
        assert job.runtime_ref["fixture"] and job.result_digest
        if mode == "corrupt":
            assert artifact is None
        else:
            assert artifact and artifact.run_id == UUID(run["id"])
            PrivateArtifactStore(tmp_path / "artifacts").verify(
                artifact.object_key,
                {"sha256": artifact.sha256, "size_bytes": artifact.size_bytes},
            )
    assert list((tmp_path / "artifacts/receipts" / run["id"]).glob("*.json"))


@pytest.mark.parametrize("unavailable", [True, False])
def test_worker_missing_config_vs_unknown_runtime(control, tmp_path, unavailable):
    c = control
    run = c.start()

    class Broken:
        def execute(self, request, stop):
            raise (
                RuntimeUnavailable()
                if unavailable
                else RuntimeError("uncertain allocation")
            )

    worker = Worker(
        c.app.state.engine, WorkerSettings(_env_file=None, root=tmp_path), Broken()
    )
    assert worker.run_once()
    result = c.client.get("/api/v1/runs/" + run["id"]).json()
    assert result["state"] == ("failed" if unavailable else "interrupted")
    assert (c.get()["active_run_id"] is None) == unavailable


def test_resource_reference_is_immutable_and_downgrade_preserves_c2_history(
    control, settings, monkeypatch
):
    from alembic import command
    from alembic.config import Config

    c = control
    c.start()
    job = claim(c)
    tx(c, tasks.register_resource, *args(job), {"container_id": "fixture"})
    with pytest.raises(ApiException) as error:
        tx(c, tasks.register_resource, *args(job), {"container_id": "different"})
    assert error.value.code == "RESOURCE_CONFLICT"
    # Validation may append a distinct role; swapping the engineering ID still fails.
    tx(
        c,
        tasks.register_resource,
        *args(job),
        {"role": "validation", "container_id": "validation-fixture"},
    )
    with Session(c.app.state.engine) as db:
        row = db.get(m.DispatchJob, job["operation_id"])
        assert [item["role"] for item in row.runtime_ref["resources"]] == [
            "engineering",
            "validation",
        ]
    monkeypatch.setenv("ONEFDE_DATABASE_URL", settings.database_url.get_secret_value())
    with pytest.raises(RuntimeError, match="history"):
        command.downgrade(Config("alembic.ini"), "4bf8db3c4ef3")


def test_heartbeat_renews_lease_and_shutdown_does_not_claim(control, tmp_path):
    c = control
    c.start()
    worker = Worker(
        c.app.state.engine, WorkerSettings(_env_file=None, root=tmp_path), None
    )
    worker.shutdown.set()
    assert worker.run_once() is False
    job = claim(c)
    tx(c, tasks.heartbeat_claim, *args(job), 120)
    with Session(c.app.state.engine) as db:
        row = db.get(m.DispatchJob, job["operation_id"])
        assert row.lease_until > db.scalar(select(func.clock_timestamp())) + timedelta(
            seconds=110
        )


def test_configuration_error_after_allocation_cannot_release_slot(control, tmp_path):
    c = control
    run = c.start()

    class AllocatedFailure:
        def execute(self, request, stop):
            request.on_resource({"fixture": "allocated"})
            raise RuntimeUnavailable()

    worker = Worker(
        c.app.state.engine,
        WorkerSettings(_env_file=None, root=tmp_path),
        AllocatedFailure(),
    )
    assert worker.run_once()
    assert c.get()["active_run_id"] == run["id"]
    assert c.client.get("/api/v1/runs/" + run["id"]).json()["state"] == "interrupted"


def test_model_profile_provision_persists_reference_not_key(control):
    from onefde.modules.tasks.configuration import ModelConfiguration, provision_model

    c = control
    config = ModelConfiguration(
        provider="fixture",
        model="openai/fixture",
        base_url="https://model.example/v1",
        secret_ref="env:ONEFDE_MODEL_TEST",
    )
    identifier = tx(c, provision_model, config)
    with Session(c.app.state.engine) as db:
        profile = db.get(m.ModelProfileRevision, identifier)
        assert profile.integration_status == "configured"
        assert profile.config["secret_ref"] == "env:ONEFDE_MODEL_TEST"
        assert "api_key" not in profile.config
    response = c.client.get("/api/v1/model-profiles")
    assert response.status_code == 200
    assert "secret_ref" not in response.text and "base_url" not in response.text


def test_lost_heartbeat_keeps_receipt_without_late_completion(
    control, tmp_path, monkeypatch
):
    c = control
    run = c.start()

    class StopOnLost:
        def execute(self, request, stop):
            assert stop.wait(5)
            return ExecutionReport(
                report(), proof={"stopped": True, "method": "test-fixture"}
            )

    def disconnected(*args):
        raise ConnectionError("SIMULATED heartbeat database outage")

    monkeypatch.setattr(tasks, "heartbeat_claim", disconnected)
    worker = Worker(
        c.app.state.engine, WorkerSettings(_env_file=None, root=tmp_path), StopOnLost()
    )
    assert worker.run_once()
    assert c.get()["active_run_id"] == run["id"]
    with Session(c.app.state.engine) as db:
        job = db.scalar(select(m.DispatchJob))
        assert job.result_digest is None and job.state == "running"
    assert list((tmp_path / "artifacts/receipts" / run["id"]).glob("*.json"))
    expire(c)
    assert worker.run_once() is False
    assert c.client.get("/api/v1/runs/" + run["id"]).json()["state"] == "interrupted"


def test_unconfirmed_validation_stop_does_not_release_the_slot(control):
    c = control
    run = c.start()
    job = claim(c)
    recorded = tx(
        c,
        tasks.complete_claim,
        *args(job),
        {
            "state": "interrupted",
            "summary": "验证异常且停止未知",
            "error_code": "STOP_UNCONFIRMED",
            "stopped": False,
        },
        (),
        {"stopped": False},
    )
    assert recorded.state == "interrupted"
    assert c.get()["active_run_id"] == run["id"]
    assert c.get()["state"] == "blocked"
    assert claim(c) is None


def test_legacy_queued_snapshot_claims_trusted_spec_version(control):
    """A queued snapshot stored before spec_version was persisted still claims."""
    from onefde.infrastructure.runtime.engineering import build_context

    c = control
    c.action("queue")
    task = c.get()
    stored = {
        "spec": task["spec"],
        "inputs": [],
        "actor": "founder",
        "owner_role": "fde",
        "executor_role": "engineering",
        "permissions": ["engineering:task-workspace"],
        "engineering": {"checks": []},
    }
    with Session(c.app.state.engine) as db, db.begin():
        version = db.scalar(
            select(m.TaskVersion).where(m.TaskVersion.task_id == UUID(c.tid))
        )
        run = m.Run(
            task_id=UUID(c.tid),
            task_spec_version=task["spec_version"],
            attempt=1,
            model_profile_revision_id=UUID(c.profile),
            applied_input_ids=list(version.applied_input_ids),
            snapshot=stored,
        )
        db.add(run)
        db.flush()
        db.add(m.DispatchJob(run_id=run.id, payload={"run_id": str(run.id)}))
        row = db.get(m.Task, UUID(c.tid))
        row.state = "running"
        row.active_run_id = run.id
        row.latest_run_id = run.id
        run_id = run.id
    job = claim(c)
    assert job["snapshot"]["spec_version"] == task["spec_version"]
    assert job["snapshot"]["spec"] == stored["spec"]
    with Session(c.app.state.engine) as db:
        persisted = db.get(m.Run, run_id)
        assert "spec_version" not in persisted.snapshot
        assert persisted.snapshot == stored
    context = build_context(
        job["snapshot"],
        task_id=job["task_id"],
        run_id=job["run_id"],
        engagement_id=job["engagement_id"],
        spec_version=job["snapshot"]["spec_version"],
    )
    assert context["identity"]["spec_version"] == task["spec_version"]
