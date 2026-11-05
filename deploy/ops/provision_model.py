"""Idempotent non-secret profile provisioning; privileged short job, no LLM."""

import json
import os
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from onefde.modules.tasks.configuration import ModelConfiguration, provision_model
from onefde.modules.tasks.models import ModelProfileRevision

config = ModelConfiguration.model_validate_json(
    Path("/run/config/deepseek-profile.json").read_text()
)
url = os.environ["ONEFDE_WORKER_DATABASE_URL"]
if not url.endswith("/onefde_compose_dev"):
    raise SystemExit("Local Compose configuration only")
engine = create_engine(url, hide_parameters=True)
try:
    with Session(engine) as db, db.begin():
        values = config.model_dump()
        provider, model = values.pop("provider"), values.pop("model")
        fixed = {"adapter": "openhands", **values}
        existing = db.scalar(
            select(ModelProfileRevision).where(
                ModelProfileRevision.provider == provider,
                ModelProfileRevision.model == model,
                ModelProfileRevision.config == fixed,
            )
        )
        identifier = existing.revision_id if existing else provision_model(db, config)
    print(
        json.dumps(
            {
                "revision_id": str(identifier),
                "integration_status": "configured",
                "reused": existing is not None,
                "model_called": False,
            }
        )
    )
finally:
    engine.dispose()
