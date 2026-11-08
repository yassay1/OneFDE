"""Read-only delivery aggregation for the thin project detail surface."""

from sqlalchemy import select

from onefde.modules.engagements.queries import require_engagement
from onefde.modules.engagements.schemas import Engagement
from onefde.modules.fde.schemas import DeliveryDetail, DeliveryTaskSummary
from onefde.modules.tasks import models as task_models
from onefde.modules.tasks import schemas as task_schemas


def delivery_detail(db, engagement_id) -> DeliveryDetail:
    engagement = Engagement.model_validate(require_engagement(db, engagement_id))
    rows = list(
        db.scalars(
            select(task_models.Task)
            .where(task_models.Task.engagement_id == engagement_id)
            .order_by(task_models.Task.created_at.asc())
        )
    )
    tasks = []
    unknowns: list[str] = []
    latest_checks: list[str] = []
    scheme_summary = None
    fixed_hint = None
    for row in rows:
        spec = task_schemas.TaskSpec.model_validate(row.spec)
        tasks.append(
            DeliveryTaskSummary(
                id=row.id,
                state=row.state,
                title=spec.title,
                objective=spec.objective,
                scope=spec.scope,
                pending_input_count=row.pending_input_count,
                latest_run_id=row.latest_run_id,
                revision=row.revision,
                spec_version=row.spec_version,
            )
        )
        if scheme_summary is None:
            scheme_summary = spec.objective
        pending = list(
            db.scalars(
                select(task_models.TaskInput).where(
                    task_models.TaskInput.task_id == row.id,
                    task_models.TaskInput.status == "pending",
                    task_models.TaskInput.kind.in_(("question", "clarification")),
                )
            )
        )
        unknowns.extend(item.text for item in pending)
        if row.latest_run_id:
            run = db.get(task_models.Run, row.latest_run_id)
            if run and run.result_summary:
                latest_checks.append(run.result_summary)
            if row.state == "succeeded":
                fixed_hint = f"task={row.id} spec_version={row.spec_version}"
            elif row.state == "review" and run is not None:
                fixed_hint = (
                    f"pending_review run={run.id} spec_version={row.spec_version}"
                )

    sources = (
        "模拟演示项目" if engagement.is_demo else "真实资料须按 Engagement 授权范围读取"
    )
    return DeliveryDetail(
        engagement=engagement,
        sources_note=sources,
        unknowns=unknowns,
        scheme_summary=scheme_summary,
        tasks=tasks,
        latest_checks=latest_checks,
        fixed_version_hint=fixed_hint,
    )
