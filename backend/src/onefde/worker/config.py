import os
import platform
from pathlib import Path
from typing import Literal

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
    execution_mode: Literal["dedicated", "local_wsl", "ecs_shared"] = "dedicated"
    local_development_confirmed: bool = False
    shared_host_confirmed: bool = False
    storage_limit_bytes: int = Field(default=2 * 1024**3, ge=64 * 1024**2)
    min_free_disk_bytes: int = Field(default=144 * 1024**2, ge=1024**2)
    min_free_memory_mb: int = Field(default=4096, ge=128)
    model_execution_enabled: bool = False
    network: str | None = None
    # Current shared-host Compose reserves this internal proxy address.
    egress_proxy_url: str | None = Field(
        default=None, pattern=r"^http://172\.29\.241\.3:3128$"
    )
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

    def blockers(self, *, environment_only=False):
        issues = []
        if platform.system() != "Linux":
            issues.append("Worker必须运行在Linux中")
        if self.execution_mode == "local_wsl":
            if "microsoft" not in platform.release().lower():
                issues.append("local_wsl模式必须运行在WSL2发行版中")
            if not self.local_development_confirmed:
                issues.append("尚未确认仅用于授权演示任务的本地开发环境")
            if self.root and str(self.root).startswith("/mnt/"):
                issues.append(
                    "本地工作目录必须位于Linux文件系统，不能使用Windows挂载目录"
                )
        elif self.execution_mode == "ecs_shared":
            if not self.shared_host_confirmed:
                issues.append("尚未确认共享宿主的容器/权限/资源边界")
            if self.isolated_host_confirmed:
                issues.append("共享宿主不能声明为独立执行节点")
            if self.root and str(self.root).startswith("/mnt/"):
                issues.append("共享宿主工作区不能使用Windows挂载路径")
        elif not self.isolated_host_confirmed:
            issues.append("尚未确认专用节点及隔离/出网策略")
        if not self.database_url:
            issues.append("缺少Worker受限数据库连接")
        if self.root is None or not self.root.is_absolute():
            issues.append("缺少绝对路径的Worker私有持久目录")
        if not self.network:
            issues.append("缺少工程容器隔离网络")
        if not environment_only and not self.model_execution_enabled:
            issues.append("模型执行未启用；当前禁止消费工程作业")
        if not environment_only and self.max_cost_usd is None:
            issues.append("缺少明确的模型费用上限及提供方配额")
        if (
            not environment_only
            and self.model_execution_enabled
            and self.execution_mode == "ecs_shared"
            and not self.egress_proxy_url
        ):
            issues.append("共享模式启用模型时必须配置受控出口代理")
        return issues

    def capacity_blockers(self):
        """Read-only admission before claiming; sibling containers need own limits."""
        if self.execution_mode != "ecs_shared":
            return []
        issues = []
        try:
            space = os.statvfs(self.root)
            if space.f_blocks * space.f_frsize > self.storage_limit_bytes:
                issues.append("Worker持久盘未处于已核验的硬容量边界内")
            if space.f_bavail * space.f_frsize < self.min_free_disk_bytes:
                issues.append("Worker持久盘剩余空间不足，未认领作业")
            values = dict(
                line.split(":", 1)
                for line in Path("/proc/meminfo").read_text().splitlines()
            )
            if int(values["MemAvailable"].split()[0]) < self.min_free_memory_mb * 1024:
                issues.append("宿主可用内存不足，未认领作业")
        except (OSError, TypeError, KeyError, ValueError):
            issues.append("无法核验共享宿主资源，未认领作业")
        return issues
