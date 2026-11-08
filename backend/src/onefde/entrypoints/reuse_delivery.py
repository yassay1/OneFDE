"""Trusted local operations for delivery of an approved fixed capability."""

import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from onefde.core.config import Settings
from onefde.core.engineering import derive_checks
from onefde.entrypoints.quote_support import (
    MAX_ARCHIVE_BYTES,
    prepare_preview,
    verify_preview,
)
from onefde.infrastructure.artifacts import PrivateArtifactStore
from onefde.infrastructure.db.session import make_engine
from onefde.modules.business import models as business
from onefde.modules.business import service as cases
from onefde.modules.knowledge import catalog
from onefde.modules.knowledge.access import project_for_get
from onefde.modules.tasks import models, queries, schemas, service

CHECK = "node products/demo-supplier-quotes/check.mjs"


def queue(db, task_id, revision, archive, store, asset_id):
    manifest = catalog.get_manifest(asset_id)
    asset = project_for_get(manifest, purpose="delivery") if manifest else None
    if not asset or asset.get("reuse_scope") != "cross_project_internal":
        raise ValueError("Capability is not authorized for internal reuse")
    version = f"{asset_id}@{asset['version']}"
    task = queries.require_task(db, task_id)
    checks = [
        check["command"]
        for check in derive_checks(task.spec)
        if check["kind"] == "automatic"
    ]
    if version not in task.spec["capability_versions"] or checks != [CHECK]:
        raise ValueError(
            "Record the approved capability and its exact check in the Task spec"
        )
    with archive.open("rb") as stream:
        data = stream.read(MAX_ARCHIVE_BYTES + 1)
    digest = hashlib.sha256(data).hexdigest()
    if (
        len(data) > MAX_ARCHIVE_BYTES
        or asset.get("implementation_archive_sha256") != digest
    ):
        raise ValueError("Archive does not match the approved capability digest")
    key = f"engagements/{task.engagement_id}/reuse-sources/{digest}.tar.gz"
    source = {**store.put(key, data), "object_key": key}
    actor = "service:fde:reuse-delivery"
    queued = service.action(
        db,
        task_id,
        schemas.TaskAction(
            command="queue",
            expected_revision=revision,
            expected_run_id=None,
        ),
        actor,
    )
    return service.action(
        db,
        task_id,
        schemas.VerificationStart(
            expected_revision=queued.task.revision,
        ),
        actor,
        initial_source=source,
        reuse_asset=version,
    )


def accepted_reuse(db, case, artifact_id):
    if (
        case.state != "handling"
        or case.owner != "fde"
        or not case.task_id
        or case.workflow == "support"
    ):
        cases.conflict("首交需要原交接会话和已接受的复用任务")
    release = queries.accepted_artifact(db, case.task_id, artifact_id)
    if not release:
        cases.conflict("首交需要当前已接受的固定产物")
    artifact = db.get(models.Artifact, artifact_id)
    run = queries.require_run(db, artifact.run_id)
    version = run.snapshot.get("engineering", {}).get("reuse_asset")
    if not version or artifact.engagement_id != case.engagement_id:
        cases.conflict("产物不是本项目的固定能力验证结果")
    return artifact, release, version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    enqueue = commands.add_parser("queue")
    enqueue.add_argument("--task", type=UUID, required=True)
    enqueue.add_argument("--revision", type=int, required=True)
    enqueue.add_argument("--asset", required=True)
    enqueue.add_argument("--archive", type=Path, required=True)
    prepare = commands.add_parser("prepare")
    deliver = commands.add_parser("deliver")
    for command in (prepare, deliver):
        command.add_argument("--case", type=UUID, required=True)
        command.add_argument("--artifact", type=UUID, required=True)
    prepare.add_argument("--directory", type=Path, required=True)
    deliver.add_argument("--url", required=True)
    args = parser.parse_args()
    store = PrivateArtifactStore(args.store)
    engine = make_engine(Settings().database_url.get_secret_value())
    try:
        if args.command == "queue":
            with Session(engine) as db, db.begin():
                result = queue(
                    db, args.task, args.revision, args.archive, store, args.asset
                )
            print(result.model_dump_json())
            return
        with Session(engine) as db:
            artifact, _, _ = accepted_reuse(
                db, cases.case_for(db, args.case), args.artifact
            )
            if args.command == "prepare":
                prepare_preview(store, artifact, args.directory)
                return
            verify_preview(store, artifact, args.url)
        with Session(engine) as db, db.begin():
            case = cases.case_for(db, args.case, lock=True)
            _, release, version = accepted_reuse(db, case, args.artifact)
            prior = db.scalar(
                select(business.Message).where(
                    business.Message.case_id == case.id,
                    business.Message.reference["reuse_review_id"].astext
                    == release["review_id"],
                    business.Message.reference["access_url"].astext == args.url,
                )
            )
            message = prior or cases.reply(
                db,
                case,
                f"已交付 {version}，访问地址：{args.url}",
                {
                    "reuse_review_id": release["review_id"],
                    "artifact_id": str(args.artifact),
                    "sha256": release["sha256"],
                    "access_url": args.url,
                },
            )
            message_id = message.id
        print(json.dumps({"message_id": message_id, "review_id": release["review_id"]}))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
