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
mimo_path = Path("/run/secrets/mimo_api_key")
assert stat.S_IMODE(mimo_path.stat().st_mode) == 0o600
mimo_key = mimo_path.read_text().strip()
assert os.environ.get("ONEFDE_MODEL_ENGINEERING_MIMO") == mimo_key
assert not mimo_key or key != mimo_key
standby_verified = False
for process in Path("/proc").iterdir():
    if not process.name.isdigit():
        continue
    try:
        command = (process / "cmdline").read_bytes().split(b"\0")
        if b"onefde.entrypoints.worker" in command and b"standby" in command:
            environment = (process / "environ").read_bytes().split(b"\0")
            assert b"ONEFDE_MODEL_ENGINEERING=" + key.encode() in environment
            assert b"ONEFDE_MODEL_ENGINEERING_MIMO=" + mimo_key.encode() in environment
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
        mimo_profiles = db.scalars(
            select(ModelProfileRevision).where(ModelProfileRevision.provider == "mimo")
        ).all()
        mimo_revisions = [
            str(row.revision_id)
            for row in mimo_profiles
            if row.config.get("secret_ref") == "env:ONEFDE_MODEL_ENGINEERING_MIMO"
            and row.config.get("base_url") == "https://api.xiaomimimo.com/v1"
            and row.integration_status == "configured"
        ]
        assert mimo_revisions
        assert all(
            "api_key" not in row.config
            and key not in json.dumps(row.config)
            and (not mimo_key or mimo_key not in json.dumps(row.config))
            for row in [*matched, *mimo_profiles]
        )
finally:
    engine.dispose()
print(
    json.dumps(
        {
            "key_loaded_in_standby_process": True,
            "secret_mode": "600",
            "profile_revision_ids": revisions,
            "mimo_profile_revision_ids": mimo_revisions,
            "mimo_key_configured": bool(mimo_key),
            "database_contains_references_only": True,
            "model_execution_enabled": False,
            "model_called": False,
        }
    )
)
