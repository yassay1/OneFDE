"""Real no-model Coding Agent checks inside the trusted Worker host.

Covers workspace compare, automatic-check contract, and fixed-source validation
with DockerWorkspace. Does NOT create Agent/LLM or consume business jobs.
"""

from __future__ import annotations

import json
import logging
import secrets
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from onefde.infrastructure.artifacts import PrivateArtifactStore
from onefde.infrastructure.runtime import engineering as eng
from onefde.infrastructure.runtime.openhands import (
    archive_workspace,
    confirm_stopped,
    shared_workspace,
)
from onefde.worker.config import WorkerSettings

logging.getLogger("openhands").setLevel(logging.CRITICAL)
settings = WorkerSettings()
assert settings.execution_mode == "ecs_shared"
assert not settings.model_execution_enabled
assert settings.blockers(environment_only=True) == []

report = {
    "scope": "coding_agent_no_model",
    "model_called": False,
    "checked_at_utc": datetime.now(UTC).isoformat(),
    "checks": [],
    "task_id": str(uuid4()),
    "run_id": str(uuid4()),
}


def passed(name):
    report["checks"].append(name)


root = settings.root / "evidence" / "coding-agent" / report["run_id"]
if root.exists():
    shutil.rmtree(root)
workspace = root / "workspace"
session = root / "session"
workspace.mkdir(parents=True)
session.mkdir(parents=True)
(workspace / "index.html").write_text(
    "<!doctype html><title>OneFDE CA demo</title><h1>ok</h1>\n", encoding="utf-8"
)
(workspace / "check.sh").write_text(
    "#!/bin/sh\ntest -f /workspace/index.html && grep -q '<h1>ok</h1>' /workspace/index.html\n",
    encoding="utf-8",
)
(workspace / "check.sh").chmod(0o700)
archive, count = archive_workspace(workspace, settings.max_artifact_bytes)
assert count >= 2
store = PrivateArtifactStore(settings.root / "artifacts")
key = f"environment/coding-agent/{report['run_id']}/workspace.tar.gz"
evidence = store.put(key, archive)
store.verify(key, evidence)
passed("frozen source archive created without model")

# Drift gate: unknown edits block; matching tree does not.
gate = eng.evaluate_workspace_gate(workspace, archive)
assert gate["blocked"] is False
(workspace / "index.html").write_text("<h1>drift</h1>\n", encoding="utf-8")
assert eng.evaluate_workspace_gate(workspace, archive)["blocked"] is True
(workspace / "index.html").write_text(
    "<!doctype html><title>OneFDE CA demo</title><h1>ok</h1>\n", encoding="utf-8"
)
passed("workspace compare blocks unknown drift and accepts matching tree")

# Result contract: unrelated exit 0 cannot satisfy registered automatic check.
checks = eng.derive_checks(
    {"completion_criteria": ["[auto] sh /workspace/check.sh", "[review] owner accepts"]}
)
bad, extras = eng.decide_result(
    {
        "outcome": "submitted",
        "summary": "self passed",
        "acceptance": [{"status": "passed"}],
    },
    reason="FINISHED",
    source_count=count,
    checks=checks,
    evidence=[{"command": "ls", "cwd": "/workspace", "exit_code": 0, "timeout": False}],
)
assert bad["error_code"] == "AUTOMATIC_CHECK_FAILED"
assert extras["check_coverage"][0]["matched"] is False
passed("unrelated exit 0 and self-reported passed rejected for submission")

# Fixed-source validation container: restore archive, run registered check, no model.
validation_root = root / "validation"
validation_workspace = validation_root / "workspace"
validation_session = validation_root / "session"
validation_session.mkdir(parents=True)
restored = eng.restore_archive(
    archive, validation_workspace, settings.max_artifact_bytes
)
before = restored["digest"]
session_key = secrets.token_urlsafe(32)
containers = []


def allocated(reference):
    containers.append(reference["container_id"])


workspace_client = None
try:
    workspace_client = shared_workspace(
        settings,
        validation_workspace,
        validation_session,
        session_key,
        allocated,
    )
    observed = workspace_client.execute_command(
        "sh /workspace/check.sh", cwd="/workspace", timeout=30
    )
    assert observed.exit_code == 0
    # Mutating a frozen source member must be detected even if bash_events appear.
    observed_write = workspace_client.execute_command(
        "sh -c 'echo dirty >> /workspace/index.html'", cwd="/workspace", timeout=30
    )
    assert observed_write.exit_code == 0
finally:
    stopped = confirm_stopped(containers[0] if containers else None)
    if workspace_client is not None and stopped:
        workspace_client.cleanup()
mutated = eng.compare_workspace_to_archive(validation_workspace, archive)
assert stopped
assert mutated["changed"] == ["index.html"]
passed(
    "validation container ran registered check; source mutation detected; stop confirmed"
)

# Clean restore + successful validation without mutation.
shutil.rmtree(validation_root)
validation_session.mkdir(parents=True)
eng.restore_archive(archive, validation_workspace, settings.max_artifact_bytes)
before = eng.workspace_digest(validation_workspace)
containers = []
workspace_client = None
try:
    workspace_client = shared_workspace(
        settings,
        validation_workspace,
        validation_session,
        session_key,
        allocated,
    )
    observed = workspace_client.execute_command(
        "sh /workspace/check.sh", cwd="/workspace", timeout=30
    )
    assert observed.exit_code == 0
finally:
    stopped = confirm_stopped(containers[0] if containers else None)
    if workspace_client is not None and stopped:
        workspace_client.cleanup()
intact = eng.compare_workspace_to_archive(validation_workspace, archive)
assert stopped and not intact["removed"] and not intact["changed"]
ok, proof = eng.decide_result(
    {"outcome": "submitted", "summary": "demo page ready"},
    reason="FINISHED",
    source_count=count,
    checks=checks,
    evidence=[
        {
            "command": "sh /workspace/check.sh",
            "cwd": "/workspace",
            "exit_code": 0,
            "timeout": False,
        }
    ],
    validation={
        "passed": True,
        "stopped": True,
        "source_unchanged": True,
        "results": [
            {
                "command": "sh /workspace/check.sh",
                "exit_code": 0,
                "timeout": False,
            }
        ],
    },
)
assert ok["outcome"] == "submitted"
report["artifact"] = {**evidence, "local_key": key, "file_count": count}
report["source_digest"] = intact["archive_digest"]
report["validation"] = proof.get("validation")
report["source_comparison"] = {
    "changed": intact["changed"],
    "removed": intact["removed"],
    "added_source_members": intact["added"],
}
passed("fixed-source validation passed with unchanged digest and typed submission")

out = Path("work")
out.mkdir(exist_ok=True)
path = out / "coding-agent-no-model.json"
path.write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(
    json.dumps(
        {
            "passed": len(report["checks"]),
            "model_called": False,
            "evidence": str(path),
            "artifact_sha256": evidence["sha256"],
        }
    )
)
