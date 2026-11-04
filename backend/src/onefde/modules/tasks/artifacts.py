from uuid import UUID

from onefde.modules.tasks import models as m
from onefde.modules.tasks.policies import conflict


def validate_artifacts(db, ids, task, run_id=None):
    for identifier in ids:
        artifact = db.get(m.Artifact, UUID(str(identifier)))
        if (
            not artifact
            or artifact.engagement_id != task.engagement_id
            or (run_id and artifact.run_id != run_id)
        ):
            conflict("ARTIFACT_SCOPE_CONFLICT", "产物必须存在并属于本项目及指定提交")
