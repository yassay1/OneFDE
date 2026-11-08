"""Business automation authorization and message-driven leases."""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from onefde.core.clock import now
from onefde.core.errors import ApiException
from onefde.modules.business import models as m
from onefde.modules.engagements.queries import require_engagement
from onefde.modules.tasks.models import ModelProfileRevision

ACTOR = "service:business:delivery"
FOUNDER_TEXT = "已转给负责人，请保留这个链接查看后续回复。"


def fail(code, message):
    raise ApiException(409, code, message)


def isolated(db):
    name = db.get_bind().engine.url.database
    return bool(name and name.endswith("_test"))


def active(db, case):
    if not isolated(db):
        return None
    grant = db.get(m.AgentGrant, case.id)
    if (
        grant
        and grant.expires_at > now()
        and (not case.engagement_id or case.engagement_id == grant.engagement_id)
    ):
        return grant
    return None


def owns_intake(case):
    return (
        case.owner == "business"
        and case.state in ("open", "clarifying")
        and case.handler is None
        and not case.handoff
    )


def enroll(db, case_id, engagement_id, profile_id, policy):
    project = require_engagement(db, engagement_id) if engagement_id else None
    profile = db.get(ModelProfileRevision, profile_id)
    case = db.get(m.Case, case_id, with_for_update=True)
    if (
        not isolated(db)
        or (project and not project.is_demo)
        or (
            case
            and (
                not owns_intake(case) or case.engagement_id not in (None, engagement_id)
            )
        )
        or not profile
        or profile.integration_status == "unavailable"
        or policy.expires_at.utcoffset() is None
        or policy.expires_at <= now()
        or db.get(m.AgentGrant, case_id)
    ):
        fail("BUSINESS_AGENT_GRANT_INVALID", "仅可为隔离库的指定模拟会话登记有效授权")
    db.add(
        m.AgentGrant(
            case_id=case_id,
            engagement_id=engagement_id,
            profile_id=profile_id,
            expires_at=policy.expires_at,
            policy=policy.model_dump(mode="json", exclude={"expires_at"}),
            progress={},
        )
    )


def latest(db, case, *kinds):
    return db.scalar(
        select(m.Message)
        .where(
            m.Message.case_id == case.id,
            m.Message.kind.in_(kinds),
        )
        .order_by(m.Message.id.desc())
        .limit(1)
    )


def pending(db, case, grant):
    public = latest(db, case, "customer", "reply")
    if public is None:
        return None
    if owns_intake(case) and public.kind == "customer":
        if public.id > grant.progress.get("customer_id", 0):
            return (
                "customer",
                public.id,
                public.id,
                case.state,
                case.owner,
                case.handler,
            )
    if case.owner == "fde" and case.state == "handling":
        approved = db.scalar(
            select(m.Message)
            .where(
                m.Message.case_id == case.id,
                m.Message.kind == "note",
                m.Message.reference["type"].astext == "approved_fde_feedback",
            )
            .order_by(m.Message.id.desc())
            .limit(1)
        )
        if (
            approved
            and approved.id > grant.progress.get("feedback_id", 0)
            and approved.reference["public_id"] == public.id
        ):
            return (
                "feedback",
                approved.id,
                public.id,
                case.state,
                case.owner,
                case.handler,
            )
    return None


def claim(db, profile_id, case_id=None):
    query = (
        select(m.AgentGrant.case_id)
        .where(
            m.AgentGrant.profile_id == profile_id,
            m.AgentGrant.expires_at > now(),
            (m.AgentGrant.lease_until.is_(None)) | (m.AgentGrant.lease_until <= now()),
        )
        .order_by(m.AgentGrant.case_id)
    )
    if case_id:
        query = query.where(m.AgentGrant.case_id == case_id)
    for identifier in db.scalars(query):
        case = db.scalar(
            select(m.Case)
            .where(m.Case.id == identifier)
            .with_for_update(skip_locked=True)
        )
        if not case:
            continue
        grant = active(db, case)
        if not grant or (grant.lease_until and grant.lease_until > now()):
            continue
        event = pending(db, case, grant)
        if event:
            grant.lease_token = uuid4()
            renew(grant)
            return case.id, grant.lease_token, event
    return None


def renew(grant):
    grant.lease_until = now() + timedelta(seconds=150)


def owned(db, case_id, token, event):
    case = db.get(m.Case, case_id, with_for_update=True)
    grant = active(db, case) if case else None
    if (
        not grant
        or grant.lease_token != token
        or grant.lease_until <= now()
        or pending(db, case, grant) != event
    ):
        fail("BUSINESS_AGENT_STALE", "原会话已有更新、转交或授权变动")
    renew(grant)
    return case, grant


def release(db, case_id, token):
    db.get(m.Case, case_id, with_for_update=True)
    grant = db.get(m.AgentGrant, case_id)
    if grant and grant.lease_token == token:
        grant.lease_token = grant.lease_until = None
