"""Private credential equality + restricted DB metadata check. Never invokes LLM."""

import json
import os
import stat
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from onefde.modules.tasks.models import ModelProfileRevision
from onefde.worker.config import WorkerSettings

settings = WorkerSettings()
assert not settings.model_execution_enabled
path = Path("/run/secrets/deepseek_api_key")
assert stat.S_IMODE(path.stat().st_mode) == 0o600
key = path.read_text().strip()
assert key and os.environ.get("ONEFDE_MODEL_ENGINEERING") == key
standby_verified = False
for process in Path("/proc").iterdir():
    if not process.name.isdigit():
        continue
    try:
        command = (process / "cmdline").read_bytes().split(b"\0")
        if b"onefde.entrypoints.worker" in command and b"standby" in command:
            assert b"ONEFDE_MODEL_ENGINEERING=" + key.encode() in (
                process / "environ"
            ).read_bytes().split(b"\0")
            standby_verified = True
    except (FileNotFoundError, PermissionError):
        continue
assert standby_verified
engine = create_engine(settings.database_url.get_secret_value(), hide_parameters=True)
try:
    with Session(engine) as db:
        profiles = db.scalars(
            select(ModelProfileRevision).where(
                ModelProfileRevision.provider == "deepseek"
            )
        ).all()
        matched = [
            row
            for row in profiles
            if row.config.get("secret_ref") == "env:ONEFDE_MODEL_ENGINEERING"
        ]
        assert matched
        assert all(
            "api_key" not in row.config and key not in json.dumps(row.config)
            for row in matched
        )
        revisions = [str(row.revision_id) for row in matched]
finally:
    engine.dispose()
print(
    json.dumps(
        {
            "key_loaded_in_standby_process": True,
            "secret_mode": "600",
            "profile_revision_ids": revisions,
            "database_contains_references_only": True,
            "model_execution_enabled": False,
            "model_called": False,
        }
    )
)
