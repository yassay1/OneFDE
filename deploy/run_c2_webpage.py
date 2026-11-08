"""One authorized C2 webpage smoke: real Backend → Worker → Engineering → model.

Uses Compose API + host Worker with latest source. Does not print secrets.
Requires an explicit ONEFDE_WORKER_MAX_COST_USD budget.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path("/srv/onefde-local/private")
EVIDENCE = Path("/srv/onefde-local/worker/evidence")
BASE = "http://127.0.0.1:8002"
COST = float(os.environ["ONEFDE_WORKER_MAX_COST_USD"])
assert 0 < COST <= 5, "Smoke cost ceiling must be positive and at most 5 USD"
PROVIDER = os.environ.get("ONEFDE_SMOKE_PROVIDER", "deepseek")
MODEL, SECRET = {
    "deepseek": ("deepseek-flash", "ONEFDE_MODEL_ENGINEERING"),
    "mimo": ("mimo-v2.6-pro", "ONEFDE_MODEL_ENGINEERING_MIMO"),
}[PROVIDER]
RETRY_TASK = os.environ.get("ONEFDE_SMOKE_RETRY_TASK_ID")
REQUESTS = int(os.environ.get("ONEFDE_WORKER_MAX_REQUESTS", "20"))
assert 3 <= REQUESTS <= 20
OUTPUT_NAME = (
    "c2-webpage-smoke.json" if PROVIDER == "deepseek" else "c2-mimo-webpage-smoke.json"
)

report = {
    "scope": "c2_real_webpage_smoke",
    "checked_at_utc": datetime.now(UTC).isoformat(),
    "model_provider": PROVIDER,
    "max_cost_usd": COST,
    "model_called": True,
    "steps": [],
}


def step(name, **fields):
    report["steps"].append({"name": name, **fields})


def write(client, path, body, expected=200):
    response = client.post(
        "/api/v1" + path,
        json=body,
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == expected, (path, response.status_code, response.text)
    return response.json()


# Resolve the selected provider's profile revision (references only).
admin = create_engine(
    (PRIVATE / "admin_url").read_text().strip().replace("@postgres:", "@172.29.240.3:"),
    hide_parameters=True,
)
with Session(admin) as db:
    from onefde.modules.tasks.models import ModelProfileRevision

    profile = db.scalar(
        select(ModelProfileRevision)
        .where(
            ModelProfileRevision.provider == PROVIDER,
            ModelProfileRevision.model == "openai/" + MODEL,
            ModelProfileRevision.integration_status == "configured",
        )
        .limit(1)
    )
    assert profile is not None, "Selected model profile revision missing"
    revision_id = str(profile.revision_id)
    report["model_profile_revision_id"] = revision_id
    report["model"] = profile.model
admin.dispose()

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
    assert login.status_code == 200, login.text
    client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
    if RETRY_TASK:
        response = client.get(f"/api/v1/tasks/{RETRY_TASK}")
        response.raise_for_status()
        task = response.json()
        assert task["state"] == "blocked", "Retry requires a stopped blocked smoke task"
        assert task["spec"]["title"] == "Static demo page"
        queued = {"task": task}
        engagement = {"id": task["engagement_id"]}
    else:
        engagement = write(
            client,
            "/engagements",
            {
                "title": f"C2 {PROVIDER} webpage smoke DEMO",
                "is_demo": True,
                "goal": "Authorized real-model Engineering smoke; not supplier quotes",
            },
            201,
        )
        task = write(
            client,
            f"/engagements/{engagement['id']}/tasks",
            {
                "request_id": str(uuid4()),
                "task_key": "c2-webpage-" + datetime.now(UTC).strftime("%H%M%S"),
                "original_request": (
                    "Create a tiny static demo page and a check script under /workspace. "
                    "Do not ask business questions."
                ),
                "owner_role": "fde",
                "executor_role": "engineering",
                "spec": {
                    "title": "Static demo page",
                    "objective": (
                        "Create /workspace/index.html containing the exact heading "
                        "<h1>OneFDE C2 Smoke</h1> and a short paragraph stating this is a "
                        "local demo page. Also create /workspace/check.sh that exits 0 only "
                        "when that heading is present."
                    ),
                    "scope": (
                        "Only index.html and check.sh under /workspace. No network installs, "
                        "no git remotes, no deployment, no secrets."
                    ),
                    "inputs": ["Local demo only; not customer data"],
                    "confirmed_rules": [
                        "Heading text must be exactly OneFDE C2 Smoke",
                        "check.sh must be executable via sh /workspace/check.sh",
                    ],
                    "completion_criteria": [
                        "[auto] sh /workspace/check.sh",
                        "[review] Page content matches the frozen demo heading",
                    ],
                    "dependencies": [],
                    "capability_versions": [],
                },
            },
            201,
        )
        queued = write(
            client,
            f"/tasks/{task['id']}/actions",
            {
                "command": "queue",
                "expected_revision": task["revision"],
                "expected_run_id": None,
            },
            202,
        )
    started = write(
        client,
        f"/tasks/{task['id']}/actions",
        {
            "command": "retry" if RETRY_TASK else "start",
            "expected_revision": queued["task"]["revision"],
            "expected_run_id": task["latest_run_id"] if RETRY_TASK else None,
            "model_profile_revision_id": revision_id,
        },
        202,
    )
    run_id = started["run"]["id"]
    report["engagement_id"] = engagement["id"]
    report["task_id"] = task["id"]
    report["run_id"] = run_id
    step("http_start", state=started["run"]["state"], http_status=202)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / f"{run_id}-start.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps({"task_id": task["id"], "run_id": run_id, "state": "queued"}),
        flush=True,
    )

worker_url = (
    (PRIVATE / "worker_url").read_text().strip().replace("@postgres:", "@172.29.240.3:")
)
env = os.environ.copy()
env.update(
    {
        "ONEFDE_WORKER_DATABASE_URL": worker_url,
        "ONEFDE_WORKER_ROOT": "/srv/onefde-local/worker",
        "ONEFDE_WORKER_NETWORK": "onefde-local-sandbox",
        "ONEFDE_WORKER_EXECUTION_MODE": "ecs_shared",
        "ONEFDE_WORKER_SHARED_HOST_CONFIRMED": "true",
        "ONEFDE_WORKER_ISOLATED_HOST_CONFIRMED": "false",
        "ONEFDE_WORKER_MODEL_EXECUTION_ENABLED": "true",
        "ONEFDE_WORKER_MAX_COST_USD": str(COST),
        "ONEFDE_WORKER_EGRESS_PROXY_URL": "http://172.29.241.3:3128",
        "ONEFDE_WORKER_WORKER_ID": "onefde-c2-smoke-once",
        "ONEFDE_WORKER_MAX_SECONDS": "900",
        "ONEFDE_WORKER_MAX_REQUESTS": str(REQUESTS),
        SECRET: (PRIVATE / f"{PROVIDER}_api_key").read_text().strip(),
        "OPENHANDS_SUPPRESS_BANNER": "1",
        "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        "HOME": "/tmp",
    }
)
# Drop any Windows proxy interference for the Worker process itself.
for name in (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
):
    env.pop(name, None)

preflight = subprocess.run(
    [
        str(ROOT / "backend/.venv/bin/python"),
        "-m",
        "onefde.entrypoints.worker",
        "check",
    ],
    cwd=str(ROOT / "backend"),
    env=env,
    capture_output=True,
    text=True,
    timeout=60,
    check=False,
)
step(
    "execution_preflight",
    exit_code=preflight.returncode,
    report=json.loads(preflight.stdout) if preflight.stdout.strip() else None,
)
if preflight.returncode != 0:
    Path("work").mkdir(exist_ok=True)
    path = Path("work/c2-webpage-blocked.json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {"blocked": True, "evidence": str(path), "exit": preflight.returncode}
        )
    )
    sys.exit(2)

started_at = time.monotonic()
stdout_log = EVIDENCE / f"{run_id}-worker.stdout.log"
stderr_log = EVIDENCE / f"{run_id}-worker.stderr.log"
with stdout_log.open("w") as output, stderr_log.open("w") as errors:
    stdout_log.chmod(0o600)
    stderr_log.chmod(0o600)
    worker = subprocess.run(
        [
            str(ROOT / "backend/.venv/bin/python"),
            "-m",
            "onefde.entrypoints.worker",
            "once",
            "--run-id",
            run_id,
        ],
        cwd=str(ROOT / "backend"),
        env=env,
        stdout=output,
        stderr=errors,
        text=True,
        timeout=960,
        check=False,
    )
elapsed = round(time.monotonic() - started_at, 2)
step(
    "worker_once",
    exit_code=worker.returncode,
    elapsed_seconds=elapsed,
    stdout_log=str(stdout_log),
    stderr_log=str(stderr_log),
)

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
    client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
    task_view = client.get(f"/api/v1/tasks/{report['task_id']}").json()
    run_view = client.get(f"/api/v1/runs/{report['run_id']}").json()
    artifacts = client.get(f"/api/v1/runs/{report['run_id']}/artifacts").json()
    events = client.get(f"/api/v1/runs/{report['run_id']}/events").json()

report["task_state"] = task_view["state"]
report["run"] = {
    "state": run_view["state"],
    "outcome": run_view.get("outcome"),
    "summary": run_view.get("result_summary"),
    "error_code": run_view.get("error_code"),
    "spec_version": run_view.get("task_spec_version"),
}
report["artifacts"] = [
    {
        "id": item["id"],
        "name": item["name"],
        "kind": item["kind"],
        "sha256": item["sha256"],
        "size_bytes": item["size_bytes"],
    }
    for item in artifacts.get("items", [])
]
report["event_kinds"] = [item.get("kind") for item in events.get("items", [])]

# Job proof from DB (no secrets).
worker_db = create_engine(worker_url, hide_parameters=True)
with worker_db.connect() as db:
    row = (
        db.execute(
            text(
                "SELECT result_payload, runtime_ref, attempts, claim_owner "
                "FROM dispatch_jobs WHERE run_id = CAST(:r AS uuid)"
            ),
            {"r": report["run_id"]},
        )
        .mappings()
        .one()
    )
payload = row["result_payload"] or {}
proof = payload.get("proof") or {}
report["dispatch"] = {
    "attempts": row["attempts"],
    "claim_owner": row["claim_owner"],
    "runtime_roles": [
        item.get("role") for item in (row["runtime_ref"] or {}).get("resources", [])
    ]
    if isinstance(row["runtime_ref"], dict)
    else row["runtime_ref"],
    "stopped": proof.get("stopped"),
    "source_digest": proof.get("source_digest"),
    "check_coverage": proof.get("check_coverage"),
    "validation": {
        key: proof.get("validation", {}).get(key)
        for key in (
            "passed",
            "stopped",
            "source_unchanged",
            "error_code",
            "results",
        )
    }
    if proof.get("validation")
    else None,
    "context_revisions": proof.get("context_revisions"),
}
worker_db.dispose()

workspace = Path("/srv/onefde-local/worker/tasks") / report["task_id"] / "workspace"
report["workspace_files"] = (
    sorted(
        p.relative_to(workspace).as_posix()
        for p in workspace.rglob("*")
        if p.is_file() and "bash_events" not in p.parts
    )
    if workspace.exists()
    else []
)
if (workspace / "index.html").is_file():
    text = (workspace / "index.html").read_text(encoding="utf-8", errors="replace")
    report["index_has_heading"] = "<h1>OneFDE C2 Smoke</h1>" in text
    report["index_preview"] = text[:500]

EVIDENCE.mkdir(parents=True, exist_ok=True)
out = EVIDENCE / OUTPUT_NAME
public = Path("work")
public.mkdir(exist_ok=True)
public_out = public / OUTPUT_NAME
blob = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
out.write_text(blob, encoding="utf-8")
public_out.write_text(blob, encoding="utf-8")
success = (
    report["run"]["state"] == "completed"
    and report["run"]["outcome"] == "submitted"
    and report.get("index_has_heading") is True
    and proof.get("stopped") is True
    and (proof.get("validation") or {}).get("passed") is True
)
print(
    json.dumps(
        {
            "success": success,
            "task_id": report["task_id"],
            "run_id": report["run_id"],
            "task_state": report["task_state"],
            "run_state": report["run"]["state"],
            "outcome": report["run"]["outcome"],
            "evidence": str(public_out),
            "elapsed_seconds": elapsed,
            "max_cost_usd": COST,
        }
    )
)
sys.exit(0 if success else 1)
