from datetime import datetime

from pydantic import BaseModel, Field, SecretStr

from onefde.core.schemas import Input


class Login(Input):
    username: str = Field(min_length=1, max_length=128)
    password: SecretStr = Field(
        min_length=1, max_length=1024, json_schema_extra={"writeOnly": True}
    )


class OwnerSession(BaseModel):
    username: str
    csrf_token: str
    expires_at: datetime
