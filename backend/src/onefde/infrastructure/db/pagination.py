import base64
import binascii
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, tuple_

from onefde.core.errors import ApiException


def page(db, model, schema, limit, cursor, *, scope, filters=(), project=None):
    query = select(model).where(*filters)
    if cursor is not None:
        try:
            if len(cursor) > 1024:
                raise ValueError()
            saved_scope, timestamp, identifier = json.loads(
                base64.urlsafe_b64decode(cursor.encode())
            )
            timestamp, identifier = datetime.fromisoformat(timestamp), UUID(identifier)
            if saved_scope != scope or timestamp.utcoffset() is None:
                raise ValueError()
        except (ValueError, TypeError, binascii.Error, UnicodeError):
            raise ApiException(422, "INVALID_CURSOR", "分页游标无效") from None
        query = query.where(
            tuple_(model.created_at, model.id) > tuple_(timestamp, identifier)
        )
    rows = list(db.scalars(query.order_by(model.created_at, model.id).limit(limit + 1)))
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = base64.urlsafe_b64encode(
            json.dumps([scope, last.created_at.isoformat(), str(last.id)]).encode()
        ).decode()
    return {
        "items": [
            (project(row) if project else schema.model_validate(row))
            for row in rows[:limit]
        ],
        "next_cursor": next_cursor,
    }
