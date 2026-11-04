"""PostgreSQL control tests. All runtime results/artifacts are deterministic fixtures."""

import hashlib
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from onefde.modules.tasks import schemas as s
from onefde.modules.tasks import service as tasks
from tests.support.factories import create_engagement, create_task


class Control:
    def __init__(self, client, auth, app, profile):
        self.client, self.auth, self.app, self.profile = client, auth, app, profile
        self.eid = create_engagement(client, auth)["id"]
        response = create_task(client, auth, self.eid)
        assert response.status_code == 201, response.text
        self.tid = response.json()["id"]

    def get(self):
        return self.client.get("/api/v1/tasks/" + self.tid).json()

    def write(self, suffix, data, status=200, key=None, method="post"):
        response = getattr(self.client, method)(
            "/api/v1/tasks/" + self.tid + suffix,
            json=data,
            headers={**self.auth, "Idempotency-Key": key or str(uuid4())},
        )
        assert response.status_code == status, response.text
        return response.json()

    def action(self, command, status=202, key=None, **fields):
        data = {
            "command": command,
            "expected_revision": self.get()["revision"],
            "expected_run_id": None,
            **fields,
        }
        if command in ("start", "retry", "continue"):
            data["model_profile_revision_id"] = self.profile
        return self.write("/actions", data, status, key)

    def start(self):
        self.action("queue")
        return self.action("start")["run"]

    def claim(self, run):
        with Session(self.app.state.engine) as db:
            tasks.mark_run_started(db, UUID(run["id"]))
            db.commit()

    def finish(self, run, state="completed", outcome="submitted", **fields):
        data = dict(
            state=state,
            outcome=outcome,
            summary="SIMULATED control result",
            stopped=state != "interrupted",
            **fields,
        )
        if outcome == "submitted":
            data["artifacts"] = [
                {
                    "name": "SIMULATED report",
                    "kind": "test-fixture",
                    "sha256": hashlib.sha256(b"explicit simulation").hexdigest(),
                    "size_bytes": 19,
                }
            ]
        if outcome == "needs_input":
            data["question"] = "SIMULATED: 请确认范围"
        result = s.RunResult(**data)
        with Session(self.app.state.engine) as db:
            response = tasks.record_run_result(db, UUID(run["id"]), result)
            db.commit()
        return response, result

    def input(self, kind="clarification", status=201, **fields):
        return self.write(
            "/inputs",
            {
                "expected_revision": self.get()["revision"],
                "kind": kind,
                "text": "SIMULATED follow-up",
                "evidence_artifact_ids": [],
                **fields,
            },
            status,
        )

    def adopt(self, apply=(), reject=(), status=200, **fields):
        return self.write(
            "/apply-inputs",
            {
                "expected_revision": self.get()["revision"],
                "apply_ids": list(apply),
                "reject_ids": list(reject),
                "reason": "明确处理模拟输入",
                **fields,
            },
            status,
        )

    def artifact(self, run):
        return self.client.get("/api/v1/runs/" + run["id"] + "/artifacts").json()[
            "items"
        ][0]["id"]

    def review(self, run, verdict="accept", status=201, key=None, **fields):
        task = self.get()
        return self.write(
            "/reviews",
            {
                "expected_revision": task["revision"],
                "run_id": run["id"],
                "task_spec_version": task["spec_version"],
                "artifact_ids": [self.artifact(run)],
                "verdict": verdict,
                "reason": "SIMULATED review",
                "check_evidence": ["deterministic control check"],
                **fields,
            },
            status,
            key,
        )
