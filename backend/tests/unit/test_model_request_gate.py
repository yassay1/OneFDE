"""Unpaid HTTP stand-in for the per-Run model request ceiling."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

import pytest

from onefde.core.execution import RuntimeUnavailable
from onefde.infrastructure.runtime import openhands as binding
from onefde.infrastructure.runtime.model_gate import (
    disable_remote_autotitle,
    start_model_gate,
)
from onefde.worker.config import WorkerSettings


class _StopRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = build_opener(_StopRedirect())


class _Upstream(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self._hit()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        self._hit()

    def _hit(self):
        self.server.hits += 1
        self.server.authorizations.append(self.headers.get("Authorization"))
        self.server.paths.append(self.path)
        if self.server.block is not None:
            self.server.entered.set()
            self.server.block.wait(2)
        status = 302 if self.path.endswith("/redirect") else self.server.status
        body = b'{"id":"stub"}'
        self.send_response(status)
        if status == 302:
            self.send_header("Location", "http://127.0.0.1:1/elsewhere")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


@pytest.fixture
def upstream():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Upstream)
    server.hits = 0
    server.status = 200
    server.block = None
    server.entered = threading.Event()
    server.authorizations = []
    server.paths = []
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}
    )
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def _gate(upstream, limit):
    port = upstream.server_address[1]
    return start_model_gate(
        "127.0.0.1",
        f"http://127.0.0.1:{port}/v1",
        limit,
        timeout=2,
    )


def _call(url, method="POST"):
    request = Request(
        url,
        data=b'{"messages":[]}' if method == "POST" else None,
        method=method,
        headers={
            "Authorization": "Bearer scoped-test",
            "Content-Type": "application/json",
        },
    )
    try:
        with _OPENER.open(request, timeout=2) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def test_budget_counts_failures_and_stops_before_the_next_upstream_call(upstream):
    gate = _gate(upstream, 3)
    try:
        assert _call(f"{gate.base_url}/chat/completions")[0] == 200
        assert _call(f"{gate.base_url}/responses")[0] == 200
        upstream.status = 500
        assert _call(f"{gate.base_url}/chat/completions")[0] == 500
        refused = _call(f"{gate.base_url}/chat/completions")
        assert refused[0] == 429
        assert json.loads(refused[1])["error"] == "request_budget_exhausted"
        assert upstream.hits == 3
        assert gate.forwarded == 3 and gate.refused == 1 and gate.remaining == 0
        assert upstream.authorizations == ["Bearer scoped-test"] * 3
        assert upstream.paths == [
            "/v1/chat/completions",
            "/v1/responses",
            "/v1/chat/completions",
        ]
    finally:
        gate.close()


def test_one_budget_is_shared_and_unknown_callers_are_not_forwarded(upstream):
    gate = _gate(upstream, 1)
    try:
        assert _call(f"{gate.base_url}/chat/completions")[0] == 200
        assert _call(f"{gate.base_url}/chat/completions")[0] == 429
        wrong = gate.base_url.replace(gate.base_url.split("/")[3], "wrong-token", 1)
        assert _call(f"{wrong}/chat/completions")[0] == 404
        assert _call(f"{gate.base_url}/chat/completions?stream=true", "GET")[0] == 400
        assert upstream.hits == 1
    finally:
        gate.close()


def test_concurrent_call_is_refused_while_the_first_is_still_upstream(upstream):
    upstream.block = threading.Event()
    gate = _gate(upstream, 1)
    outcomes = []

    def call():
        outcomes.append(_call(f"{gate.base_url}/chat/completions")[0])

    try:
        first = threading.Thread(target=call)
        second = threading.Thread(target=call)
        first.start()
        assert upstream.entered.wait(2)
        second.start()
        second.join(2)
        assert outcomes == [429]
        assert upstream.hits == 1 and gate.forwarded == 1 and gate.refused == 1
        upstream.block.set()
        first.join(2)
        assert sorted(outcomes) == [200, 429]
    finally:
        upstream.block.set()
        gate.close()


def test_redirect_is_not_followed_to_another_host(upstream):
    gate = _gate(upstream, 1)
    try:
        assert _call(f"{gate.base_url}/redirect")[0] == 302
        assert upstream.hits == 1
        assert upstream.paths == ["/v1/redirect"]
    finally:
        gate.close()


def test_gateway_and_autotitle_stay_inside_the_existing_boundary(monkeypatch):
    settings = WorkerSettings(_env_file=None, network="onefde-sandbox")

    def docker(*args):
        gateway = "8.8.8.8" if settings.network == "public-net" else "172.29.241.1"
        if args[:2] == ("network", "inspect"):
            payload = [{"IPAM": {"Config": [{"Gateway": gateway}]}}]
            return type(
                "Result", (), {"returncode": 0, "stdout": json.dumps(payload)}
            )()
        raise AssertionError(args)

    monkeypatch.setattr(binding, "docker", docker)
    assert binding.sandbox_gateway(settings) == "172.29.241.1"
    settings.network = "public-net"
    with pytest.raises(RuntimeUnavailable):
        binding.sandbox_gateway(settings)
    settings.network = "bad network"
    with pytest.raises(RuntimeUnavailable):
        binding.sandbox_gateway(settings)

    calls = []

    class Client:
        def request(self, method, url, **kwargs):
            calls.append(kwargs.get("json"))
            return "ok"

    workspace = type("Workspace", (), {"client": Client()})()
    disable_remote_autotitle(workspace)
    assert (
        workspace.client.request(
            "POST",
            "http://172.29.241.4:8000/api/conversations",
            json={"agent": {}, "max_iterations": 2},
        )
        == "ok"
    )
    assert calls[0]["autotitle"] is False
    assert calls[0]["max_iterations"] == 2
    assert workspace.client.request("GET", "/api/conversations/1", json={"agent": {}})
    assert "autotitle" not in calls[1]


def test_proxy_bypass_includes_the_model_gate_gateway(monkeypatch):
    settings = WorkerSettings(
        _env_file=None,
        network="onefde-sandbox",
        egress_proxy_url="http://172.29.241.3:3128",
    )

    def docker(*args):
        assert args[:2] == ("network", "inspect")
        payload = [{"IPAM": {"Config": [{"Gateway": "172.29.241.1"}]}}]
        return type("Result", (), {"returncode": 0, "stdout": json.dumps(payload)})()

    monkeypatch.setattr(binding, "docker", docker)
    flags = binding.sandbox_proxy_flags(settings)
    assert "NO_PROXY=localhost,127.0.0.1,172.29.241.1" in flags
    assert "HTTPS_PROXY=http://172.29.241.3:3128" in flags


def test_public_bind_and_provider_are_rejected():
    with pytest.raises(RuntimeUnavailable):
        start_model_gate("8.8.8.8", "https://model.example/v1", 1, timeout=1)
    with pytest.raises(RuntimeUnavailable):
        start_model_gate(
            "127.0.0.1", "https://user:secret@model.example/v1", 1, timeout=1
        )
