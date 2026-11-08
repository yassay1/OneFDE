"""Count each model HTTP call before it is forwarded.

OpenHands ``max_iteration_per_run`` increments after an agent step. Title
generation, prompt-cache retries, and other auxiliary completions are separate
HTTP calls, so an iteration allowance is not a request ceiling. This gate is
the ceiling: one budget for the whole Run, reserved before the upstream socket
opens. A refused call is not forwarded. The reviewed provider origin is the
only destination, and the path token is not a credential for that provider.
"""

import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import IPv4Address
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from onefde.core.execution import RuntimeUnavailable

_MAX_BODY = 8 * 1024 * 1024


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class RequestBudget:
    def __init__(self, limit):
        if limit < 1:
            raise RuntimeUnavailable("Model request budget must be positive")
        self.limit = limit
        self.forwarded = 0
        self.refused = 0
        self._lock = threading.Lock()

    @property
    def remaining(self):
        with self._lock:
            return self.limit - self.forwarded

    def reserve(self):
        """Occupy one slot before any upstream connection. Failures stay occupied."""
        with self._lock:
            if self.forwarded >= self.limit:
                self.refused += 1
                return False
            self.forwarded += 1
            return True


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self._forward()

    def do_POST(self):
        self._forward()

    def log_message(self, format, *args):
        return

    def _forward(self):
        length = self._length()
        if length is None:
            return
        body = self.rfile.read(length) if length else b""
        target = self._target()
        if target is None:
            return
        if not self.server.budget.reserve():
            self._reply(429, b'{"error":"request_budget_exhausted"}')
            return
        header_value = self.headers.get("Authorization")
        request = Request(target, data=body or None, method=self.command)
        content_type = self.headers.get("Content-Type")
        if content_type:
            request.add_header("Content-Type", content_type)
        if header_value:
            request.add_header("Authorization", header_value)
        request.add_header("Accept", self.headers.get("Accept", "application/json"))
        try:
            upstream = self.server.opener.open(request, timeout=self.server.timeout)
        except HTTPError as error:
            upstream = error
        except (URLError, TimeoutError, OSError):
            self._reply(502, b"")
            return
        try:
            with upstream:
                status = getattr(upstream, "status", None) or upstream.code
                payload = upstream.read(_MAX_BODY + 1)
                response_type = upstream.headers.get("Content-Type", "application/json")
        except (URLError, TimeoutError, OSError):
            self._reply(502, b"")
            return
        if len(payload) > _MAX_BODY:
            self._reply(502, b"")
            return
        self._reply(status, payload, response_type)

    def _target(self):
        path, separator, _query = self.path.partition("?")
        if separator or "\\" in path or ".." in path.split("/"):
            self._reply(400, b"")
            return None
        segment, separator, rest = path.lstrip("/").partition("/")
        try:
            matched = secrets.compare_digest(segment, self.server.token)
        except (TypeError, ValueError):
            matched = False
        if not separator or not matched:
            self._reply(404, b"")
            return None
        if not rest or rest.startswith("/"):
            self._reply(400, b"")
            return None
        return self.server.origin + "/" + rest

    def _length(self):
        raw = self.headers.get("Content-Length", "0")
        try:
            length = int(raw)
        except ValueError:
            self._reply(400, b"")
            return None
        if length < 0 or length > _MAX_BODY:
            self._reply(413, b"")
            return None
        return length

    def _reply(self, status, payload, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)


class _Server(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True


class ModelRequestGate:
    def __init__(self, server, thread, base_url, budget):
        self._server = server
        self._thread = thread
        self.base_url = base_url
        self.limit = budget.limit
        self._budget = budget

    @property
    def forwarded(self):
        return self._budget.forwarded

    @property
    def refused(self):
        return self._budget.refused

    @property
    def remaining(self):
        return self._budget.remaining

    def close(self):
        try:
            self._server.shutdown()
            self._thread.join(timeout=3)
            self._server.server_close()
        except OSError:
            return


def _bindable(host):
    try:
        address = IPv4Address(host)
    except ValueError:
        return False
    return (address.is_private or address.is_loopback) and not address.is_link_local


def _origin(upstream):
    parts = urlsplit(upstream)
    if parts.username or parts.password or parts.query or parts.fragment:
        raise RuntimeUnavailable("Model endpoint must not carry secrets or a query")
    if not parts.hostname:
        raise RuntimeUnavailable("Model endpoint has no host")
    loopback = parts.hostname in {"127.0.0.1", "localhost"}
    if parts.scheme == "https" or (parts.scheme == "http" and loopback):
        port = ""
        if parts.port and parts.port not in (80, 443):
            port = f":{parts.port}"
        return f"{parts.scheme}://{parts.hostname}{port}", parts.path.rstrip("/")
    raise RuntimeUnavailable("Model endpoint must be the reviewed HTTPS origin")


def start_model_gate(bind_host, upstream, limit, *, timeout, proxy_url=None):
    if not _bindable(bind_host):
        raise RuntimeUnavailable("Model gate can bind only a private sandbox address")
    origin, path = _origin(upstream)
    budget = RequestBudget(limit)
    token = secrets.token_urlsafe(24)
    proxy = ProxyHandler({"http": proxy_url, "https": proxy_url} if proxy_url else {})
    server = _Server((bind_host, 0), _Handler)
    server.budget = budget
    server.token = token
    server.origin = origin
    server.timeout = timeout
    server.opener = build_opener(proxy, _NoRedirect())
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.05},
        name="onefde-model-gate",
        daemon=True,
    )
    thread.start()
    port = server.server_address[1]
    return ModelRequestGate(
        server, thread, f"http://{bind_host}:{port}/{token}{path}", budget
    )


def disable_remote_autotitle(workspace):
    """The pinned server titles a new conversation with another model call."""
    client = getattr(workspace, "client", None)
    original = getattr(client, "request", None)
    if original is None or getattr(original, "_onefde_autotitle", False):
        return

    def request(method, url, *args, **kwargs):
        if str(method).upper() == "POST":
            route = urlsplit(str(url)).path.rstrip("/")
            body = kwargs.get("json")
            if route == "/api/conversations" and isinstance(body, dict):
                kwargs["json"] = {**body, "autotitle": False}
        return original(method, url, *args, **kwargs)

    request._onefde_autotitle = True
    client.request = request
