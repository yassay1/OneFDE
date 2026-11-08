"""Trusted source registration for the existing Engineering start command."""

import hashlib
import io
import tarfile
from pathlib import PurePosixPath

from onefde.modules.tasks import models, queries, schemas, service
from onefde.modules.tasks.policies import conflict

MAX_SOURCE_BYTES = 8 * 1024 * 1024
GUIDE_REVISION = "review-v1"


def canonical_path(name):
    path = PurePosixPath(name)
    if (
        name != path.as_posix()
        or path.is_absolute()
        or not path.parts
        or any(part in (".", "..", ".git", "bash_events") for part in path.parts)
        or "\\" in name
    ):
        raise ValueError("源文件路径必须是规范的项目内相对路径")
    return name


def archive_files(data):
    sizes = 0
    files = set()
    if not 0 < len(data) <= MAX_SOURCE_BYTES:
        raise ValueError("固定源码归档超出大小限制")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive:
            name = canonical_path(member.name)
            if not member.isfile() or name in files:
                raise ValueError("固定源码归档只接受唯一的常规文件")
            files.add(name)
            sizes += member.size
            if sizes > MAX_SOURCE_BYTES or len(files) > 512:
                raise ValueError("固定源码归档解包范围超出限制")
    if not files:
        raise ValueError("固定源码归档为空")
    return files


def register_source(
    db,
    task,
    store,
    *,
    expected_sha256,
    allowed_paths,
    review_paths,
    archive=None,
    accepted_artifact_id=None,
    known_differences=(),
):
    """Register a starter or the exact accepted artifact of this Task's parent."""
    if (archive is None) == (accepted_artifact_id is None):
        raise ValueError("请选择一个受信起始归档或关联 Task 已接受产物")
    if accepted_artifact_id:
        if not task.related_task_id:
            conflict(
                "SOURCE_SCOPE_CONFLICT", "续办归档必须来自本 Task 关联的已接受任务"
            )
        prior = queries.require_task(db, task.related_task_id)
        accepted = queries.accepted_artifact(db, prior.id, accepted_artifact_id)
        artifact = db.get(models.Artifact, accepted_artifact_id)
        if (
            not accepted
            or not artifact
            or prior.engagement_id != task.engagement_id
            or artifact.kind != "source-snapshot"
        ):
            conflict("SOURCE_SCOPE_CONFLICT", "续办归档必须来自同项目的已接受源码")
        if artifact.sha256 != expected_sha256:
            conflict("SOURCE_DIGEST_MISMATCH", "已接受归档摘要不符")
        with store.path(artifact.object_key).open("rb") as blob:
            data = blob.read(MAX_SOURCE_BYTES + 1)
    else:
        if task.related_task_id:
            conflict("SOURCE_SCOPE_CONFLICT", "关联 Task 应引用原任务已接受的归档")
        with archive.open("rb") as blob:
            data = blob.read(MAX_SOURCE_BYTES + 1)
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        conflict("SOURCE_DIGEST_MISMATCH", "固定源码归档摘要不符")
    baseline_files = archive_files(data)
    allowed = sorted({canonical_path(path) for path in allowed_paths})
    review = sorted({canonical_path(path) for path in review_paths})
    if not allowed or not review or not set(review) <= baseline_files.union(allowed):
        raise ValueError("请登记可修改文件及其评审范围")
    if len(known_differences) > 8 or any(
        not text.strip() or len(text) > 500 for text in known_differences
    ):
        raise ValueError("已知差异最多八条，每条不超过 500 字")
    key = f"engagements/{task.engagement_id}/engineering-seeds/{expected_sha256}.tar.gz"
    return {
        **store.put(key, data),
        "object_key": key,
        "allowed_paths": allowed,
        "review_paths": review,
        "review_guide_revision": GUIDE_REVISION,
        "assembly_revision": "standard-v1",
        "task_id": str(task.id),
        "engagement_id": str(task.engagement_id),
        "baseline_origin": "accepted_artifact"
        if accepted_artifact_id
        else "trusted_starter",
        "baseline_artifact_id": str(accepted_artifact_id)
        if accepted_artifact_id
        else None,
        "known_differences": list(known_differences),
    }


def start_assembled(
    db, task_id, *, expected_revision, profile_id, actor, initial_source
):
    """Reuse the queue/start transaction and existing Run/dispatch snapshot."""
    task = queries.require_task(db, task_id)
    if (
        initial_source.get("assembly_revision") != "standard-v1"
        or initial_source.get("task_id") != str(task_id)
        or initial_source.get("engagement_id") != str(task.engagement_id)
    ):
        conflict("SOURCE_SCOPE_CONFLICT", "Run 装配必须属于当前任务和项目")
    queued = service.action(
        db,
        task_id,
        schemas.TaskAction(
            command="queue", expected_revision=expected_revision, expected_run_id=None
        ),
        actor,
    )
    return service.action(
        db,
        task_id,
        schemas.TaskAction(
            command="start",
            expected_revision=queued.task.revision,
            expected_run_id=None,
            model_profile_revision_id=profile_id,
        ),
        actor,
        initial_source=initial_source,
    )
