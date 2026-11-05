"""Trusted Compose secret loading. Never forward management secrets to Sandbox."""

import os
import sys
from pathlib import Path

for name in (
    "ONEFDE_DATABASE_URL",
    "ONEFDE_TEST_DATABASE_URL",
    "ONEFDE_OWNER_PASSWORD_HASH",
    "ONEFDE_WORKER_DATABASE_URL",
    "ONEFDE_MODEL_ENGINEERING",
):
    reference = os.environ.get(name + "_FILE")
    if reference:
        if not reference.startswith("/run/secrets/"):
            raise SystemExit("Secret must come from /run/secrets")
        os.environ[name] = Path(reference).read_text().strip()

commands = {
    "check": [
        "python",
        "-m",
        "onefde.entrypoints.worker",
        "check",
        "--environment-only",
    ],
    "execution-check": ["python", "-m", "onefde.entrypoints.worker", "check"],
    "api": [
        "uvicorn",
        "onefde.entrypoints.api:create_app",
        "--factory",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ],
    "worker": ["python", "-m", "onefde.entrypoints.worker", "standby"],
    "migrate": ["alembic", "upgrade", "head"],
    "initialize": ["python", "/app/ops/initialize.py"],
    "configure-model": ["python", "/app/ops/provision_model.py"],
    "model-check": ["python", "/app/ops/check_model.py"],
    "verify": ["python", "/app/ops/verify_inside.py"],
}
if len(sys.argv) != 2 or sys.argv[1] not in commands:
    raise SystemExit("Select an approved service command")
command = commands[sys.argv[1]]
os.execvp(command[0], command)
