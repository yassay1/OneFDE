"""Loopback API processes + real Worker controller + explicitly simulated runtime.

Destructively resets ONLY the configured isolated *_test database. No model call.
"""

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
from alembic import command
from alembic.config import Config
from argon2 import PasswordHasher
from dotenv import dotenv_values
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from onefde.core.execution import ExecutionReport
from onefde.infrastructure.artifacts import PrivateArtifactStore
from onefde.infrastructure.db.session import make_engine
from onefde.modules.tasks import models as m
from onefde.worker.config import WorkerSettings
from onefde.worker.controller import Worker
from tests.support.control import Control

BACKEND = Path(__file__).resolve().parents[2]


def main():
    values = {**dotenv_values(".env"), **os.environ}
    url = values.get("ONEFDE_TEST_DATABASE_URL")
    if (
        not url
        or not make_url(url).database.endswith("_test")
        or url == values.get("ONEFDE_DATABASE_URL")
    ):
        raise SystemExit(
            "Requires isolated PostgreSQL *_test, different from development"
        )
    old = os.environ.get("ONEFDE_DATABASE_URL")
    os.environ["ONEFDE_DATABASE_URL"] = url
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        if old is None:
            os.environ.pop("ONEFDE_DATABASE_URL", None)
        else:
            os.environ["ONEFDE_DATABASE_URL"] = old
    engine = make_engine(url)
    with engine.begin() as db:
        db.execute(
            text(
                "TRUNCATE tasks, engagements, auth_sessions, login_attempts, idempotency_records, model_profile_revisions CASCADE"
            )
        )
    with Session(engine) as db, db.begin():
        profile = m.ModelProfileRevision(
            provider="SIMULATED C2 HTTP",
            model="NO-MODEL-CALL",
            config={"adapter": "test-fixture"},
        )
        db.add(profile)
        db.flush()
        profile_id = str(profile.revision_id)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base, password = f"http://127.0.0.1:{port}", secrets.token_urlsafe(24)
    env = os.environ.copy()
    env.update(
        ONEFDE_DATABASE_URL=url,
        ONEFDE_OWNER_USERNAME="c2-smoke",
        ONEFDE_OWNER_PASSWORD_HASH=PasswordHasher().hash(password),
        ONEFDE_ENVIRONMENT="development",
        ONEFDE_COOKIE_SECURE="false",
        ONEFDE_TRUSTED_ORIGIN=base,
    )
    work = BACKEND / "work"
    work.mkdir(exist_ok=True)
    root = work / "c2-runtime" / str(uuid4())
    checks = []
    evidence = {
        "started_at": datetime.now(UTC).isoformat(),
        "scope": "C2 control only; runtime is explicitly simulated",
        "real_model_calls": 0,
        "real_sandbox_started": False,
        "checks": checks,
    }

    class Fixture:
        def execute(self, request, stop):
            request.on_resource({"adapter": "SIMULATED", "run_id": str(request.run_id)})
            c.action("stop_for_update", expected_run_id=str(request.run_id))
            assert c.get()["active_run_id"] == str(request.run_id)
            checks.append("HTTP stop intent retains slot before confirmation")
            assert stop.wait(5)
            checks.append("Worker heartbeat observes HTTP stop")
            store = PrivateArtifactStore(root / "artifacts")
            key = f"engagements/{request.engagement_id}/runs/{request.run_id}/{uuid4()}"
            item = {
                "name": "SIMULATED source",
                "kind": "test-fixture",
                **store.put(key, b"EXPLICIT C2 TEST FIXTURE"),
            }
            return ExecutionReport(
                {
                    "state": "completed",
                    "outcome": "submitted",
                    "summary": "SIMULATED result",
                    "stopped": True,
                    "artifacts": [item],
                },
                (key,),
                {"stopped": True, "method": "test-fixture"},
            )

    def stop_api(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)

    def start_api(log):
        process = subprocess.Popen(
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
            cwd=BACKEND,
            env=env,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        for _ in range(100):
            if process.poll() is not None:
                break
            try:
                if httpx.get(base + "/health", timeout=0.3).status_code == 200:
                    return process
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        stop_api(process)
        raise RuntimeError("API startup failed; inspect work/c2-http-server.log")

    with (
        (work / "c2-http-server.log").open("w", encoding="utf-8") as log,
        httpx.Client(base_url=base, timeout=10) as client,
    ):
        process = start_api(log)
        try:
            evidence["first_process_id"] = process.pid
            identity = client.post(
                "/api/v1/auth/login",
                json={"username": "c2-smoke", "password": password},
                headers={"Origin": base},
            )
            assert identity.status_code == 200
            auth = {"Origin": base, "X-CSRF-Token": identity.json()["csrf_token"]}
            c = Control(
                client,
                auth,
                SimpleNamespace(state=SimpleNamespace(engine=engine)),
                profile_id,
            )
            run = c.start()
            assert run["state"] == "queued"
            checks.append("HTTP 202 persists queued Run without executing")
            worker = Worker(
                engine,
                WorkerSettings(_env_file=None, root=root, heartbeat_seconds=0.1),
                Fixture(),
            )
            assert worker.run_once()
            checks.append("Worker claims committed job and persists result")
            result = client.get("/api/v1/runs/" + run["id"]).json()
            assert result["state"] == "completed" and result["outcome"] == "superseded"
            assert c.get()["state"] == "draft" and c.get()["active_run_id"] is None
            checks.append("Stop intent wins result race, releases only after proof")
            artifacts = client.get("/api/v1/runs/" + run["id"] + "/artifacts").json()[
                "items"
            ]
            assert len(artifacts) == 1
            with Session(engine) as db:
                item = db.scalar(select(m.Artifact))
                PrivateArtifactStore(root / "artifacts").verify(
                    item.object_key,
                    {"sha256": item.sha256, "size_bytes": item.size_bytes},
                )
                job = db.scalar(select(m.DispatchJob))
                assert job.result_digest and job.attempts == 1
            checks.append(
                "Private blob digest/size match PostgreSQL metadata after stop"
            )
            assert not worker.run_once()
            checks.append("Second Worker pass does not execute completed job")
            stop_api(process)
            process = start_api(log)
            evidence["second_process_id"] = process.pid
            assert client.get("/api/v1/runs/" + run["id"]).json() == result
            assert (
                client.get("/api/v1/runs/" + run["id"] + "/artifacts").json()["items"]
                == artifacts
            )
            assert c.get()["state"] == "draft"
            checks.append("Run/Task/artifacts/session survive API process restart")
            restarted = Worker(engine, worker.settings, Fixture())
            assert not restarted.run_once()
            checks.append("New Worker instance does not reclaim completed job")
            evidence.update(
                run_id=run["id"], task_id=c.tid, engagement_id=c.eid, passed=len(checks)
            )
        finally:
            stop_api(process)
            engine.dispose()
    (work / "c2-http-evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "passed": len(checks),
                "evidence": str(work / "c2-http-evidence.json"),
                "real_model_calls": 0,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
