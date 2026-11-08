from uuid import uuid4

from sqlalchemy import select

from onefde.core.clock import now
from onefde.core.errors import ApiException
from onefde.modules.business import amap
from onefde.modules.business import models as m
from onefde.modules.business import schemas as s


def search(db, key, data):
    entries = amap.search(key, data.adcode, sample=data.sample)
    timestamp = now()
    rows = [m.Candidate(id=uuid4(), queried_at=timestamp, **entry) for entry in entries]
    db.add_all(rows)
    db.flush()
    return s.CandidateResults(items=rows)


def candidates(db, adcode):
    rows = db.scalars(
        select(m.Candidate)
        .where(m.Candidate.adcode == adcode)
        .order_by(m.Candidate.queried_at.desc(), m.Candidate.id)
        .limit(50)
    )
    return s.CandidateResults(items=list(rows))


def invite(db, identifier, actor):
    row = db.scalar(
        select(m.Candidate).where(m.Candidate.id == identifier).with_for_update()
    )
    if not row:
        raise ApiException(404, "BUSINESS_CANDIDATE_NOT_FOUND", "候选门店不存在")
    if not row.invited_at:
        row.invited_at, row.invited_by = now(), actor
    return s.CandidateView.model_validate(row)
