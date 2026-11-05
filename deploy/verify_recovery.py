"""After restarting ONLY OneFDE WSL: verify previous records, disk and rules."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import httpx

evidence = Path("/srv/onefde-local/worker/evidence")
private = Path("/srv/onefde-local/private")
root = Path(__file__).resolve().parents[1]
compose = [
    "docker",
    "compose",
    "--env-file",
    str(private / "compose.env"),
    "-f",
    str(root / "deploy/compose.yaml"),
]
control = json.loads((evidence / "control.json").read_text())
environment = json.loads((evidence / "environment.json").read_text())
stat = os.statvfs(evidence)
assert stat.f_blocks * stat.f_frsize <= 2 * 1024**3
archive = Path("/srv/onefde-local/worker/artifacts") / environment["artifact"]["key"]
assert (
    hashlib.sha256(archive.read_bytes()).hexdigest()
    == environment["artifact"]["sha256"]
)
subprocess.run(["mountpoint", "-q", "/srv/onefde-local/worker"], check=True)
with httpx.Client(
    base_url="http://127.0.0.1:8002",
    headers={"Origin": "http://127.0.0.1:8002"},
    trust_env=False,
    timeout=10,
) as client:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": "founder",
            "password": (private / "owner_password").read_text().strip(),
        },
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    for tid in control["task_ids"]:
        assert client.get("/api/v1/tasks/" + tid).json()["state"] == "cancelled"
    assert (
        client.get("/api/v1/runs/" + control["run_id"]).json()["state"] == "cancelled"
    )
    assert (
        client.post(
            "/api/v1/auth/logout", headers={"Content-Type": "application/json"}
        ).status_code
        == 204
    )
checks = {}
for mode, expected in [("check", 0), ("execution-check", 2)]:
    result = subprocess.run(
        compose + ["exec", "-T", "worker", "python", "/app/ops/launch.py", mode],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == expected, (
        result.returncode,
        result.stdout,
        result.stderr,
    )
    checks[mode] = {"exit_code": result.returncode, "report": json.loads(result.stdout)}
containers = json.loads(
    subprocess.check_output(
        [
            "docker",
            "inspect",
            "onefde-local-api-1",
            "onefde-local-worker-1",
            "onefde-local-postgres-1",
            "onefde-wsl-postgres-1",
        ],
        text=True,
    )
)
for item in containers:
    assert item["State"]["Health"]["Status"] == "healthy"
report = {
    "model_called": False,
    "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
    "persistent_task_ids": control["task_ids"],
    "persistent_run_id": control["run_id"],
    "artifact_sha256": environment["artifact"]["sha256"],
    "bounded_filesystem_bytes": stat.f_blocks * stat.f_frsize,
    "preflight": checks,
    "services": [
        {
            "name": v["Name"],
            "image": v["Image"],
            "started_at": v["State"]["StartedAt"],
            "health": v["State"]["Health"]["Status"],
            "ports": v["NetworkSettings"]["Ports"],
        }
        for v in containers
    ],
}
(evidence / "recovery.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n"
)
print(
    json.dumps(
        {
            "persistent_records": True,
            "bounded_disk": True,
            "services_healthy": True,
            "environment_preflight": 0,
            "execution_preflight": 2,
            "model_called": False,
        }
    )
)
