"""Loopback HTTP + deterministic internal adapter, isolated PostgreSQL *_test only.

This proves control persistence, never actual model or engineering execution.
Run from backend: uv run --locked python -m scripts.c1b_smoke
"""

import copy
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from alembic import command
from alembic.config import Config
from argon2 import PasswordHasher
from dotenv import dotenv_values
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from onefde.core.config import Settings
from onefde.infrastructure.db.session import make_engine
from onefde.modules.tasks import models as m
from onefde.modules.tasks import schemas as s
from onefde.modules.tasks import service as tasks
from onefde.modules.tasks.policies import ACTIVE

ROOT = Path(__file__).resolve().parents[2]


def main():
    configured = Settings()
    test_url = os.environ.get("ONEFDE_TEST_DATABASE_URL") or dotenv_values(".env").get(
        "ONEFDE_TEST_DATABASE_URL"
    )
    if (
        not test_url
        or not make_url(test_url).database.endswith("_test")
        or test_url == configured.database_url.get_secret_value()
    ):
        raise SystemExit("Requires a separate ONEFDE_TEST_DATABASE_URL ending _test")
    previous = os.environ.get("ONEFDE_DATABASE_URL")
    os.environ["ONEFDE_DATABASE_URL"] = test_url
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        if previous is None:
            os.environ.pop("ONEFDE_DATABASE_URL", None)
        else:
            os.environ["ONEFDE_DATABASE_URL"] = previous
    engine = make_engine(test_url)
    with Session(engine) as db:
        if db.scalar(select(m.Run.id).where(m.Run.state.in_(ACTIVE)).limit(1)):
            raise SystemExit(
                "Isolated test database has an active run; inspect it before repeating this test"
            )
        profile = m.ModelProfileRevision(
            provider="deterministic-control-test",
            model="NO-MODEL-CALL",
            capabilities=[],
            config={"adapter": "deterministic-test"},
        )
        db.add(profile)
        db.flush()
        profile_id = str(profile.revision_id)
        db.commit()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    password = secrets.token_urlsafe(24)
    env = os.environ.copy()
    env.update(
        ONEFDE_DATABASE_URL=test_url,
        ONEFDE_ENVIRONMENT="development",
        ONEFDE_COOKIE_SECURE="false",
        ONEFDE_TRUSTED_ORIGIN=base,
        ONEFDE_OWNER_USERNAME="c1b-smoke-founder",
        ONEFDE_OWNER_PASSWORD_HASH=PasswordHasher().hash(password),
    )
    evidence = {
        "started_at": datetime.now(UTC).isoformat(),
        "scope": "C1b deterministic control only",
        "real_model_calls": 0,
        "worker_started": False,
        "checks": [],
    }
    work = ROOT / "work"
    work.mkdir(exist_ok=True)

    def check(response, status, label):
        assert response.status_code == status, (
            label,
            response.status_code,
            response.text,
        )
        evidence["checks"].append({"check": label, "status": status})
        return response.json() if response.content else None

    def start(log):
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "onefde.entrypoints.api:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        for _ in range(100):
            if proc.poll() is not None:
                raise RuntimeError("API exited; inspect work/c1b-http-server.log")
            try:
                if httpx.get(base + "/health", timeout=0.3).status_code == 200:
                    return proc
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        stop(proc)
        raise RuntimeError("API startup timed out")

    def stop(proc):
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)

    with (
        (work / "c1b-http-server.log").open("w", encoding="utf-8") as log,
        httpx.Client(base_url=base, timeout=10) as client,
    ):
        process = start(log)
        try:
            evidence["first_process_id"] = process.pid
            check(
                httpx.get(base + "/api/v1/auth/session"),
                401,
                "unauthenticated rejected",
            )
            identity = check(
                client.post(
                    "/api/v1/auth/login",
                    json={"username": "c1b-smoke-founder", "password": password},
                    headers={"Origin": base},
                ),
                200,
                "login",
            )
            headers = {"Origin": base, "X-CSRF-Token": identity["csrf_token"]}

            def post(path, data, label, status=200, key=None, method="POST"):
                return check(
                    client.request(
                        method,
                        path,
                        json=data,
                        headers={
                            **headers,
                            "Content-Type": "application/json",
                            "Idempotency-Key": key or str(uuid4()),
                        },
                    ),
                    status,
                    label,
                )

            engagement = post(
                "/api/v1/engagements",
                {
                    "title": "C1b SIMULATED control only",
                    "goal": "验证持久控制，不执行工程",
                    "is_demo": True,
                },
                "create simulated engagement",
                201,
            )
            spec = {
                "title": "SIMULATED persistent task",
                "objective": "验证输入采用与评审",
                "scope": "control-only",
                "inputs": ["SIMULATED fixture"],
                "confirmed_rules": [],
                "completion_criteria": ["核查控制状态"],
                "dependencies": [],
                "capability_versions": [],
            }
            task = post(
                f"/api/v1/engagements/{engagement['id']}/tasks",
                {
                    "request_id": str(uuid4()),
                    "task_key": "c1b-control",
                    "original_request": "SIMULATED control",
                    "spec": spec,
                    "owner_role": "fde",
                    "executor_role": "engineering",
                },
                "create task",
                201,
            )
            tid = task["id"]
            path = f"/api/v1/tasks/{tid}"

            def current():
                response = client.get(path)
                assert response.status_code == 200, response.text
                return response.json()

            def act(name, run_id=None):
                body = {
                    "command": name,
                    "expected_revision": current()["revision"],
                    "expected_run_id": run_id,
                }
                if name in ("start", "continue", "retry"):
                    body["model_profile_revision_id"] = profile_id
                return post(path + "/actions", body, name, 202)

            def simulate_result(run_id, outcome):
                # Internal test adapter, not a public endpoint, worker or model call.
                with Session(engine) as db:
                    tasks.mark_run_started(db, UUID(run_id))
                    db.commit()
                payload = {
                    "state": "completed",
                    "outcome": outcome,
                    "summary": "SIMULATED fixture result",
                    "stopped": True,
                }
                if outcome == "needs_input":
                    payload["question"] = "SIMULATED question: confirm scope"
                else:
                    payload["artifacts"] = [
                        {
                            "name": "SIMULATED fixture",
                            "kind": "test-fixture",
                            "sha256": "a" * 64,
                            "size_bytes": 0,
                        }
                    ]
                with Session(engine) as db:
                    tasks.record_run_result(db, UUID(run_id), s.RunResult(**payload))
                    db.commit()

            check(
                client.post(
                    path + "/inputs",
                    json={},
                    headers={**headers, "X-CSRF-Token": "wrong"},
                ),
                403,
                "bad CSRF rejected",
            )
            first = post(
                path + "/inputs",
                {
                    "expected_revision": 1,
                    "kind": "clarification",
                    "text": "SIMULATED clarification",
                    "evidence_artifact_ids": [],
                },
                "record pending clarification",
                201,
            )
            assert (
                first["task"]["spec_version"] == 1
                and first["input"]["status"] == "pending"
            )
            adopt = {
                "expected_revision": current()["revision"],
                "apply_ids": [first["input"]["id"]],
                "reject_ids": [],
                "reason": "SIMULATED adoption",
                "spec": copy.deepcopy(spec),
            }
            adopted = post(
                path + "/apply-inputs",
                adopt,
                "adopt clarification",
                key="adopt-clarification",
            )
            assert adopted["spec_version"] == 2
            post(
                path + "/apply-inputs",
                adopt | {"reason": "different"},
                "same-key conflict",
                409,
                key="adopt-clarification",
            )
            post(
                path,
                {"expected_revision": 1, "spec": spec},
                "stale revision rejected",
                409,
                method="PATCH",
            )
            act("queue")
            run1 = act("start")["run"]
            with Session(engine) as db:
                assert (
                    db.scalar(
                        select(m.DispatchJob.state).where(
                            m.DispatchJob.run_id == UUID(run1["id"])
                        )
                    )
                    == "pending"
                )
            simulate_result(run1["id"], "needs_input")
            waiting = check(
                client.get(path), 200, "completed question run releases slot"
            )
            assert (
                waiting["state"] == "waiting_input" and waiting["active_run_id"] is None
            )
            inputs = check(client.get(path + "/inputs"), 200, "read inputs")
            question = inputs["items"][-1]
            answer = post(
                path + "/inputs",
                {
                    "expected_revision": current()["revision"],
                    "kind": "answer",
                    "text": "SIMULATED answer",
                    "reply_to_input_id": question["id"],
                    "evidence_artifact_ids": [],
                },
                "record answer",
                201,
            )
            post(
                path + "/apply-inputs",
                {
                    "expected_revision": current()["revision"],
                    "apply_ids": [answer["input"]["id"]],
                    "reject_ids": [],
                    "reason": "SIMULATED answer adopted",
                },
                "adopt answer and linked question",
            )
            run2 = act("continue", run1["id"])["run"]
            simulate_result(run2["id"], "submitted")
            assert current()["state"] == "review"
            artifacts = check(
                client.get(f"/api/v1/runs/{run2['id']}/artifacts"),
                200,
                "fixed artifact metadata",
            )
            reviewed = post(
                path + "/reviews",
                {
                    "expected_revision": current()["revision"],
                    "run_id": run2["id"],
                    "task_spec_version": current()["spec_version"],
                    "artifact_ids": [artifacts["items"][0]["id"]],
                    "verdict": "request_changes",
                    "reason": "SIMULATED changes",
                    "check_evidence": [],
                },
                "request changes",
                201,
            )
            assert reviewed["task"]["state"] == "draft"
            changes = client.get(path + "/inputs").json()["items"][-1]
            spec["scope"] = "SIMULATED revised control scope"
            post(
                path + "/apply-inputs",
                {
                    "expected_revision": current()["revision"],
                    "apply_ids": [changes["id"]],
                    "reject_ids": [],
                    "reason": "SIMULATED revised spec adopted",
                    "spec": spec,
                },
                "adopt changes",
            )
            act("queue")
            run3 = act("start")["run"]
            simulate_result(run3["id"], "submitted")
            artifacts = client.get(f"/api/v1/runs/{run3['id']}/artifacts").json()[
                "items"
            ]
            accepted = post(
                path + "/reviews",
                {
                    "expected_revision": current()["revision"],
                    "run_id": run3["id"],
                    "task_spec_version": current()["spec_version"],
                    "artifact_ids": [artifacts[0]["id"]],
                    "verdict": "accept",
                    "reason": "SIMULATED acceptance",
                    "check_evidence": ["deterministic state check"],
                },
                "accept fixed submission",
                201,
            )
            assert accepted["task"]["state"] == "succeeded"
            assert (
                post(
                    path + "/apply-inputs",
                    adopt,
                    "adoption replay precedes closed/revision checks",
                    key="adopt-clarification",
                )
                == adopted
            )
            versions = check(
                client.get(path + "/versions"), 200, "read immutable versions"
            )
            assert [v["spec_version"] for v in versions["items"]] == [1, 2, 3, 4]
            check(client.get(path + "/versions/1"), 200, "read original version")
            runs = check(client.get(path + "/runs"), 200, "read three runs")
            reviews = check(client.get(path + "/reviews"), 200, "read two reviews")
            events = check(
                client.get(path + "/events?limit=100"), 200, "read ordered task events"
            )
            assert [e["sequence"] for e in events["items"]] == list(
                range(1, len(events["items"]) + 1)
            )
            check(
                client.get(f"/api/v1/runs/{run1['id']}/events"), 200, "read run events"
            )
            check(
                client.get("/api/v1/model-profiles"),
                200,
                "read profile metadata without secrets",
            )
            stop(process)
            process = start(log)
            evidence["second_process_id"] = process.pid
            assert evidence["first_process_id"] != process.pid
            assert (
                check(client.get(path), 200, "task survives process restart")
                == accepted["task"]
            )
            assert (
                check(
                    client.get(path + "/reviews"),
                    200,
                    "reviews survive process restart",
                )
                == reviews
            )
            assert (
                check(client.get(path + "/runs"), 200, "runs survive process restart")
                == runs
            )
            assert (
                check(
                    client.get(path + "/versions"),
                    200,
                    "versions survive process restart",
                )
                == versions
            )
            post("/api/v1/auth/logout", None, "logout", 204)
            evidence.update(
                result="passed",
                completed_at=datetime.now(UTC).isoformat(),
                task=accepted["task"],
                run_ids=[run1["id"], run2["id"], run3["id"]],
                reviews=reviews["items"],
                versions=versions["items"],
                event_count=len(events["items"]),
            )
            (work / "c1b-http.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(
                f"Passed {len(evidence['checks'])} HTTP checks; simulated control only; work/c1b-http.json"
            )
        finally:
            stop(process)
            engine.dispose()


if __name__ == "__main__":
    main()
