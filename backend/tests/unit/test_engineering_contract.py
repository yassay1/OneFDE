"""Deterministic Engineering context, result contract, and workspace compare."""

import io
import tarfile
from pathlib import Path
from uuid import uuid4

import pytest

from onefde.core.engineering import CONTEXT_REVISION, ROLE_REVISION, derive_checks
from onefde.infrastructure.runtime import engineering as eng


def test_derive_checks_splits_automatic_and_review():
    checks = derive_checks(
        {
            "completion_criteria": [
                "[auto] python -m pytest -q",
                "[review] 业务样例结果正确",
                "未标注默认进入评审",
            ]
        }
    )
    assert [item["kind"] for item in checks] == [
        "automatic",
        "business_review",
        "business_review",
    ]
    assert checks[0]["command"] == "python -m pytest -q"


def test_context_excludes_pending_as_authorization_and_keeps_revisions():
    context = eng.build_context(
        {
            "spec": {
                "title": "t",
                "objective": "o",
                "scope": "s",
                "inputs": ["data only"],
                "confirmed_rules": ["r1"],
                "completion_criteria": ["[auto] true"],
            },
            "inputs": [{"id": str(uuid4()), "kind": "answer", "text": "adopted"}],
            "owner_role": "fde",
            "executor_role": "engineering",
            "permissions": ["engineering:task-workspace"],
            "model_profile": {
                "model": "openai/fixture",
                "provider": "fixture",
                "protocol": "openai_chat_completions",
            },
            "config": {
                "adapter": "openhands",
                "secret_ref": "env:ONEFDE_MODEL_TEST",
                "max_requests": 20,
            },
            "engineering": {
                "role_revision": ROLE_REVISION,
                "context_revision": CONTEXT_REVISION,
            },
        },
        task_id=uuid4(),
        run_id=uuid4(),
        engagement_id=uuid4(),
        spec_version=3,
        workspace_status={"status": "empty", "blocked": False},
    )
    assert context["revisions"]["role"] == ROLE_REVISION
    assert "Pending inputs" in context["pending_reminder"]
    prompt = eng.user_prompt(context)
    assert "secret_ref" in prompt and "ONEFDE_MODEL_TEST" in prompt
    assert "adopted" in prompt
    suffix = eng.agent_context_kwargs(context)
    assert suffix["load_user_skills"] is False
    assert ROLE_REVISION in suffix["system_message_suffix"]


def test_unrelated_exit_zero_cannot_satisfy_automatic_check():
    checks = derive_checks({"completion_criteria": ["[auto] python -m pytest -q"]})
    evidence = [
        {"command": "ls", "cwd": "/workspace", "exit_code": 0, "timeout": False}
    ]
    result, extras = eng.decide_result(
        {
            "outcome": "submitted",
            "summary": "done",
            "acceptance": [{"status": "passed"}],
        },
        reason="FINISHED",
        source_count=1,
        checks=checks,
        evidence=evidence,
    )
    assert result["state"] == "failed"
    assert result["error_code"] == "AUTOMATIC_CHECK_FAILED"
    assert extras["check_coverage"][0]["matched"] is False


def test_matching_automatic_check_and_source_can_submit():
    checks = derive_checks({"completion_criteria": ["[auto] python -m pytest -q"]})
    evidence = [
        {
            "command": "python -m pytest -q",
            "cwd": "/workspace",
            "exit_code": 0,
            "timeout": False,
        }
    ]
    result, extras = eng.decide_result(
        {"outcome": "submitted", "summary": "ok"},
        reason="FINISHED",
        source_count=2,
        checks=checks,
        evidence=evidence,
        validation={"passed": True, "results": evidence},
    )
    assert result == {
        "state": "completed",
        "outcome": "submitted",
        "summary": "ok",
        "stopped": True,
    }
    assert extras["check_coverage"][0]["matched"] is True


def test_invalid_json_and_self_report_do_not_discard_classification():
    result, _ = eng.decide_result(
        {},
        reason="RESULT_FORMAT_INVALID",
        source_count=1,
        checks=[],
        evidence=[{"exit_code": 0}],
    )
    assert result["error_code"] == "RESULT_FORMAT_INVALID"
    with pytest.raises(ValueError):
        eng.parse_proposal("not-json")


def test_parse_proposal_accepts_fenced_json_and_compound_checks():
    proposal = eng.parse_proposal(
        'Done.\n```json\n{"outcome":"submitted","summary":"ok"}\n```'
    )
    assert proposal["outcome"] == "submitted"
    checks = derive_checks({"completion_criteria": ["[auto] sh /workspace/check.sh"]})
    evidence = [
        {
            "command": "cd /workspace && sh /workspace/check.sh; echo done",
            "cwd": None,
            "exit_code": 0,
            "timeout": False,
        }
    ]
    result, extras = eng.decide_result(
        proposal,
        reason="FINISHED",
        source_count=1,
        checks=checks,
        evidence=evidence,
        validation={"passed": True},
    )
    assert result["outcome"] == "submitted"
    assert extras["check_coverage"][0]["matched"] is True


def _archive(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def test_workspace_compare_blocks_unknown_drift(tmp_path: Path):
    archive = _archive({"index.html": b"<html>v1</html>"})
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "index.html").write_bytes(b"<html>v1</html>")
    assert eng.evaluate_workspace_gate(workspace, archive)["blocked"] is False
    (workspace / "index.html").write_bytes(b"<html>changed</html>")
    gate = eng.evaluate_workspace_gate(workspace, archive)
    assert gate["blocked"] is True
    assert gate["comparison"]["changed"] == ["index.html"]


def test_restore_archive_roundtrip(tmp_path: Path):
    archive = _archive({"app.py": b"print(1)\n", "nested/a.txt": b"x"})
    target = tmp_path / "restored"
    restored = eng.restore_archive(archive, target, 1024)
    assert restored["file_count"] == 2
    assert (target / "app.py").read_text(encoding="utf-8") == "print(1)\n"
    assert eng.compare_workspace_to_archive(target, archive)["match"] is True


def _member(
    name: str, content: bytes = b"", *, kind: bytes | None = None, link: str = ""
):
    info = tarfile.TarInfo(name)
    if kind is None:
        info.size = len(content)
        payload = io.BytesIO(content)
    else:
        info.type = kind
        info.linkname = link
        payload = io.BytesIO(b"")
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        archive.addfile(info, payload)
    return buffer.getvalue()


def test_hidden_archive_names_roundtrip_and_escape_stays_rejected(tmp_path: Path):
    archive = _archive(
        {
            "./.gitignore": b"*.pyc\n",
            "./.github/workflows/ci.yml": b"name: ci\n",
        }
    )
    names = [item[0] for item in eng.archive_manifest(archive)]
    assert names == [".github/workflows/ci.yml", ".gitignore"]
    target = tmp_path / "hidden"
    restored = eng.restore_archive(archive, target, 1024)
    assert restored["file_count"] == 2
    assert (target / ".gitignore").read_bytes() == b"*.pyc\n"
    assert (target / ".github" / "workflows" / "ci.yml").read_bytes() == b"name: ci\n"
    assert eng.compare_workspace_to_archive(target, archive)["match"] is True
    for unsafe in (
        "../secret",
        "./../secret",
        "/etc/passwd",
        "nested/../../etc/passwd",
    ):
        escaped = tmp_path / "bad" / unsafe.replace("/", "_")
        with pytest.raises(ValueError, match="unsafe archive member"):
            eng.restore_archive(_member(unsafe, b"no"), escaped, 1024)
        assert not (escaped / "secret").exists()
        assert not (escaped / "passwd").exists()
    for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
        with pytest.raises(ValueError, match="unsafe archive member"):
            eng.restore_archive(
                _member("link", kind=kind, link="outside"),
                tmp_path / f"link-{kind}",
                1024,
            )


def test_spec_inputs_stay_inputs_and_spec_version_comes_from_the_run():
    context = eng.build_context(
        {
            "spec": {
                "title": "t",
                "objective": "o",
                "scope": "s",
                "inputs": [".gitignore"],
                "non_goals": ["do not deploy"],
                "confirmed_rules": [],
                "completion_criteria": ["[review] owner accepts"],
            },
            "inputs": [],
            "owner_role": "fde",
            "executor_role": "engineering",
        },
        task_id=uuid4(),
        run_id=uuid4(),
        engagement_id=uuid4(),
        spec_version=4,
    )
    assert context["identity"]["spec_version"] == 4
    assert context["goal"]["inputs"] == [".gitignore"]
    assert context["goal"]["non_goals"] == ["do not deploy"]
    assert ".gitignore" not in context["goal"]["non_goals"]
    prompt = eng.user_prompt(context)
    assert '"spec_version": 4' in prompt
    assert '"inputs": [".gitignore"]' in prompt


def test_frozen_source_check_rejects_added_files_and_keeps_tool_logs(tmp_path: Path):
    archive = _archive({"app.py": b"print(1)\n"})
    workspace = tmp_path / "workspace"
    eng.restore_archive(archive, workspace, 1024)
    (workspace / "dist").mkdir()
    (workspace / "dist" / "app.js").write_text("built", encoding="utf-8")
    (workspace / "bash_events").mkdir()
    (workspace / "bash_events" / "1.json").write_text("{}", encoding="utf-8")
    comparison = eng.compare_workspace_to_archive(workspace, archive)
    assert comparison["added"] == ["dist/app.js"]
    assert comparison["removed"] == [] and comparison["changed"] == []
    assert eng.frozen_source_unchanged(comparison) is False
    assert eng.is_frozen_source("bash_events/1.json") is False
    assert eng.is_frozen_source("dist/app.js") is True
    removed = tmp_path / "removed"
    eng.restore_archive(archive, removed, 1024)
    (removed / "app.py").unlink()
    assert (
        eng.frozen_source_unchanged(eng.compare_workspace_to_archive(removed, archive))
        is False
    )
