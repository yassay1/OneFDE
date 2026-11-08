from sqlalchemy import select

from onefde.core.engineering import check_revision, derive_checks
from onefde.core.errors import ApiException
from onefde.infrastructure.db.pagination import page as paginate
from onefde.modules.engagements.queries import require_engagement
from onefde.modules.tasks import models as m
from onefde.modules.tasks import schemas as s


def require_task(db, task_id):
    row = db.get(m.Task, task_id)
    if row is None:
        raise ApiException(404, "NOT_FOUND", "任务不存在")
    return row


def require_run(db, run_id):
    row = db.get(m.Run, run_id)
    if row is None:
        raise ApiException(404, "NOT_FOUND", "运行不存在")
    return row


def run_review_evidence(db, run_id):
    run = require_run(db, run_id)
    job = db.scalar(select(m.DispatchJob).where(m.DispatchJob.run_id == run_id))
    proof = ((job.result_payload or {}).get("proof") or {}) if job else {}
    material = proof.get("review_material")
    if not material or run.state != "completed" or run.outcome != "submitted":
        return None
    artifact = db.scalar(
        select(m.Artifact).where(
            m.Artifact.run_id == run_id,
            m.Artifact.kind == "source-snapshot",
            m.Artifact.sha256 == material["artifact_sha256"],
        )
    )
    if not artifact:
        return None
    validation = proof.get("validation") or {}
    engineering = run.snapshot.get("engineering") or {}
    if "candidate_sha256" in validation and (
        validation.get("passed") is not True
        or validation["candidate_sha256"] != artifact.sha256
        or validation.get("spec_version") != run.task_spec_version
        or validation.get("check_revision")
        != check_revision(
            engineering.get("checks") or derive_checks(run.snapshot.get("spec") or {})
        )
    ):
        return None
    source = engineering.get("initial_source") or {}
    standard = source.get("assembly_revision") == "standard-v1"
    if standard and source.get("sha256") != material["baseline_sha256"]:
        return None
    return s.RunReviewEvidence(
        **material,
        artifact_id=artifact.id,
        self_checks=[
            row["evidence"]
            for row in proof.get("check_coverage", [])
            if row.get("matched") and row.get("evidence")
        ],
        validation_checks=validation.get("results", []),
        validation_passed=validation.get("passed"),
        guide_revision=source.get("review_guide_revision"),
        assembly_revision=source.get("assembly_revision") if standard else None,
        baseline_origin=source.get("baseline_origin") if standard else None,
        baseline_artifact_id=source.get("baseline_artifact_id") if standard else None,
        known_differences=source.get("known_differences", []) if standard else [],
    )


def sequence_page(db, model, schema, parent_id, after, limit, *, run=False):
    (require_run if run else require_task)(db, parent_id)
    column = model.run_id if run else model.task_id
    rows = list(
        db.scalars(
            select(model)
            .where(column == parent_id, model.sequence > after)
            .order_by(model.sequence)
            .limit(limit + 1)
        )
    )
    items = rows[:limit]
    return {
        "items": [schema.model_validate(i) for i in items],
        "last_sequence": items[-1].sequence if items else after,
        "has_more": len(rows) > limit,
    }


def page(
    db, model, schema, limit, cursor, engagement_id=None, *, task_id=None, run_id=None
):
    filters = []
    scope = "engagements"
    if engagement_id:
        require_engagement(db, engagement_id)
        filters.append(model.engagement_id == engagement_id)
        scope = str(engagement_id)
    if task_id:
        require_task(db, task_id)
        filters.append(model.task_id == task_id)
        scope = model.__tablename__ + ":" + str(task_id)
    if run_id:
        require_run(db, run_id)
        filters.append(model.run_id == run_id)
        scope = model.__tablename__ + ":" + str(run_id)
    return paginate(db, model, schema, limit, cursor, filters=filters, scope=scope)


def get_version(db, task_id, spec_version):
    require_task(db, task_id)
    row = db.scalar(
        select(m.TaskVersion).where(
            m.TaskVersion.task_id == task_id, m.TaskVersion.spec_version == spec_version
        )
    )
    if row is None:
        raise ApiException(404, "NOT_FOUND", "任务版本不存在")
    return row


def list_profiles(db):
    return list(
        db.scalars(
            select(m.ModelProfileRevision).order_by(
                m.ModelProfileRevision.id, m.ModelProfileRevision.revision_id
            )
        )
    )


def has_input_text(db, task_id, text):
    return (
        db.scalar(
            select(m.TaskInput.id)
            .where(
                m.TaskInput.task_id == task_id,
                m.TaskInput.text == text,
            )
            .limit(1)
        )
        is not None
    )


def accepted_artifact(db, task_id, artifact_id):
    task = require_task(db, task_id)
    artifact = db.get(m.Artifact, artifact_id)
    if (
        task.state != "succeeded"
        or not artifact
        or artifact.run_id != task.latest_run_id
        or artifact.engagement_id != task.engagement_id
    ):
        return None
    review = db.scalar(
        select(m.TaskReview).where(
            m.TaskReview.task_id == task_id,
            m.TaskReview.run_id == artifact.run_id,
            m.TaskReview.task_spec_version == task.spec_version,
            m.TaskReview.verdict == "accept",
        )
    )
    if not review or str(artifact_id) not in review.artifact_ids:
        return None
    return {
        "run_id": str(review.run_id),
        "spec_version": review.task_spec_version,
        "review_id": str(review.id),
        "sha256": artifact.sha256,
    }
