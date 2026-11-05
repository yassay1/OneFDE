"""Local Compose HTTP/persistence checks. Fixture metadata, never model execution."""

import hashlib
import json
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from onefde.modules.tasks.configuration import ModelConfiguration, provision_model

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path("/srv/onefde-local/private")
EVIDENCE = Path("/srv/onefde-local/worker/evidence")
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    str(PRIVATE / "compose.env"),
    "-f",
    str(ROOT / "deploy/compose.yaml"),
]
base = "http://127.0.0.1:8002"
report = {"model_called": False, "engineering_executed": False, "checks": []}
admin = create_engine(
    (PRIVATE / "admin_url").read_text().strip().replace("@postgres:", "@172.29.240.3:"),
    hide_parameters=True,
)
with Session(admin) as db, db.begin():
    profile = str(
        provision_model(
            db,
            ModelConfiguration(
                provider="OFFLINE verification fixture",
                model="openai/offline-fixture",
                base_url="https://never-called.invalid/v1",
                secret_ref="env:ONEFDE_MODEL_ABSENT_FIXTURE",
            ),
        )
    )


def write(client, path, body, expected):
    response = client.post(
        "/api/v1" + path, json=body, headers={"Idempotency-Key": str(uuid4())}
    )
    assert response.status_code == expected, (response.status_code, response.text)
    return response.json()


with httpx.Client(
    base_url=base, trust_env=False, timeout=10, headers={"Origin": base}
) as client:
    assert client.get("/api/v1/engagements").status_code == 401
    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": "founder",
            "password": (PRIVATE / "owner_password").read_text().strip(),
        },
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    # An interrupted prior verifier can leave only its explicitly marked,
    # never-claimed fixture queued. Cancel through owner commands, never SQL.
    with admin.connect() as db:
        previous = (
            db.execute(
                text(
                    "SELECT t.id FROM tasks t JOIN engagements e ON e.id=t.engagement_id WHERE e.title='Compose environment verification DEMO' AND t.original_request='Environment control check only; never invoke a model' AND t.state IN ('running','queued')"
                )
            )
            .scalars()
            .all()
        )
    for tid in previous:
        prior = client.get("/api/v1/tasks/" + str(tid)).json()
        with admin.connect() as db:
            assert (
                db.execute(
                    text(
                        "SELECT count(*) FROM dispatch_jobs WHERE run_id=:r AND (attempts>0 OR claim_owner IS NOT NULL)"
                    ),
                    {"r": prior["active_run_id"]},
                ).scalar_one()
                == 0
            )
        write(
            client,
            "/tasks/" + str(tid) + "/actions",
            {
                "command": "cancel",
                "expected_revision": prior["revision"],
                "expected_run_id": prior["active_run_id"],
            },
            202,
        )
    engagement = write(
        client,
        "/engagements",
        {
            "title": "Compose environment verification DEMO",
            "is_demo": True,
            "goal": "No model; prove standby, cancellation and persistence",
        },
        201,
    )
    tasks = []
    for i in range(2):
        tasks.append(
            write(
                client,
                f"/engagements/{engagement['id']}/tasks",
                {
                    "request_id": str(uuid4()),
                    "task_key": f"offline-{i}",
                    "original_request": "Environment control check only; never invoke a model",
                    "owner_role": "fde",
                    "executor_role": "engineering",
                    "spec": {
                        "title": "OFFLINE control fixture",
                        "objective": "Verify local infrastructure",
                        "scope": "No Engineering execution",
                        "inputs": [],
                        "confirmed_rules": [],
                        "completion_criteria": ["Records survive restart"],
                        "dependencies": [],
                        "capability_versions": [],
                    },
                },
                201,
            )
        )

    def action(task, command, expected=202, **fields):
        result = write(
            client,
            "/tasks/" + task["id"] + "/actions",
            {
                "command": command,
                "expected_revision": task["revision"],
                "expected_run_id": task["active_run_id"],
                **fields,
            },
            expected,
        )
        task.update(result["task"])
        return result

    for task in tasks:
        action(task, "queue")
    first = action(tasks[0], "start", model_profile_revision_id=profile)
    write(
        client,
        "/tasks/" + tasks[1]["id"] + "/actions",
        {
            "command": "start",
            "expected_revision": tasks[1]["revision"],
            "expected_run_id": None,
            "model_profile_revision_id": profile,
        },
        409,
    )
    time.sleep(2)
    with admin.connect() as db:
        job = (
            db.execute(
                text(
                    "SELECT state,attempts,claim_owner,runtime_ref FROM dispatch_jobs WHERE run_id=:r"
                ),
                {"r": first["run"]["id"]},
            )
            .mappings()
            .one()
        )
        assert (
            job["state"] == "pending"
            and job["attempts"] == 0
            and job["claim_owner"] is None
            and job["runtime_ref"] is None
        )
    report["checks"].extend(
        [
            "unauthenticated HTTP denied; authenticated create works",
            "two tasks cannot create parallel active Runs",
            "model-disabled standby leaves queued job unclaimed (attempts=0)",
        ]
    )
    action(tasks[0], "cancel")
    action(tasks[1], "cancel")
    report["task_ids"] = [t["id"] for t in tasks]
    report["run_id"] = first["run"]["id"]
    assert (
        client.get("/api/v1/runs/" + first["run"]["id"]).json()["state"] == "cancelled"
    )
    before = [client.get("/api/v1/tasks/" + t["id"]).json() for t in tasks]
    saved = json.loads((EVIDENCE / "environment.json").read_text())["artifact"]
    archive = Path("/srv/onefde-local/worker/artifacts") / saved["key"]
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == saved["sha256"]
    subprocess.run(
        COMPOSE + ["restart", "postgres", "api", "worker", "egress"], check=True
    )
    for _ in range(60):
        try:
            if (
                client.get("/health").status_code == 200
                and client.get("/api/v1/tasks/" + tasks[0]["id"]).status_code == 200
            ):
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    after = [client.get("/api/v1/tasks/" + t["id"]).json() for t in tasks]
    assert before == after
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == saved["sha256"]
    assert (
        client.get("/api/v1/runs/" + first["run"]["id"]).json()["state"] == "cancelled"
    )
    assert (
        client.post(
            "/api/v1/auth/logout", headers={"Content-Type": "application/json"}
        ).status_code
        == 204
    )
report["checks"].append(
    "core Compose restarted; authenticated Task/Run and immutable artifact digest unchanged"
)
admin.dispose()
(EVIDENCE / "control.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
