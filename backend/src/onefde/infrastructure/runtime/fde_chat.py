"""OpenAI-compatible tool calling for FDE; no business access."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_REQUEST_BYTES = 128_000
MAX_OUTPUT_TOKENS = 1600
MAX_RESPONSE_BYTES = 96_000


class ModelFailure(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ChatModel:
    def __init__(self, profile, secret):
        self.profile = profile
        self.secret = secret
        self.http = build_opener(NoRedirect())

    def __call__(self, messages, tools):
        options = {
            "model": self.profile.model.removeprefix("openai/"),
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "max_tokens": MAX_OUTPUT_TOKENS,
            "n": 1,
            "stream": False,
        }
        if self.profile.provider.lower() in ("deepseek", "mimo"):
            options["thinking"] = {"type": "disabled"}
        if self.profile.provider.lower() == "mimo":
            options["max_completion_tokens"] = options.pop("max_tokens")
        encoded = json.dumps(
            options, ensure_ascii=False, separators=(",", ":")
        ).encode()
        if len(encoded) > MAX_REQUEST_BYTES:
            raise ModelFailure("FDE_CONTEXT_LIMIT")
        request = Request(
            self.profile.base_url.rstrip("/") + "/chat/completions",
            data=encoded,
            headers={
                "Authorization": f"Bearer {self.secret}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self.http.open(
                request, timeout=self.profile.timeout_seconds
            ) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            raise ModelFailure(f"FDE_PROVIDER_HTTP_{exc.code}") from None
        except (OSError, URLError):
            raise ModelFailure("FDE_PROVIDER_UNREACHABLE") from None
        try:
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError
            result = json.loads(raw)
            choice = result["choices"][0]
            message = choice["message"]
            if message.get("role") != "assistant" or choice["finish_reason"] not in (
                "stop",
                "tool_calls",
            ):
                raise ValueError
            calls = message.get("tool_calls") or []
            if len(calls) > 4 or len({call["id"] for call in calls}) != len(calls):
                raise ValueError
            if any(
                item.get("type") != "function"
                or not isinstance(item["id"], str)
                or not isinstance(item["function"]["name"], str)
                or not isinstance(item["function"]["arguments"], str)
                or len(item["function"]["arguments"]) > 24_000
                for item in calls
            ):
                raise ValueError
            content = message.get("content")
            if content is not None and not isinstance(content, str):
                raise ValueError
            clean = {"role": "assistant", "content": content}
            if calls:
                clean["tool_calls"] = [
                    {
                        "id": item["id"],
                        "type": "function",
                        "function": {
                            "name": item["function"]["name"],
                            "arguments": item["function"]["arguments"],
                        },
                    }
                    for item in calls
                ]
            usage = {
                k: v
                for k, v in (result.get("usage") or {}).items()
                if k
                in (
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "prompt_cache_hit_tokens",
                )
                and type(v) is int
                and v >= 0
            }
            return clean, usage
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            raise ModelFailure("FDE_PROVIDER_RESPONSE_INVALID") from None
