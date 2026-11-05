"""Idempotent setup of this isolated Compose DB, never an existing WSL DB."""

import os
from pathlib import Path

from psycopg import sql
from sqlalchemy import create_engine, text

url = os.environ["ONEFDE_DATABASE_URL"]
if not url.endswith("/onefde_compose_dev"):
    raise SystemExit("Refuse initialization outside the isolated Compose database")
engine = create_engine(url, isolation_level="AUTOCOMMIT", hide_parameters=True)
with engine.connect() as db:
    if not db.execute(
        text("SELECT 1 FROM pg_roles WHERE rolname='onefde_app'")
    ).scalar():
        db.execute(
            text(
                "CREATE ROLE onefde_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION"
            )
        )
        password = Path("/run/secrets/api_password").read_text().strip()
        with db.connection.driver_connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("ALTER ROLE onefde_app PASSWORD {}").format(
                    sql.Literal(password)
                )
            )
    if not db.execute(
        text("SELECT 1 FROM pg_roles WHERE rolname='onefde_worker'")
    ).scalar():
        db.execute(
            text(
                "CREATE ROLE onefde_worker LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION"
            )
        )
        password = Path("/run/secrets/worker_password").read_text().strip()
        with db.connection.driver_connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("ALTER ROLE onefde_worker PASSWORD {}").format(
                    sql.Literal(password)
                )
            )
    db.execute(text("REVOKE CONNECT ON DATABASE onefde_compose_dev FROM PUBLIC"))
    db.execute(text("GRANT CONNECT ON DATABASE onefde_compose_dev TO onefde_worker"))
    db.execute(text("GRANT CONNECT ON DATABASE onefde_compose_dev TO onefde_app"))
    db.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
    db.execute(text("GRANT USAGE ON SCHEMA public TO onefde_worker"))
    db.execute(text("GRANT USAGE ON SCHEMA public TO onefde_app"))
    db.execute(text("GRANT SELECT ON ALL TABLES IN SCHEMA public TO onefde_app"))
    db.execute(
        text(
            "GRANT INSERT,UPDATE,DELETE ON auth_sessions,login_attempts,idempotency_records,engagements,tasks,task_inputs,task_reviews,task_versions,task_events,runs,run_events,dispatch_jobs,artifacts TO onefde_app"
        )
    )
    db.execute(
        text(
            "GRANT SELECT ON engagements,tasks,task_versions,task_inputs,task_reviews,task_events,runs,run_events,artifacts,model_profile_revisions,dispatch_jobs TO onefde_worker"
        )
    )
    db.execute(text("GRANT UPDATE ON tasks,runs,dispatch_jobs TO onefde_worker"))
    db.execute(
        text(
            "GRANT INSERT ON task_inputs,task_events,run_events,artifacts TO onefde_worker"
        )
    )
engine.dispose()
print("Isolated Compose database initialized; Worker has no auth/DDL/admin privileges.")
