"""Real loopback HTTP against two separate API processes, preserving PostgreSQL data.

Run after Alembic upgrade: uv run --locked python -m scripts.http_smoke
Creates explicitly simulated records in the configured development database.
"""

import argparse
import getpass
import json
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

from onefde.core.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--password-file",
        type=Path,
        help="Only for disposable local verification credentials",
    )
    args = parser.parse_args()
    settings = Settings()
    if settings.environment != "development" or settings.cookie_secure:
        parser.error("Smoke requires explicit development HTTP cookie configuration")
    password = (
        args.password_file.read_text().strip()
        if args.password_file
        else getpass.getpass("Founder password: ")
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    work = ROOT / "work"
    work.mkdir(exist_ok=True)
    evidence = {"started_at": datetime.now(UTC).isoformat(), "checks": []}

    def check(response, status, label):
        assert response.status_code == status, (
            label,
            response.status_code,
            response.text,
        )
        evidence["checks"].append({"check": label, "status": status})
        return response.json() if response.content else None

    def start(log):
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
            cwd=ROOT,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError("API exited; inspect work/http-smoke-server.log")
            try:
                if httpx.get(base + "/health", timeout=0.3).status_code == 200:
                    return process
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        process.terminate()
        process.wait(timeout=10)
        raise RuntimeError("API did not become ready")

    def stop(process):
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)

    with (
        (work / "http-smoke-server.log").open("w", encoding="utf-8") as log,
        httpx.Client(base_url=base, timeout=10) as client,
    ):
        process = start(log)
        try:
            evidence["first_process_id"] = process.pid
            assert client.get("/docs").status_code == 200
            evidence["checks"].append(
                {"check": "development API docs available", "status": 200}
            )
            check(client.get("/api/v1/engagements"), 401, "unauthenticated rejected")
            origin = {"Origin": settings.trusted_origin}
            session = check(
                client.post(
                    "/api/v1/auth/login",
                    json={"username": settings.owner_username, "password": password},
                    headers=origin,
                ),
                200,
                "login",
            )
            headers = {
                **origin,
                "X-CSRF-Token": session["csrf_token"],
                "Idempotency-Key": str(uuid4()),
            }
            check(client.get("/api/v1/auth/session"), 200, "session retrieval")
            payload = {
                "title": "C0+C1a HTTP 模拟验证",
                "is_demo": True,
                "goal": "证明草稿持久化，不运行 Agent",
            }
            check(
                client.post(
                    "/api/v1/engagements",
                    json=payload,
                    headers={**headers, "X-CSRF-Token": "wrong"},
                ),
                403,
                "invalid CSRF rejected",
            )
            engagement = check(
                client.post("/api/v1/engagements", json=payload, headers=headers),
                201,
                "create engagement",
            )
            assert (
                check(
                    client.post("/api/v1/engagements", json=payload, headers=headers),
                    201,
                    "engagement replay",
                )
                == engagement
            )
            check(
                client.post(
                    "/api/v1/engagements",
                    json={**payload, "goal": "changed"},
                    headers=headers,
                ),
                409,
                "idempotency conflict",
            )
            eid = engagement["id"]
            spec = {
                "title": "模拟工程草稿",
                "objective": "检查控制接口",
                "scope": "仅草稿",
                "inputs": ["模拟输入"],
                "confirmed_rules": [],
                "completion_criteria": ["重启后可查回"],
                "dependencies": [],
                "capability_versions": [],
            }
            task_payload = {
                "request_id": str(uuid4()),
                "task_key": "first-engineering",
                "original_request": "创建草稿",
                "spec": spec,
                "owner_role": "fde",
                "executor_role": "engineering",
            }
            task = check(
                client.post(
                    f"/api/v1/engagements/{eid}/tasks",
                    json=task_payload,
                    headers=headers,
                ),
                201,
                "create draft engineering task",
            )
            assert task["state"] == "draft" and task["active_run_id"] is None
            assert (
                check(
                    client.post(
                        f"/api/v1/engagements/{eid}/tasks",
                        json=task_payload,
                        headers=headers,
                    ),
                    201,
                    "task replay",
                )
                == task
            )
            check(
                client.post(
                    "/api/v1/engagements",
                    json={**payload, "title": ""},
                    headers={**headers, "Idempotency-Key": str(uuid4())},
                ),
                422,
                "invalid input",
            )
            check(client.get(f"/api/v1/tasks/{uuid4()}"), 404, "missing task")
            stop(process)
            process = start(log)
            evidence["second_process_id"] = process.pid
            assert evidence["first_process_id"] != process.pid
            assert (
                check(
                    client.get(f"/api/v1/engagements/{eid}"),
                    200,
                    "engagement survives process restart",
                )
                == engagement
            )
            assert (
                check(
                    client.get(f"/api/v1/tasks/{task['id']}"),
                    200,
                    "task survives process restart",
                )
                == task
            )
            check(client.get("/api/v1/engagements"), 200, "list engagements")
            tasks = check(
                client.get(f"/api/v1/engagements/{eid}/tasks"), 200, "list tasks"
            )
            assert tasks["items"] == [task]
            assert (
                check(
                    client.post(
                        f"/api/v1/engagements/{eid}/tasks",
                        json=task_payload,
                        headers=headers,
                    ),
                    201,
                    "idempotency survives restart",
                )
                == task
            )
            check(
                client.post(
                    "/api/v1/auth/logout",
                    headers={**headers, "Content-Type": "application/json"},
                ),
                204,
                "logout",
            )
            check(client.get("/api/v1/auth/session"), 401, "revoked session rejected")
            evidence.update(
                engagement=engagement,
                task=task,
                completed_at=datetime.now(UTC).isoformat(),
                result="passed",
            )
            (work / "http-smoke.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(
                f"Passed {len(evidence['checks'])} HTTP checks, two separate API processes; work/http-smoke.json"
            )
        finally:
            stop(process)


if __name__ == "__main__":
    main()
