from typing import Annotated

from fastapi import Depends, Header, Query, Request
from sqlalchemy.orm import Session


def get_db(request: Request):
    """One Session per request; services commit writes before returning a response."""
    with Session(request.app.state.engine, expire_on_commit=False) as session:
        yield session


Limit = Annotated[int, Query(ge=1, le=100)]


Key = Annotated[
    str, Header(alias="Idempotency-Key", min_length=1, max_length=128, pattern=r"\S")
]


After = Annotated[int, Query(ge=0)]


DB = Annotated[Session, Depends(get_db)]
