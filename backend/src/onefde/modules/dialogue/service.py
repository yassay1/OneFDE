"""Persist staff turns. Callers commit through the existing idempotency boundary."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from onefde.core.clock import now
from onefde.infrastructure.runtime.staff_chat import complete
from onefde.modules.dialogue import actions
from onefde.modules.dialogue import models as m
from onefde.modules.dialogue.schemas import (
    BeatView,
    DialogueReply,
    DialogueView,
    RuntimeStatus,
)

BEAT_NAMES = ("fde_agent", "engineering_worker")
FRESH_SECONDS = 45
_STALE = "没有心跳。待处理不代表已经完成，也不是正在执行。"


def beat(db, name: str, detail: str = ""):
    if name not in BEAT_NAMES:
        raise ValueError(name)
    statement = insert(m.RuntimeBeat).values(name=name, beat_at=now(), detail=detail)
    db.execute(
        statement.on_conflict_do_update(
            index_elements=[m.RuntimeBeat.name],
            set_={
                "beat_at": statement.excluded.beat_at,
                "detail": statement.excluded.detail,
            },
        )
    )


def record_beat(engine, name: str, detail: str = ""):
    with Session(engine) as db, db.begin():
        beat(db, name, detail)


def _view_beat(name, row):
    if row is None:
        return BeatView(
            name=name,
            state="not_running",
            beat_at=None,
            age_seconds=None,
            detail=_STALE,
        )
    age = max(int((now() - row.beat_at).total_seconds()), 0)
    fresh = age <= FRESH_SECONDS
    return BeatView(
        name=name,
        state="running" if fresh else "not_running",
        beat_at=row.beat_at,
        age_seconds=age,
        detail=row.detail
        or ("最近有心跳" if fresh else "心跳已过期，不能当作正在执行。"),
    )


def runtime_status(db) -> RuntimeStatus:
    rows = {row.name: row for row in db.scalars(select(m.RuntimeBeat))}
    return RuntimeStatus(
        fde_agent=_view_beat("fde_agent", rows.get("fde_agent")),
        engineering_worker=_view_beat(
            "engineering_worker", rows.get("engineering_worker")
        ),
    )


def beat_label(db, name: str):
    status = runtime_status(db)
    beat_view = status.fde_agent if name == "fde_agent" else status.engineering_worker
    if beat_view.state == "running":
        return f"最近 {beat_view.age_seconds} 秒内有心跳", beat_view.state
    return beat_view.detail, beat_view.state


def list_turns(db, role: str, anchor_id: str) -> DialogueView:
    rows = db.scalars(
        select(m.StaffTurn)
        .where(m.StaffTurn.role == role, m.StaffTurn.anchor_id == anchor_id)
        .order_by(m.StaffTurn.created_at.asc(), m.StaffTurn.id.asc())
        .limit(200)
    )
    return DialogueView(turns=list(rows))


def append(
    db, *, role, anchor_id, actor, question, context, mode, staff_basis=None, live=None
):
    text, basis, adapter = complete(mode, role, question, context, live=live)
    if adapter == "live":
        text, basis = actions.settle(
            db, role, anchor_id, actor, question, context, text, basis
        )
    staff = m.StaffTurn(
        role=role,
        anchor_id=anchor_id,
        author=actor,
        text=question,
        basis=staff_basis or {},
        adapter="staff",
    )
    assistant = m.StaffTurn(
        role=role,
        anchor_id=anchor_id,
        author="assistant",
        text=text,
        basis=basis,
        adapter=adapter,
    )
    db.add(staff)
    db.add(assistant)
    db.flush()
    return DialogueReply(turns=[staff, assistant])
