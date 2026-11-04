from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Nonblank = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]


Title = Annotated[Nonblank, Field(max_length=200)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None


class ApiError(BaseModel):
    code: str
    message: str
    request_id: str
    details: dict | None = None


class Health(BaseModel):
    status: Literal["ok"] = "ok"


class SequencePage(Input, Generic[T]):
    items: list[T]
    last_sequence: int = Field(ge=0)
    has_more: bool
