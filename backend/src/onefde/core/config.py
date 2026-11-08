from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from argon2 import extract_parameters
from argon2.low_level import Type
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="ONEFDE_", extra="ignore", hide_input_in_errors=True
    )
    environment: Literal["development", "production"] = "production"
    database_url: SecretStr
    owner_username: str = Field(min_length=1, max_length=128)
    owner_password_hash: SecretStr
    trusted_origin: str
    business_amap_key: SecretStr | None = None
    business_customer_origin: str = "http://127.0.0.1:8765"
    session_hours: int = Field(default=8, ge=1, le=24)
    cookie_secure: bool = True
    login_limit: int = Field(default=10, ge=1, le=100)
    staff_chat_mode: Literal["scripted", "live"] = "scripted"
    staff_model_revision_id: UUID | None = None

    @model_validator(mode="after")
    def check_security(self):
        if not self.database_url.get_secret_value().startswith("postgresql+psycopg://"):
            raise ValueError("database_url must use postgresql+psycopg")
        try:
            params = extract_parameters(self.owner_password_hash.get_secret_value())
            if (
                params.type != Type.ID
                or params.memory_cost < 19456
                or params.time_cost < 2
            ):
                raise ValueError()
        except Exception:
            raise ValueError(
                "owner_password_hash must be a strong Argon2id hash"
            ) from None
        origin = urlsplit(self.trusted_origin)
        if (
            origin.scheme not in ("http", "https")
            or not origin.netloc
            or origin.path
            or origin.query
            or origin.fragment
            or origin.username
        ):
            raise ValueError("trusted_origin must be a single origin without path")
        if self.environment == "production" and (
            not self.cookie_secure or origin.scheme != "https"
        ):
            raise ValueError("production requires HTTPS and secure cookies")
        customer = urlsplit(self.business_customer_origin)
        if (
            customer.scheme not in ("http", "https")
            or not customer.hostname
            or customer.path
            or customer.query
            or customer.fragment
            or customer.username
            or self.business_customer_origin == self.trusted_origin
        ):
            raise ValueError("business_customer_origin must be an independent origin")
        return self

    @property
    def cookie_name(self):
        return "__Host-onefde_session" if self.cookie_secure else "onefde_dev_session"
