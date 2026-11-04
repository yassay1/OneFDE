import platform
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AGENT_SERVER_IMAGE = "ghcr.io/openhands/agent-server:1.59.0-python@sha256:96038f92dc66228e389a95c2e5081dfc2cd4f5d307f051a7df9b1d50ccb86be7"
SDK_VERSION = "1.59.0"


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.worker",
        env_prefix="ONEFDE_WORKER_",
        extra="ignore",
        hide_input_in_errors=True,
    )
    database_url: SecretStr | None = None
    worker_id: str = Field(default="engineering-1", min_length=1, max_length=128)
    root: Path | None = None
    isolated_host_confirmed: bool = False
    network: str | None = None
    server_image: str = AGENT_SERVER_IMAGE
    lease_seconds: int = Field(default=120, ge=3, le=3600)
    heartbeat_seconds: float = Field(default=5, ge=0.1, le=60)
    poll_seconds: float = Field(default=1, ge=0.1, le=10)
    max_seconds: int = Field(default=900, ge=1, le=900)
    max_requests: int = Field(default=20, ge=1, le=20)
    max_cost_usd: float | None = Field(default=None, gt=0)
    cpus: float = Field(default=1, gt=0, le=8)
    memory: str = Field(default="2g", pattern=r"^[1-9][0-9]*[mg]$")
    pids_limit: int = Field(default=256, ge=32, le=1024)
    max_artifact_bytes: int = Field(
        default=64 * 1024 * 1024, ge=1024, le=512 * 1024 * 1024
    )

    @model_validator(mode="after")
    def validate_configuration(self):
        if self.database_url and not self.database_url.get_secret_value().startswith(
            "postgresql+psycopg://"
        ):
            raise ValueError("Worker database must use psycopg PostgreSQL")
        if self.lease_seconds < self.heartbeat_seconds * 3:
            raise ValueError("lease must exceed three heartbeat intervals")
        if self.server_image != AGENT_SERVER_IMAGE:
            raise ValueError(
                "C2 requires the reviewed SDK-compatible pinned Agent Server image"
            )
        return self

    def blockers(self):
        issues = []
        if platform.system() != "Linux":
            issues.append("需要专用Linux执行节点，当前宿主不符合")
        if not self.isolated_host_confirmed:
            issues.append("尚未确认专用节点及隔离/出网策略")
        if not self.database_url:
            issues.append("缺少Worker受限数据库连接")
        if self.root is None or not self.root.is_absolute():
            issues.append("缺少绝对路径的Worker私有持久目录")
        if not self.network:
            issues.append("缺少工程容器隔离网络")
        if self.max_cost_usd is None:
            issues.append("缺少明确的模型费用上限及提供方配额")
        return issues
