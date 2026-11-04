import json
from datetime import datetime, timedelta

from sqlalchemy import DateTime, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from onefde.core.clock import now
from onefde.core.errors import ApiException
from onefde.core.security import digest
from onefde.infrastructure.db.base import Base


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    scope_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSONB)
    status_code: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


def idempotent_create(
    db, username, path, key, data, create, *, method="POST", status_code=201
):
    """Auth SELECT has begun the request transaction. Lock, create and record, then commit.

    Any exception closes/rolls back the request Session. Never commit a placeholder.
    Advisory locks serialize even absent keys; database uniqueness remains authoritative.
    """
    scope = digest(json.dumps([username, method, path, key]))
    fingerprint = digest(
        json.dumps(data.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    )
    lock_id = int.from_bytes(bytes.fromhex(scope)[:8], signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
    saved = db.get(IdempotencyRecord, scope)
    if saved and saved.expires_at > now():
        if saved.request_hash != fingerprint:
            raise ApiException(409, "IDEMPOTENCY_CONFLICT", "幂等键已用于不同请求")
        result = saved.response
        db.commit()
        return result
    if saved:
        db.delete(saved)
        db.flush()
    result = create().model_dump(mode="json")
    db.add(
        IdempotencyRecord(
            scope_hash=scope,
            request_hash=fingerprint,
            response=result,
            status_code=status_code,
            expires_at=now() + timedelta(hours=24),
        )
    )
    db.commit()
    return result
