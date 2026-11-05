"""Actual pinned SDK types + fake Docker/Conversation; no model or sandbox call."""

import json
import threading
from types import SimpleNamespace
from uuid import uuid4

import pytest

from onefde.core.execution import ExecutionRequest
from onefde.infrastructure.runtime import openhands as binding
from onefde.worker.config import WorkerSettings


@pytest.mark.parametrize(
    "failure",
    [
        None,
        "health",
        "limits",
        "unknown-stop",
        "text-only",
        "needs-input",
        "deadline",
        "stop",
    ],
)
def test_pinned_sdk_binding_and_cleanup(tmp_path, monkeypatch, failure):
    sdk = pytest.importorskip(
        "openhands.sdk", reason="Install worker extra for SDK binding checks"
    )
    workspace_module = pytest.importorskip("openhands.workspace")
    settings = WorkerSettings(
        _env_file=None, root=tmp_path, max_cost_usd=0.1, poll_seconds=0.1
    )
    monkeypatch.setattr(WorkerSettings, "blockers", lambda _: [])
    monkeypatch.setenv("ONEFDE_MODEL_TEST", "scoped-fixture-only")
    actions, captured, identifier = [], {}, "a" * 64
    stop = threading.Event()
    if failure == "stop":
        stop.set()

    class FakeWorkspace:
        def __init__(self, **kwargs):
            captured["workspace"] = kwargs
            self._container_id = identifier
            self._wait_for_health(timeout=60)

        def _wait_for_health(self, *, timeout):
            if failure == "health":
                raise RuntimeError("health failed after allocation")

    class FakeConversation:
        def __init__(self, **kwargs):
            captured["conversation"] = kwargs
            assert kwargs["agent"].llm.num_retries == 0
            assert kwargs["agent"].condenser is None and kwargs["agent"].critic is None
            self.state = SimpleNamespace(
                execution_status="running" if failure == "deadline" else "finished"
            )

        def send_message(self, message):
            assert "frozen fixture" in message and "adopted fixture" in message
            assert "scoped-fixture-only" not in message
            assert (
                "engineering-role-v1"
                in captured["conversation"]["agent"].agent_context.system_message_suffix
            )

        def run(self, *, blocking):
            assert blocking is False and actions[0] == "update"
            actions.append("run")
            path = tmp_path / "tasks" / str(request.task_id) / "workspace/source.py"
            path.write_text('print("SIMULATED")', encoding="utf-8")
            value = {
                "outcome": "needs_input" if failure == "needs-input" else "submitted",
                "summary": "SIMULATED scoped-fixture-only",
            }
            if failure == "needs-input":
                value["question"] = "SIMULATED question"
            action = type(
                "FinishAction",
                (),
                {
                    "message": "not JSON"
                    if failure == "text-only"
                    else json.dumps(value)
                },
            )()
            observation = type(
                "TerminalObservation",
                (),
                {
                    "exit_code": 0,
                    "command": "python -m pytest -q",
                    "cwd": "/workspace",
                    "timeout": False,
                },
            )()
            for callback in captured["conversation"]["callbacks"]:
                callback(SimpleNamespace(action=action, observation=observation))

        def close(self):
            actions.append("close")

    def docker(*args):
        actions.append(args[0])
        if args[0] == "ps":
            return SimpleNamespace(
                returncode=1 if failure == "unknown-stop" else 0, stdout=""
            )
        return SimpleNamespace(
            returncode=1 if failure == "limits" and args[0] == "update" else 0,
            stdout="",
        )

    monkeypatch.setattr(workspace_module, "DockerWorkspace", FakeWorkspace)
    monkeypatch.setattr(sdk, "Conversation", FakeConversation)
    monkeypatch.setattr(binding, "docker", docker)
    if failure == "deadline":
        ticks = iter([0, 1000])
        monkeypatch.setattr(binding.time, "monotonic", lambda: next(ticks))
    request = ExecutionRequest(
        operation_id=uuid4(),
        run_id=uuid4(),
        task_id=uuid4(),
        engagement_id=uuid4(),
        snapshot={
            "spec_version": 1,
            "spec": {
                "objective": "frozen fixture",
                "completion_criteria": ["[review] owner accepts"],
            },
            "inputs": [{"text": "adopted fixture"}],
            "config": {
                "adapter": "openhands",
                "secret_ref": "env:ONEFDE_MODEL_TEST",
                "base_url": "https://model.example/v1",
            },
            "model_profile": {
                "protocol": "openai_chat_completions",
                "model": "openai/fixture",
            },
            "engineering": {
                "role_revision": "engineering-role-v1",
                "context_revision": "engineering-context-v1",
                "checks": [
                    {
                        "id": "review-1",
                        "kind": "business_review",
                        "criterion": "owner accepts",
                    }
                ],
            },
        },
        on_resource=lambda value: captured.update(resource=value),
    )
    result = binding.OpenHandsAdapter(settings).execute(request, stop)
    assert captured["resource"]["container_id"] == identifier
    assert captured["resource"]["role"] == "engineering"
    assert "stop" in actions and "ps" in actions
    assert captured["workspace"]["forward_env"] == [
        "OH_SESSION_API_KEYS_0",
        "OH_CONVERSATIONS_PATH",
    ]
    assert all("docker.sock" not in value for value in captured["workspace"]["volumes"])
    if failure == "unknown-stop":
        assert result.result["state"] == "interrupted" and not result.proof["stopped"]
    elif failure in ("health", "limits", "text-only", "deadline", "stop"):
        assert result.result["state"] == "failed" and result.proof["stopped"]
        if failure == "text-only":
            assert result.artifact_keys and result.result["artifacts"]
            assert result.result["error_code"] == "RESULT_FORMAT_INVALID"
    else:
        assert result.result["outcome"] == (
            "needs_input" if failure == "needs-input" else "submitted"
        )
        assert (
            result.artifact_keys
            and "scoped-fixture-only" not in result.result["summary"]
        )
        assert captured["conversation"]["max_iteration_per_run"] == 20
        assert captured["conversation"]["max_budget_per_run"] == 0.1
        assert result.proof["context_revisions"]["role"] == "engineering-role-v1"
    assert (tmp_path / "private" / str(request.run_id) / "session.key").is_file()
