"""Read public facts for a staff reply. This module may import other business modules."""

from sqlalchemy import select

from onefde.modules.business import service as cases
from onefde.modules.dialogue.service import beat_label
from onefde.modules.engagements.queries import require_engagement
from onefde.modules.fde import agent_work
from onefde.modules.fde.agent_models import AgentWork
from onefde.modules.fde.queries import delivery_detail
from onefde.modules.knowledge import tools as knowledge_tools
from onefde.modules.knowledge.schemas import KnowledgeToolCall
from onefde.modules.tasks import models as tasks
from onefde.modules.tasks.queries import require_task


def business(db, case_id, actor):
    row = cases.case_for(db, case_id)
    detail = cases.detail(db, row)
    handoff = detail.handoff.model_dump(mode="json") if detail.handoff else None
    return {
        "state": detail.state,
        "owner": detail.owner,
        "handler": detail.handler,
        "next_step": detail.next_step,
        "reply_allowed": detail.state == "handling" and detail.handler == actor,
        "messages": [
            {
                "id": item.id,
                "kind": item.kind,
                "author": item.author,
                "text": item.text,
            }
            for item in detail.messages
        ],
        "handoff": handoff,
    }


def _report_label(report):
    if not report:
        return "还没有"
    summary = report.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    error = report.get("error")
    if isinstance(error, str) and error.strip():
        return error.strip()
    names = ",".join(sorted(str(key) for key in report)[:8])
    return f"已保存字段 {names}" if names else "还没有"


def fde(db, engagement_id):
    engagement = require_engagement(db, engagement_id)
    delivery = delivery_detail(db, engagement_id)
    rows = db.scalars(
        select(AgentWork)
        .where(AgentWork.engagement_id == engagement_id)
        .order_by(AgentWork.created_at.desc(), AgentWork.id)
        .limit(8)
    )
    works = []
    for row in rows:
        viewed = agent_work.view(db, row)
        works.append(
            {
                "id": str(viewed["id"]),
                "goal": viewed["goal"],
                "state": viewed["state"],
                "report_label": _report_label(viewed["report"]),
            }
        )
    label, state = beat_label(db, "fde_agent")
    return {
        "title": engagement.title,
        "goal": engagement.goal,
        "unknowns": list(delivery.unknowns),
        "works": works,
        "consumer": label,
        "consumer_state": state,
    }


def engineering(db, task_id):
    task = require_task(db, task_id)
    spec = task.spec or {}
    inputs = list(
        db.scalars(
            select(tasks.TaskInput)
            .where(tasks.TaskInput.task_id == task.id)
            .order_by(tasks.TaskInput.sequence.desc())
            .limit(8)
        )
    )
    run = db.get(tasks.Run, task.latest_run_id) if task.latest_run_id else None
    label, state = beat_label(db, "engineering_worker")
    return {
        "title": spec.get("title") or task.task_key,
        "objective": spec.get("objective") or "",
        "state": task.state,
        "spec_version": task.spec_version,
        "pending_input_count": task.pending_input_count,
        "block_reason": task.block_reason,
        "inputs": [
            {
                "id": str(item.id),
                "kind": item.kind,
                "status": item.status,
                "text": item.text,
            }
            for item in inputs
        ],
        "run": None
        if run is None
        else {
            "id": str(run.id),
            "state": run.state,
            "outcome": run.outcome,
            "result_summary": run.result_summary,
        },
        "worker": label,
        "worker_state": state,
    }


def knowledge(actor, question, caller_role, purpose):
    found = knowledge_tools.invoke(
        actor,
        KnowledgeToolCall(
            tool="search_assets",
            caller_role=caller_role,
            purpose=purpose,
            arguments={"query": question},
        ),
    )
    items = list(found.result["items"][:12])
    return {
        "query": question,
        "purpose": purpose,
        "caller_role": caller_role,
        "items": items,
    }
