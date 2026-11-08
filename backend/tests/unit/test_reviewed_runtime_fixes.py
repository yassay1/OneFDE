"""Counterexamples for the reviewed validation and context defects. No model or SDK."""

import io
import tarfile
import threading
import time
from types import SimpleNamespace
from uuid import uuid4

from onefde.core.execution import ExecutionRequest
from onefde.infrastructure.runtime import openhands as binding
from onefde.worker.config import WorkerSettings

ENGINEERING = "a" * 64
VALIDATION = "b" * 64


def _archive(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def _request(tmp_path):
    return ExecutionRequest(
        operation_id=uuid4(),
        run_id=uuid4(),
        task_id=uuid4(),
        engagement_id=uuid4(),
        snapshot={"spec_version": 2, "spec": {"inputs": ["kept-as-input"]}},
        on_resource=lambda value: None,
    )


def _settings(tmp_path):
    return WorkerSettings(_env_file=None, root=tmp_path)


def _checks():
    return [
        {"id": "auto-1", "kind": "automatic", "command": "first", "cwd": "/workspace"},
        {"id": "auto-2", "kind": "automatic", "command": "second", "cwd": "/workspace"},
    ]


def test_validation_exception_with_unknown_stop_stays_interrupted(
    tmp_path, monkeypatch
):
    settings = _settings(tmp_path)
    request = _request(tmp_path)
    workspace = tmp_path / "tasks" / str(request.task_id) / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "app.py").write_text("print(1)\n", encoding="utf-8")
    seen = []

    def confirm(container_id):
        seen.append(container_id)
        return container_id == ENGINEERING

    def explode(*args):
        args[-1]({"container_id": VALIDATION, "image": "fixture", "network": "net"})
        raise RuntimeError("validation container init failed")

    monkeypatch.setattr(binding, "confirm_stopped", confirm)
    monkeypatch.setattr(binding, "shared_workspace", explode)
    proof = {"stopped": True, "resources": []}
    result = binding.OpenHandsAdapter(settings)._finalize_stopped_run(
        request,
        threading.Event(),
        time.monotonic() + 30,
        workspace,
        [{"role": "engineering", "container_id": ENGINEERING}],
        proof,
        reason="FINISHED",
        finished=['{"outcome":"submitted","summary":"ok"}'],
        messages=[],
        evidence=[],
        checks=_checks(),
        credential="scoped-fixture-only",
        session_key="session-secret",
    )
    assert VALIDATION in seen
    assert result.result["state"] == "interrupted"
    assert result.result["stopped"] is False
    assert result.result["error_code"] == "STOP_UNCONFIRMED"
    assert result.proof["stopped"] is False


def test_validation_cleanup_exception_with_unknown_stop_stays_interrupted(
    tmp_path, monkeypatch
):
    settings = _settings(tmp_path)
    request = _request(tmp_path)
    workspace = tmp_path / "tasks" / str(request.task_id) / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "app.py").write_text("print(1)\n", encoding="utf-8")
    calls = {VALIDATION: 0}

    def confirm(container_id):
        if container_id == ENGINEERING:
            return True
        calls[container_id] = calls.get(container_id, 0) + 1
        return calls[container_id] == 1

    class Fake:
        def execute_command(self, command, cwd, timeout):
            return SimpleNamespace(exit_code=0, timeout_occurred=False)

        def cleanup(self):
            raise RuntimeError("validation cleanup failed")

    def launch(*args):
        args[-1]({"container_id": VALIDATION, "image": "fixture", "network": "net"})
        return Fake()

    monkeypatch.setattr(binding, "confirm_stopped", confirm)
    monkeypatch.setattr(binding, "shared_workspace", launch)
    result = binding.OpenHandsAdapter(settings)._finalize_stopped_run(
        request,
        threading.Event(),
        time.monotonic() + 30,
        workspace,
        [{"role": "engineering", "container_id": ENGINEERING}],
        {"stopped": True},
        reason="FINISHED",
        finished=['{"outcome":"submitted","summary":"ok"}'],
        messages=[],
        evidence=[],
        checks=_checks()[:1],
        credential="scoped-fixture-only",
        session_key="session-secret",
    )
    assert calls[VALIDATION] >= 2
    assert result.result["state"] == "interrupted"
    assert result.result["stopped"] is False
    assert result.proof["stopped"] is False


def test_cancelled_or_expired_validation_creates_no_container(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    request = _request(tmp_path)
    archive = _archive({"app.py": b"print(1)\n"})
    created = []
    monkeypatch.setattr(
        binding, "shared_workspace", lambda *args: created.append("container")
    )
    monkeypatch.setattr(binding, "confirm_stopped", lambda container_id: True)
    adapter = binding.OpenHandsAdapter(settings)
    stop = threading.Event()
    stop.set()
    cancelled = adapter._validate_fixed_source(
        request, archive, _checks(), [], stop, time.monotonic() + 30
    )
    expired = adapter._validate_fixed_source(
        request, archive, _checks(), [], threading.Event(), time.monotonic() - 1
    )
    assert created == []
    assert cancelled["error_code"] == "STOP_REQUESTED"
    assert expired["error_code"] == "EXECUTION_DEADLINE"
    assert cancelled["passed"] is False and expired["passed"] is False
    assert not (
        tmp_path / "tasks" / str(request.task_id) / "validation" / str(request.run_id)
    ).exists()


def test_running_validation_check_stops_before_the_next_check(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    request = _request(tmp_path)
    archive = _archive({"app.py": b"print(1)\n"})
    commands, released = [], threading.Event()
    clock = {"now": 1_000.0}

    monkeypatch.setattr(binding.time, "monotonic", lambda: clock["now"])

    class Fake:
        def execute_command(self, command, cwd, timeout):
            commands.append(command)
            clock["now"] = 9_000.0
            assert released.wait(3)
            return SimpleNamespace(exit_code=0, timeout_occurred=False)

        def cleanup(self):
            return None

    def launch(*args):
        args[-1]({"container_id": VALIDATION, "image": "fixture", "network": "net"})
        return Fake()

    def confirm(container_id):
        released.set()
        return True

    monkeypatch.setattr(binding, "shared_workspace", launch)
    monkeypatch.setattr(binding, "confirm_stopped", confirm)
    result = binding.OpenHandsAdapter(settings)._validate_fixed_source(
        request,
        archive,
        _checks(),
        [],
        threading.Event(),
        1_030.0,
    )
    assert commands == ["first"]
    assert released.is_set()
    assert result["passed"] is False
    assert result["error_code"] == "EXECUTION_DEADLINE"


def test_stop_during_validation_check_does_not_run_later_checks(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    request = _request(tmp_path)
    archive = _archive({"app.py": b"print(1)\n"})
    commands, started, released = [], threading.Event(), threading.Event()
    stop = threading.Event()

    class Fake:
        def execute_command(self, command, cwd, timeout):
            commands.append(command)
            started.set()
            assert released.wait(3)
            return SimpleNamespace(exit_code=0, timeout_occurred=False)

        def cleanup(self):
            return None

    def launch(*args):
        args[-1]({"container_id": VALIDATION, "image": "fixture", "network": "net"})
        return Fake()

    def confirm(container_id):
        released.set()
        return True

    def cancel_once_running():
        assert started.wait(3)
        stop.set()

    monkeypatch.setattr(binding, "shared_workspace", launch)
    monkeypatch.setattr(binding, "confirm_stopped", confirm)
    threading.Thread(target=cancel_once_running, daemon=True).start()
    result = binding.OpenHandsAdapter(settings)._validate_fixed_source(
        request,
        archive,
        _checks(),
        [],
        stop,
        time.monotonic() + 30,
    )
    assert commands == ["first"]
    assert result["error_code"] == "STOP_REQUESTED"
    assert result["passed"] is False


def test_new_source_during_validation_is_not_unchanged(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    request = _request(tmp_path)
    archive = _archive({"app.py": b"print(1)\n"})
    workspace = (
        tmp_path
        / "tasks"
        / str(request.task_id)
        / "validation"
        / str(request.run_id)
        / "workspace"
    )

    class Fake:
        def execute_command(self, command, cwd, timeout):
            if command == "first":
                target = workspace / "dist"
                target.mkdir()
                (target / "app.js").write_text("new", encoding="utf-8")
            return SimpleNamespace(exit_code=0, timeout_occurred=False)

        def cleanup(self):
            return None

    def launch(*args):
        args[-1]({"container_id": VALIDATION, "image": "fixture", "network": "net"})
        return Fake()

    monkeypatch.setattr(binding, "shared_workspace", launch)
    monkeypatch.setattr(binding, "confirm_stopped", lambda container_id: True)
    added = binding.OpenHandsAdapter(settings)._validate_fixed_source(
        request,
        archive,
        _checks()[:1],
        [],
        threading.Event(),
        time.monotonic() + 30,
    )
    assert added["comparison"]["added"] == ["dist/app.js"]
    assert added["comparison"]["removed"] == [] and added["comparison"]["changed"] == []
    assert added["source_unchanged"] is False
    assert added["passed"] is False
    assert added["error_code"] == "SOURCE_MUTATED_DURING_VALIDATION"

    request = _request(tmp_path)
    workspace = (
        tmp_path
        / "tasks"
        / str(request.task_id)
        / "validation"
        / str(request.run_id)
        / "workspace"
    )

    class LogsOnly:
        def execute_command(self, command, cwd, timeout):
            log = workspace / "bash_events"
            log.mkdir()
            (log / "1.json").write_text("{}", encoding="utf-8")
            return SimpleNamespace(exit_code=0, timeout_occurred=False)

        def cleanup(self):
            return None

    monkeypatch.setattr(
        binding,
        "shared_workspace",
        lambda *args: (
            args[-1]({"container_id": VALIDATION, "image": "fixture", "network": "net"})
            or LogsOnly()
        ),
    )
    allowed = binding.OpenHandsAdapter(settings)._validate_fixed_source(
        request,
        archive,
        _checks()[:1],
        [],
        threading.Event(),
        time.monotonic() + 30,
    )
    assert allowed["source_unchanged"] is True
    assert allowed["passed"] is True
    assert "bash_events/1.json" not in allowed["comparison"]["added"]
