import hashlib
import io
import tarfile
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from onefde.core.errors import ApiException
from onefde.infrastructure.artifacts import PrivateArtifactStore
from onefde.modules.tasks import models, schemas, service
from onefde.modules.tasks.assembly import register_source, start_assembled
from tests.support.factories import create_engagement, create_task


def test_standard_assembly_keeps_pending_input_gate(
    client, auth, app, profile, tmp_path
):
    project = create_engagement(client, auth)
    response = create_task(client, auth, project["id"])
    assert response.status_code == 201, response.text
    task_id = UUID(response.json()["id"])
    archive = tmp_path / "starter.tar.gz"
    with tarfile.open(archive, "w:gz") as package:
        file = tarfile.TarInfo("DESIGN.md")
        content = b"design"
        file.size = len(content)
        package.addfile(file, io.BytesIO(content))
    with Session(app.state.engine) as db, db.begin():
        task = db.get(models.Task, task_id)
        source = register_source(
            db,
            task,
            PrivateArtifactStore(tmp_path / "private"),
            expected_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
            allowed_paths=["main.py"],
            review_paths=["DESIGN.md", "main.py"],
            archive=archive,
        )
        appended = service.append_input(
            db,
            task_id,
            schemas.TaskInputCreate(
                expected_revision=task.revision,
                kind="change_request",
                text="待采用变更",
                evidence_artifact_ids=[],
            ),
            "founder",
        )
        with pytest.raises(ApiException) as refused:
            start_assembled(
                db,
                task_id,
                expected_revision=appended.task.revision,
                profile_id=UUID(profile),
                actor="founder",
                initial_source=source,
            )
        assert refused.value.code == "INPUTS_PENDING"
        assert task.state == "draft" and task.latest_run_id is None
