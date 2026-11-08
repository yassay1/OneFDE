import hashlib
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from onefde.entrypoints import reuse_delivery
from onefde.infrastructure.artifacts import PrivateArtifactStore
from onefde.modules.tasks import models as m
from onefde.modules.tasks import schemas as s
from onefde.modules.tasks import service as tasks


def test_reuse_queue_checks_archive_and_does_not_select_model(
    control, monkeypatch, tmp_path
):
    asset_id = "approved-quote"
    original = b"fixed archive bytes"
    digest = hashlib.sha256(original).hexdigest()
    monkeypatch.setattr(
        reuse_delivery.catalog,
        "get_manifest",
        lambda _: {
            "version": "1.0",
            "visibility": "internal",
            "reuse_scope": "cross_project_internal",
            "implementation_archive_sha256": digest,
        },
    )
    task_id = UUID(control.tid)
    with Session(control.app.state.engine) as db, db.begin():
        row = db.get(m.Task, task_id)
        spec = s.TaskSpec.model_validate(row.spec).model_copy(
            update={
                "capability_versions": [asset_id + "@1.0"],
                "completion_criteria": ["[check] " + reuse_delivery.CHECK],
            }
        )
        revision = tasks.update_spec(
            db,
            task_id,
            s.TaskSpecUpdate(expected_revision=row.revision, spec=spec),
            "founder",
        ).revision
    archive = tmp_path / "source.tar.gz"
    store = PrivateArtifactStore(tmp_path / "artifacts")
    archive.write_bytes(b"wrong")
    with Session(control.app.state.engine) as db, db.begin():
        with pytest.raises(ValueError, match="approved capability digest"):
            reuse_delivery.queue(db, task_id, revision, archive, store, asset_id)
        assert db.get(m.Task, task_id).state == "draft"
    archive.write_bytes(original)
    with Session(control.app.state.engine) as db, db.begin():
        result = reuse_delivery.queue(db, task_id, revision, archive, store, asset_id)
        run = db.get(m.Run, result.run.id)
        assert run.model_profile_revision_id is None
        assert run.snapshot["model_profile"] is None
        assert run.snapshot["engineering"]["reuse_asset"] == asset_id + "@1.0"
        assert run.snapshot["engineering"]["initial_source"]["sha256"] == digest
