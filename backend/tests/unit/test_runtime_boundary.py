import subprocess
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


def test_worker_settings_fail_closed_without_environment(tmp_path, monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Windows")
    settings = WorkerSettings(_env_file=None)
    assert len(settings.blockers()) >= 6
    with pytest.raises(ValidationError):
        WorkerSettings(_env_file=None, server_image="latest")
    with pytest.raises(ValidationError):
        WorkerSettings(_env_file=None, lease_seconds=3, heartbeat_seconds=5)


def test_session_environment_is_allowlisted_and_restored(monkeypatch):
    monkeypatch.setenv("OH_SESSION_API_KEYS_0", "existing-fixture")
    monkeypatch.setenv("ONEFDE_WORKER_DATABASE_URL", "must-not-be-forwarded")
    with pytest.raises(RuntimeError):
        with binding.server_environment("temporary-fixture") as names:
            assert names == ["OH_SESSION_API_KEYS_0", "OH_CONVERSATIONS_PATH"]
            raise RuntimeError()
    import os

    assert os.environ["OH_SESSION_API_KEYS_0"] == "existing-fixture"
