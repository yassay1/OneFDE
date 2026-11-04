"""Typed boundary between persistent Worker control and execution adapters."""

from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Event
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class ExecutionRequest:
    operation_id: UUID
    run_id: UUID
    task_id: UUID
    engagement_id: UUID
    snapshot: dict
    on_resource: Callable[[dict], None]


@dataclass(frozen=True)
class ExecutionReport:
    result: dict
    artifact_keys: tuple[str, ...] = ()
    proof: dict = field(default_factory=dict)


class ExecutionAdapter(Protocol):
    def execute(self, request: ExecutionRequest, stop: Event) -> ExecutionReport: ...


class RuntimeUnavailable(Exception):
    """Configuration rejected before allocating any external execution resource."""
