"""Derive Office feeds from Case / Task / FDE Work / Run / Review facts."""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime

from sqlalchemy import or_, select

from onefde.core.clock import now
from onefde.core.errors import ApiException
from onefde.modules.business import models as business
from onefde.modules.fde.agent_models import AgentWork
from onefde.modules.fde.agent_work import view as fde_view
from onefde.modules.office import schemas as s
from onefde.modules.tasks import models as tasks

CASE_CAP = 500
TASK_CAP = 500
FDE_CAP = 200
RUN_CAP = 200
REVIEW_CAP = 200

ACTIONABLE_TASK = frozenset({"review", "waiting_input", "blocked", "running", "queued"})
CLOSED_CASE = frozenset({"closed"})


def _cursor_decode(cursor: str | None, scope: str):
    if cursor is None:
        return None
    try:
        if len(cursor) > 2048:
            raise ValueError()
        saved_scope, stamp, item_id = json.loads(
            base64.urlsafe_b64decode(cursor.encode())
        )
        stamp = datetime.fromisoformat(stamp)
        if saved_scope != scope or stamp.utcoffset() is None:
            raise ValueError()
        return stamp, str(item_id)
    except (ValueError, TypeError, binascii.Error, UnicodeError, json.JSONDecodeError):
        raise ApiException(422, "INVALID_CURSOR", "分页游标无效") from None


def _cursor_encode(scope: str, stamp: datetime, item_id: str) -> str:
    return base64.urlsafe_b64encode(
        json.dumps([scope, stamp.isoformat(), item_id]).encode()
    ).decode()


def _after(cursor_point, stamp: datetime, item_id: str) -> bool:
    """True when (stamp, id) is strictly older than cursor (desc feed)."""
    if cursor_point is None:
        return True
    cursor_stamp, cursor_id = cursor_point
    if stamp < cursor_stamp:
        return True
    if stamp == cursor_stamp and item_id < cursor_id:
        return True
    return False


def _page(items: list[s.OfficeItem], limit: int, scope: str, cursor: str | None):
    point = _cursor_decode(cursor, scope)
    filtered = [item for item in items if _after(point, item.occurred_at, item.id)]
    filtered.sort(key=lambda item: (item.occurred_at, item.id), reverse=True)
    page = filtered[:limit]
    next_cursor = None
    if len(filtered) > limit:
        last = page[-1]
        next_cursor = _cursor_encode(scope, last.occurred_at, last.id)
    return page, next_cursor


def _case_item(row: business.Case) -> s.OfficeItem:
    return s.OfficeItem(
        id=f"case:{row.id}",
        kind="case",
        role="business",
        title=f"{row.workflow} · {row.id}",
        reason=row.next_step,
        state=row.state,
        object_id=row.id,
        engagement_id=row.engagement_id,
        case_id=row.id,
        task_id=row.task_id,
        occurred_at=row.created_at,
        href=f"/business/{row.id}",
    )


def _task_item(row: tasks.Task) -> s.OfficeItem:
    title = (row.spec or {}).get("title") or row.task_key
    reason = row.block_reason or (row.spec or {}).get("objective") or row.state
    if row.pending_input_count:
        reason = f"待处理输入 {row.pending_input_count} 条 · {reason}"
    run_q = f"&run={row.latest_run_id}" if row.latest_run_id else ""
    view = "&view=submission" if row.state in {"review", "waiting_input"} else ""
    return s.OfficeItem(
        id=f"task:{row.id}",
        kind="task",
        role="engineering",
        title=str(title),
        reason=str(reason)[:500],
        state=row.state,
        object_id=row.id,
        engagement_id=row.engagement_id,
        task_id=row.id,
        run_id=row.latest_run_id,
        occurred_at=row.created_at,
        href=f"/engineering?project={row.engagement_id}&task={row.id}{run_q}{view}",
    )


def _fde_item(db, row: AgentWork) -> s.OfficeItem | None:
    viewed = fde_view(db, row)
    state = viewed["state"]
    report = viewed.get("report") or {}
    error = report.get("error")
    actionable = state in {"pending", "processing"} or bool(error)
    if not actionable:
        return None
    reason = error or row.goal or state
    case_q = f"&case={row.case_id}" if row.case_id else ""
    return s.OfficeItem(
        id=f"fde_work:{row.id}",
        kind="fde_work",
        role="fde",
        title=f"FDE 工作 · {row.engagement_id}",
        reason=str(reason)[:500],
        state="报告含错误" if error else state,
        object_id=row.id,
        engagement_id=row.engagement_id,
        case_id=row.case_id,
        task_id=row.task_id,
        occurred_at=row.created_at,
        href=f"/fde?project={row.engagement_id}&work={row.id}{case_q}",
    )


def _run_item(row: tasks.Run) -> s.OfficeItem:
    return s.OfficeItem(
        id=f"run:{row.id}",
        kind="run",
        role="engineering",
        title=f"Run · {row.id}",
        reason=(row.result_summary or row.error_code or row.state or "")[:500],
        state=f"{row.state}/{row.outcome}" if row.outcome else row.state,
        object_id=row.id,
        engagement_id=None,
        task_id=row.task_id,
        run_id=row.id,
        occurred_at=row.created_at,
        href=f"/engineering?task={row.task_id}&run={row.id}&view=submission",
    )


def _review_item(row: tasks.TaskReview) -> s.OfficeItem:
    return s.OfficeItem(
        id=f"review:{row.id}",
        kind="review",
        role="engineering",
        title=f"评审 · {row.verdict}",
        reason=(row.reason or row.verdict)[:500],
        state=row.verdict,
        object_id=row.id,
        task_id=row.task_id,
        run_id=row.run_id,
        occurred_at=row.created_at,
        href=f"/engineering?task={row.task_id}&run={row.run_id}&view=submission",
    )


def _coverage(**counts) -> s.OfficeCoverage:
    return s.OfficeCoverage(
        description=(
            "派生自当前库内 Case/Task/FDE Work/Run/Review；"
            f"扫描上限 case={CASE_CAP} task={TASK_CAP} fde={FDE_CAP} "
            f"run={RUN_CAP} review={REVIEW_CAP}。"
            "无独立通知表；不含 totalCount。"
        ),
        case_cap=CASE_CAP,
        task_cap=TASK_CAP,
        fde_work_cap=FDE_CAP,
        run_cap=RUN_CAP,
        review_cap=REVIEW_CAP,
        **counts,
    )


def list_actionable(db, *, limit: int, cursor: str | None) -> s.OfficePage:
    cases = list(
        db.scalars(
            select(business.Case)
            .where(business.Case.state.not_in(CLOSED_CASE))
            .order_by(business.Case.created_at.desc(), business.Case.id.desc())
            .limit(CASE_CAP)
        )
    )
    task_rows = list(
        db.scalars(
            select(tasks.Task)
            .where(
                or_(
                    tasks.Task.state.in_(ACTIONABLE_TASK),
                    (tasks.Task.pending_input_count > 0)
                    & tasks.Task.state.not_in(("succeeded", "cancelled")),
                )
            )
            .order_by(tasks.Task.created_at.desc(), tasks.Task.id.desc())
            .limit(TASK_CAP)
        )
    )
    works = list(
        db.scalars(
            select(AgentWork)
            .order_by(AgentWork.created_at.desc(), AgentWork.id.desc())
            .limit(FDE_CAP)
        )
    )
    items: list[s.OfficeItem] = [_case_item(row) for row in cases]
    items.extend(_task_item(row) for row in task_rows)
    for work in works:
        item = _fde_item(db, work)
        if item:
            items.append(item)
    # Dedup by id
    dedup = {item.id: item for item in items}
    page, next_cursor = _page(list(dedup.values()), limit, "office-actionable", cursor)
    return s.OfficePage(
        items=page,
        next_cursor=next_cursor,
        read_at=now(),
        coverage=_coverage(
            scanned_cases=len(cases),
            scanned_tasks=len(task_rows),
            scanned_fde_works=len(works),
            scanned_runs=0,
            scanned_reviews=0,
        ),
    )


def list_activity(db, *, limit: int, cursor: str | None) -> s.OfficePage:
    closed = list(
        db.scalars(
            select(business.Case)
            .where(business.Case.state.in_(CLOSED_CASE))
            .order_by(business.Case.created_at.desc(), business.Case.id.desc())
            .limit(CASE_CAP)
        )
    )
    runs = list(
        db.scalars(
            select(tasks.Run)
            .where(
                tasks.Run.state.in_(("completed", "failed", "cancelled", "interrupted"))
            )
            .order_by(tasks.Run.created_at.desc(), tasks.Run.id.desc())
            .limit(RUN_CAP)
        )
    )
    reviews = list(
        db.scalars(
            select(tasks.TaskReview)
            .order_by(tasks.TaskReview.created_at.desc(), tasks.TaskReview.id.desc())
            .limit(REVIEW_CAP)
        )
    )
    works = list(
        db.scalars(
            select(AgentWork)
            .where(AgentWork.completed.is_not(None))
            .order_by(AgentWork.created_at.desc(), AgentWork.id.desc())
            .limit(FDE_CAP)
        )
    )
    items: list[s.OfficeItem] = [_case_item(row) for row in closed]
    items.extend(_run_item(row) for row in runs)
    items.extend(_review_item(row) for row in reviews)
    for work in works:
        viewed = fde_view(db, work)
        items.append(
            s.OfficeItem(
                id=f"fde_work:{work.id}",
                kind="fde_work",
                role="fde",
                title=f"FDE 报告 · {work.engagement_id}",
                reason=str((viewed.get("report") or {}).get("summary") or work.goal)[
                    :500
                ],
                state=viewed["state"],
                object_id=work.id,
                engagement_id=work.engagement_id,
                case_id=work.case_id,
                task_id=work.task_id,
                occurred_at=work.created_at,
                href=f"/fde?project={work.engagement_id}&work={work.id}",
            )
        )
    # Attach project context to Run and Review facts, retaining review titles.
    task_ids = {
        item.task_id
        for item in items
        if item.kind in {"run", "review"} and item.task_id
    }
    if task_ids:
        task_map = {
            row.id: row
            for row in db.scalars(select(tasks.Task).where(tasks.Task.id.in_(task_ids)))
        }
        enriched: list[s.OfficeItem] = []
        for item in items:
            if (
                item.kind in {"run", "review"}
                and item.task_id
                and item.task_id in task_map
            ):
                task = task_map[item.task_id]
                enriched.append(
                    item.model_copy(
                        update={
                            "engagement_id": task.engagement_id,
                            "href": (
                                f"/engineering?project={task.engagement_id}"
                                f"&task={task.id}&run={item.run_id}&view=submission"
                            ),
                            "title": f"{(task.spec or {}).get('title') or task.task_key} · Run"
                            if item.kind == "run"
                            else item.title,
                        }
                    )
                )
            else:
                enriched.append(item)
        items = enriched
    dedup = {item.id: item for item in items}
    page, next_cursor = _page(list(dedup.values()), limit, "office-activity", cursor)
    return s.OfficePage(
        items=page,
        next_cursor=next_cursor,
        read_at=now(),
        coverage=_coverage(
            scanned_cases=len(closed),
            scanned_tasks=0,
            scanned_fde_works=len(works),
            scanned_runs=len(runs),
            scanned_reviews=len(reviews),
        ),
    )
