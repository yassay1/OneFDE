"""Verify the compatible tool protocol without any provider traffic."""

import io
import json
from types import SimpleNamespace

import pytest

from onefde.infrastructure.runtime.fde_chat import ChatModel, ModelFailure


@pytest.mark.parametrize("provider", ["deepseek", "mimo"])
def test_chat_completion_preserves_tool_id_and_usage(provider):
    model = ChatModel(
        SimpleNamespace(
            model="openai/"
            + ("deepseek-flash" if provider == "deepseek" else "mimo-v2.6-pro"),
            provider=provider,
            base_url="https://example.invalid/v1",
            timeout_seconds=10,
        ),
        "fixture-not-a-real-key",
    )

    def open_request(request, timeout):
        payload = json.loads(request.data)
        assert request.full_url == "https://example.invalid/v1/chat/completions"
        assert timeout == 10 and payload["model"] == model.profile.model.removeprefix(
            "openai/"
        )
        assert payload["tool_choice"] == "auto"
        assert payload["thinking"] == {"type": "disabled"}
        if provider == "mimo":
            assert payload["max_completion_tokens"] == 1600
            assert "max_tokens" not in payload
        assert payload["messages"][-1]["tool_call_id"] == "previous"
        return io.BytesIO(
            json.dumps(
                {
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "reasoning_content": "excluded",
                                "tool_calls": [
                                    {
                                        "id": "next",
                                        "type": "function",
                                        "function": {
                                            "name": "read_project",
                                            "arguments": "{}",
                                        },
                                    }
                                ],
                            },
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 42,
                        "completion_tokens": 5,
                        "total_tokens": 47,
                    },
                }
            ).encode()
        )

    model.http.open = open_request
    message, usage = model(
        [{"role": "tool", "tool_call_id": "previous", "content": "{}"}], []
    )
    assert message["tool_calls"][0]["id"] == "next"
    assert "reasoning_content" not in message
    assert usage["total_tokens"] == 47


def test_transport_fails_closed_for_oversized_context():
    model = ChatModel(
        SimpleNamespace(
            model="openai/fixture",
            provider="fixture",
            base_url="https://example.invalid",
            timeout_seconds=10,
        ),
        "fixture-not-a-real-key",
    )
    with pytest.raises(ModelFailure, match="FDE_CONTEXT_LIMIT"):
        model([{"role": "user", "content": "x" * 128_000}], [])
