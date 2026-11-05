"""Configure a fresh disposable local control instance, without model access.

Run from backend with its locked venv. Credentials stay in private local files.
Refuse existing configuration; never overwrite or reset an existing database.
"""

import os
import secrets
import subprocess
from pathlib import Path

from argon2 import PasswordHasher
from sqlalchemy import create_engine, text

backend = Path.cwd()
if backend != Path("/home/onefde/OneFDE/backend"):
    raise SystemExit("Run in the dedicated OneFDE WSL backend directory")
for filename in (".env", ".env.worker"):
    if Path(filename).exists():
        raise SystemExit("Existing configuration found; inspect it, do not reset")
os.umask(0o077)
admin_password = secrets.token_hex(24)
worker_password = secrets.token_hex(24)
owner_password = secrets.token_urlsafe(24)
base = "postgresql+psycopg://"
admin_url = f"{base}onefde:{admin_password}@127.0.0.1:55433/onefde_wsl_dev"
worker_url = f"{base}onefde_worker:{worker_password}@127.0.0.1:55433/onefde_wsl_dev"
Path(".env").write_text(
    f"POSTGRES_PASSWORD={admin_password}\n"
    f"ONEFDE_DATABASE_URL={admin_url}\n"
    f"ONEFDE_TEST_DATABASE_URL={admin_url.replace('onefde_wsl_dev', 'onefde_wsl_test')}\n"
    "ONEFDE_ENVIRONMENT=development\nONEFDE_OWNER_USERNAME=founder\n"
    f"ONEFDE_OWNER_PASSWORD_HASH='{PasswordHasher().hash(owner_password)}'\n"
    "ONEFDE_TRUSTED_ORIGIN=http://127.0.0.1:8001\nONEFDE_COOKIE_SECURE=false\n",
    encoding="utf-8",
)
Path("/home/onefde/private/owner-password").write_text(owner_password + "\n")
Path(".env.worker").write_text(
    f"ONEFDE_WORKER_DATABASE_URL={worker_url}\n"
    "ONEFDE_WORKER_EXECUTION_MODE=local_wsl\n"
    "ONEFDE_WORKER_LOCAL_DEVELOPMENT_CONFIRMED=true\n"
    "ONEFDE_WORKER_ISOLATED_HOST_CONFIRMED=false\n"
    "ONEFDE_WORKER_MODEL_EXECUTION_ENABLED=false\n"
    "ONEFDE_WORKER_WORKER_ID=local-wsl-engineering\n"
    "ONEFDE_WORKER_ROOT=/home/onefde/runtime\n"
    "ONEFDE_WORKER_NETWORK=onefde-engineering-offline\n"
    "ONEFDE_WORKER_MAX_SECONDS=900\nONEFDE_WORKER_MAX_REQUESTS=20\n"
    "ONEFDE_WORKER_CPUS=1\nONEFDE_WORKER_MEMORY=2g\n"
    "ONEFDE_WORKER_PIDS_LIMIT=256\n",
    encoding="utf-8",
)
subprocess.run(
    [
        "docker",
        "compose",
        "--env-file",
        ".env",
        "-f",
        "local-wsl/compose.yaml",
        "up",
        "-d",
        "--wait",
    ],
    check=True,
)
subprocess.run(
    ["uv", "run", "--locked", "--extra", "worker", "alembic", "upgrade", "head"],
    check=True,
)
engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
with engine.connect() as db:
    # Generated password is hexadecimal; no user-provided SQL interpolation.
    db.execute(
        text(
            f"CREATE ROLE onefde_worker LOGIN PASSWORD '{worker_password}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION"
        )
    )
    db.execute(text("REVOKE CONNECT ON DATABASE onefde_wsl_dev FROM PUBLIC"))
    db.execute(text("GRANT CONNECT ON DATABASE onefde_wsl_dev TO onefde_worker"))
    db.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
    db.execute(text("GRANT USAGE ON SCHEMA public TO onefde_worker"))
    db.execute(
        text(
            "GRANT SELECT ON engagements, tasks, task_versions, task_inputs, task_reviews, task_events, runs, run_events, artifacts, model_profile_revisions, dispatch_jobs TO onefde_worker"
        )
    )
    db.execute(text("GRANT UPDATE ON tasks, runs, dispatch_jobs TO onefde_worker"))
    db.execute(
        text(
            "GRANT INSERT ON task_inputs, task_events, run_events, artifacts TO onefde_worker"
        )
    )
    db.execute(text("CREATE DATABASE onefde_wsl_test"))
    db.execute(text("REVOKE CONNECT ON DATABASE onefde_wsl_test FROM PUBLIC"))
engine.dispose()
print(
    "Local development database and restricted Worker configured; model execution disabled."
)
