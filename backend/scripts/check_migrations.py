"""Verify full migrations in a newly created disposable PostgreSQL database.

Needs CREATE DATABASE permission on the isolated test server. Never clears an
existing database. The unique database created by this command is dropped finally.
"""

import json
import os
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def main():
    load_dotenv()
    source = make_url(os.environ["ONEFDE_TEST_DATABASE_URL"])
    if not source.database.endswith("_test") or str(source) == str(
        make_url(os.environ["ONEFDE_DATABASE_URL"])
    ):
        raise SystemExit("Requires dedicated *_test database server")
    database = f"onefde_c2_{uuid4().hex[:12]}_test"
    target = source.set(database=database)
    admin = create_engine(source, isolation_level="AUTOCOMMIT", hide_parameters=True)
    previous = os.environ.get("ONEFDE_DATABASE_URL")
    created = False
    try:
        with admin.connect() as db:
            db.execute(text(f'CREATE DATABASE "{database}"'))
            created = True
        os.environ["ONEFDE_DATABASE_URL"] = target.render_as_string(hide_password=False)
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        command.check(config)
        engine = create_engine(target, hide_parameters=True)
        with engine.connect() as db:
            head = db.scalar(text("SELECT version_num FROM alembic_version"))
            tables = db.scalars(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
                )
            ).all()
            postgres = db.scalar(text("SHOW server_version"))
        engine.dispose()
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        command.check(config)
        evidence = {
            "head": head,
            "tables": tables,
            "postgres": postgres,
            "fresh_database": True,
            "empty_downgrade_and_upgrade": True,
            "drift": False,
        }
        Path("work").mkdir(exist_ok=True)
        Path("work/c2-migration-evidence.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )
        print(json.dumps(evidence))
    finally:
        if previous is None:
            os.environ.pop("ONEFDE_DATABASE_URL", None)
        else:
            os.environ["ONEFDE_DATABASE_URL"] = previous
        if created:
            with admin.connect() as db:
                db.execute(text(f'DROP DATABASE "{database}" WITH (FORCE)'))
        admin.dispose()


if __name__ == "__main__":
    main()
