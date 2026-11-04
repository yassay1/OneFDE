"""Trusted provisioning of immutable, non-secret model metadata (no model call)."""

import re
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from onefde.modules.tasks.models import ModelProfileRevision


class ModelConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    provider: str = Field(min_length=1, max_length=128)
    model: str = Field(pattern=r"^openai/[^\s]+$", max_length=200)
    base_url: str
    secret_ref: str = Field(pattern=r"^env:ONEFDE_MODEL_[A-Z0-9_]+$")
    max_requests: int = Field(default=20, ge=1, le=20, strict=True)
    timeout_seconds: int = Field(default=60, ge=1, le=120, strict=True)

    @model_validator(mode="after")
    def endpoint(self):
        endpoint = urlsplit(self.base_url)
        if (
            endpoint.scheme != "https"
            or not endpoint.hostname
            or any(
                (
                    endpoint.username,
                    endpoint.password,
                    endpoint.query,
                    endpoint.fragment,
                )
            )
        ):
            raise ValueError(
                "Model endpoint must be HTTPS without credentials or query"
            )
        if re.search(r"[\r\n]", self.base_url):
            raise ValueError("Invalid endpoint")
        return self


def provision_model(db, config):
    values = config.model_dump()
    row = ModelProfileRevision(
        provider=values.pop("provider"),
        model=values.pop("model"),
        config={"adapter": "openhands", **values},
        capabilities=[],
        integration_status="configured",
    )
    db.add(row)
    db.flush()
    return row.revision_id
