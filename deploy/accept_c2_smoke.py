"""Founder accept of the authorized C2 webpage smoke submission."""

import json
from pathlib import Path
from uuid import uuid4

import httpx

PRIVATE = Path("/srv/onefde-local/private")
BASE = "http://127.0.0.1:8002"
evidence = json.loads(Path("work/c2-webpage-smoke.json").read_text())
task_id = evidence["task_id"]
run_id = evidence["run_id"]
artifact_id = evidence["artifacts"][0]["id"]

with httpx.Client(
    base_url=BASE, trust_env=False, timeout=30, headers={"Origin": BASE}
) as client:
    login = client.post(
        "/api/v1/auth/login",
        json={
            "username": "founder",
            "password": (PRIVATE / "owner_password").read_text().strip(),
        },
    )
    assert login.status_code == 200
    client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
    task = client.get(f"/api/v1/tasks/{task_id}").json()
    review = client.post(
        f"/api/v1/tasks/{task_id}/reviews",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "expected_revision": task["revision"],
            "run_id": run_id,
            "task_spec_version": task["spec_version"],
            "artifact_ids": [artifact_id],
            "verdict": "accept",
            "reason": "C2 smoke: heading and automatic check verified",
            "check_evidence": [
                "sh /workspace/check.sh exit 0 during Engineering",
                "fixed-source validation passed with unchanged digest",
                "index.html contains <h1>OneFDE C2 Smoke</h1>",
            ],
        },
    )
    assert review.status_code == 201, review.text
    body = review.json()
    final = client.get(f"/api/v1/tasks/{task_id}").json()
print(
    json.dumps(
        {
            "task_id": task_id,
            "run_id": run_id,
            "review": body.get("review") or body,
            "task_state": final["state"],
            "verdict": "accept",
        }
    )
)
