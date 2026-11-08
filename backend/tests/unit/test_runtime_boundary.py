import subprocess
from pathlib import PurePosixPath
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from onefde.core.execution import RuntimeUnavailable
from onefde.infrastructure.artifacts import PrivateArtifactStore
from onefde.infrastructure.runtime import openhands as binding
from onefde.modules.tasks.configuration import ModelConfiguration
from onefde.worker.config import WorkerSettings


def test_model_configuration_contains_references_only(monkeypatch):
    payload = dict(
        provider="fixture",
        model="openai/fixture",
        base_url="https://model.example/v1",
        secret_ref="env:ONEFDE_MODEL_TEST",
    )
    config = ModelConfiguration(**payload)
    assert config.max_requests == 20
    for changes in (
        {"api_key": "never-persist-this"},
        {"base_url": "https://user:password@host/v1"},
        {"secret_ref": "env:ONEFDE_DATABASE_URL"},
        {"max_requests": 21},
        {"timeout_seconds": 0},
    ):
        with pytest.raises(ValidationError):
            ModelConfiguration(**{**payload, **changes})
    snapshot = {
        "config": {"adapter": "openhands", **config.model_dump()},
        "model_profile": {"protocol": "openai_chat_completions", "model": config.model},
    }
    monkeypatch.delenv("ONEFDE_MODEL_TEST", raising=False)
    with pytest.raises(RuntimeUnavailable):
        binding.resolve_model(snapshot)
    monkeypatch.setenv("ONEFDE_MODEL_TEST", "fixture-not-a-real-secret")
    assert binding.resolve_model(snapshot) == "fixture-not-a-real-secret"


def test_private_store_rejects_escape_and_is_immutable(tmp_path):
    store = PrivateArtifactStore(tmp_path)
    evidence = store.put("run/source", b"test")
    assert store.put("run/source", b"test") == evidence
    store.verify("run/source", evidence)
    for key in ("../outside", "/absolute", "a\\escape"):
        with pytest.raises(ValueError):
            store.put(key, b"bad")
    with pytest.raises(ValueError):
        store.put("run/source", b"overwrite")
    with pytest.raises(ValueError):
        store.verify("run/source", {**evidence, "size_bytes": 0})


@pytest.mark.parametrize(
    "inventory,inspection,expected",
    [
        ("absent", None, True),
        ("present", "false", True),
        ("present", "true", False),
        ("unavailable", None, False),
    ],
)
def test_stop_confirmation_uses_daemon_evidence(
    monkeypatch, inventory, inspection, expected
):
    identifier = "a" * 64

    def fake(*args):
        if args[0] == "stop":
            return SimpleNamespace(returncode=1, stdout="")
        if args[0] == "ps":
            return SimpleNamespace(
                returncode=1 if inventory == "unavailable" else 0,
                stdout=identifier if inventory == "present" else "",
            )
        return SimpleNamespace(returncode=0, stdout=inspection)

    monkeypatch.setattr(binding, "docker", fake)
    assert binding.confirm_stopped(identifier) is expected


def test_stop_daemon_timeout_is_unknown(monkeypatch):
    def timeout(*args):
        raise subprocess.TimeoutExpired("docker", 45)

    monkeypatch.setattr(binding, "docker", timeout)
    assert binding.confirm_stopped("a" * 64) is False


@pytest.mark.parametrize("last_code,expected", [(0, True), (1, False)])
def test_stop_auto_remove_race_needs_fresh_inventory(monkeypatch, last_code, expected):
    identifier = "a" * 64
    results = iter(
        [
            SimpleNamespace(returncode=0, stdout=""),
            SimpleNamespace(returncode=0, stdout=identifier),
            SimpleNamespace(returncode=1, stdout=""),
            SimpleNamespace(returncode=last_code, stdout=""),
        ]
    )
    monkeypatch.setattr(binding, "docker", lambda *a: next(results))
    assert binding.confirm_stopped(identifier) is expected


def test_worker_settings_fail_closed_without_environment(tmp_path, monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Windows")
    settings = WorkerSettings(_env_file=None)
    assert len(settings.blockers()) >= 6
    with pytest.raises(ValidationError):
        WorkerSettings(_env_file=None, server_image="latest")
    with pytest.raises(ValidationError):
        WorkerSettings(_env_file=None, lease_seconds=3, heartbeat_seconds=5)


def test_reviewed_browser_image_capability_is_explicit():
    from onefde.worker.config import BROWSER_AGENT_SERVER_IMAGE

    base = WorkerSettings(_env_file=None)
    browser = WorkerSettings(_env_file=None, server_image=BROWSER_AGENT_SERVER_IMAGE)
    assert base.browser_support is None
    assert browser.browser_support["executable_path"] == "/usr/bin/chromium"
    with pytest.raises(ValidationError):
        WorkerSettings(_env_file=None, server_image="onefde-agent-browser:latest")


def test_session_environment_is_allowlisted_and_restored(monkeypatch):
    monkeypatch.setenv("OH_SESSION_API_KEYS_0", "existing-fixture")
    monkeypatch.setenv("ONEFDE_WORKER_DATABASE_URL", "must-not-be-forwarded")
    with pytest.raises(RuntimeError):
        with binding.server_environment("temporary-fixture") as names:
            assert names == ["OH_SESSION_API_KEYS_0", "OH_CONVERSATIONS_PATH"]
            raise RuntimeError()
    import os

    assert os.environ["OH_SESSION_API_KEYS_0"] == "existing-fixture"


def test_local_mode_requires_wsl_and_separate_development_confirmation(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.release", lambda: "6.18-microsoft-standard-WSL2")
    settings = WorkerSettings(
        _env_file=None,
        execution_mode="local_wsl",
        local_development_confirmed=True,
        database_url="postgresql+psycopg://worker:fixture@localhost/demo",
        root="/home/onefde/runtime",
        network="onefde-engineering-offline",
    )
    settings = settings.model_copy(
        update={"root": PurePosixPath("/home/onefde/runtime")}
    )
    assert not settings.isolated_host_confirmed
    assert settings.blockers(environment_only=True) == []
    # Environment readiness must never authorize model execution or bypass budget.
    assert len(settings.blockers()) == 2
    assert settings.model_copy(update={"local_development_confirmed": False}).blockers(
        environment_only=True
    )
    assert settings.model_copy(
        update={"root": PurePosixPath("/mnt/d/runtime")}
    ).blockers(environment_only=True)
    monkeypatch.setattr("platform.release", lambda: "6.18-generic")
    assert settings.blockers(environment_only=True)


def test_environment_only_flag_cannot_start_worker(monkeypatch):
    from onefde.entrypoints import worker

    monkeypatch.setattr("sys.argv", ["worker", "once", "--environment-only"])
    with pytest.raises(SystemExit) as error:
        worker.main()
    assert error.value.code == 2


def test_disabled_worker_does_not_create_database_engine(monkeypatch, tmp_path):
    from onefde.entrypoints import worker

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["worker", "once"])
    monkeypatch.setattr(
        worker,
        "inspect_environment",
        lambda *a, **k: {"blockers": ["model execution disabled"]},
    )

    def forbidden(*args, **kwargs):
        pytest.fail("Disabled execution must not connect or claim jobs")

    monkeypatch.setattr(worker, "make_engine", forbidden)
    with pytest.raises(SystemExit) as error:
        worker.main()
    assert error.value.code == 2


def test_shared_mode_requires_own_confirmation_without_model_authorization(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Linux")
    settings = WorkerSettings(
        _env_file=None,
        execution_mode="ecs_shared",
        shared_host_confirmed=True,
        database_url="postgresql+psycopg://worker:fixture@postgres/demo",
        root="/srv/onefde-local/worker",
        network="onefde-local-sandbox",
    ).model_copy(update={"root": PurePosixPath("/srv/onefde-local/worker")})
    assert settings.blockers(environment_only=True) == []
    assert len(settings.blockers()) == 2
    for changes in (
        {"shared_host_confirmed": False},
        {"isolated_host_confirmed": True},
    ):
        assert settings.model_copy(update=changes).blockers(environment_only=True)


@pytest.mark.parametrize("failure", ["unbounded", "disk", "memory", "unavailable"])
def test_shared_admission_fails_closed(monkeypatch, failure):
    import os
    from pathlib import Path

    settings = WorkerSettings(
        _env_file=None, execution_mode="ecs_shared", root="/fixture"
    )

    def space(_):
        if failure == "unavailable":
            raise OSError("fixture")
        return SimpleNamespace(
            f_blocks=4 * 1024**3 if failure == "unbounded" else 2 * 1024**3,
            f_frsize=1,
            f_bavail=0 if failure == "disk" else 512 * 1024**2,
        )

    monkeypatch.setattr(os, "statvfs", space, raising=False)
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda _: (
            "MemAvailable: " + ("0" if failure == "memory" else "8388608") + " kB"
        ),
    )
    assert settings.capacity_blockers()


def test_capacity_refusal_never_claims_or_creates_runtime(monkeypatch, tmp_path):
    from onefde.worker.controller import Worker

    settings = WorkerSettings(_env_file=None, root=tmp_path)
    monkeypatch.setattr(WorkerSettings, "capacity_blockers", lambda _: ["low capacity"])
    worker = Worker(None, settings, None)
    monkeypatch.setattr(
        worker, "transaction", lambda *args: pytest.fail("Must not claim")
    )
    assert worker.run_once() is False
    assert worker.last_admission == ["low capacity"]
