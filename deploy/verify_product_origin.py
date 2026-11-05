"""Serve the quote product on its own loopback origin and record the boundary.

Product origin: http://127.0.0.1:8765
Workbench origins stay http://127.0.0.1:8000 (dev API) and
http://127.0.0.1:8002 (local Compose). This script does not call a model,
start Compose, or publish the product.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "products" / "demo-supplier-quotes"
EVIDENCE = ROOT / "docs" / "operations" / "evidence" / "p4-product-origin.json"
HOST = "127.0.0.1"
PORT = 8765
PRODUCT_ORIGIN = f"http://{HOST}:{PORT}"
WORKBENCH_ORIGINS = (
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8002",
    "http://localhost:8000",
    "http://localhost:8002",
)
ALLOWED = {
    "index.html": "text/html; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
    "compare.js": "text/javascript; charset=utf-8",
    "check.mjs": "text/javascript; charset=utf-8",
    "check.sh": "text/plain; charset=utf-8",
    "README.md": "text/plain; charset=utf-8",
    "CHANGELOG.md": "text/plain; charset=utf-8",
}
FORBIDDEN = (*WORKBENCH_ORIGINS, "/api/v1")
PAGE_FILES = ("index.html", "app.js", "compare.js")


class ProductHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        name = "index.html" if path in ("", "/") else path.lstrip("/")
        if name not in ALLOWED or "/" in name or "\\" in name:
            self.send_error(404)
            return
        target = (PRODUCT / name).resolve()
        if target.parent != PRODUCT.resolve() or not target.is_file():
            self.send_error(404)
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ALLOWED[name])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return


def fetch(url):
    request = Request(url, headers={"Accept": "*/*"})
    try:
        with urlopen(request, timeout=3) as response:
            return response.status, dict(response.headers), response.read()
    except HTTPError as error:
        return error.code, dict(error.headers), error.read()


def require(condition, message, failures):
    if not condition:
        failures.append(message)


def script_sources(html):
    sources = []
    lower = html.lower()
    cursor = 0
    while True:
        start = lower.find("<script", cursor)
        if start < 0:
            break
        end = lower.find(">", start)
        tag = html[start:end]
        marker = 'src="'
        at = tag.find(marker)
        if at >= 0:
            value = tag[at + len(marker) :]
            sources.append(value.split('"', 1)[0])
        cursor = end + 1
    return sources


def probe_workbench():
    probes = []
    for origin in ("http://127.0.0.1:8000", "http://127.0.0.1:8002"):
        item = {"origin": origin, "running": False}
        try:
            status, _headers, body = fetch(origin + "/health")
            item["running"] = True
            item["health_status"] = status
            page_status, page_headers, page = fetch(origin + "/")
            text = page.decode("utf-8", "replace")
            item["root_status"] = page_status
            item["root_is_product"] = "模拟水果店报价比较" in text
            item["sets_cookie"] = "set-cookie" in {k.lower() for k in page_headers}
            item["health_body_is_product"] = "模拟水果店报价比较" in body.decode(
                "utf-8", "replace"
            )
        except (URLError, TimeoutError, OSError) as error:
            item["error"] = type(error).__name__
        probes.append(item)
    return probes


def product_check():
    completed = subprocess.run(
        ["node", "check.mjs"],
        cwd=PRODUCT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return {
        "command": "node products/demo-supplier-quotes/check.mjs",
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def main():
    failures = []
    probes = []
    sample = {"command": "node products/demo-supplier-quotes/check.mjs", "exit_code": None}
    try:
        server = ThreadingHTTPServer((HOST, PORT), ProductHandler)
    except OSError as error:
        failures.append(f"bind {HOST}:{PORT} failed: {error.strerror}")
        _write(failures, probes, sample)
        raise SystemExit(1) from error
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, headers, body = fetch(PRODUCT_ORIGIN + "/")
        html = body.decode("utf-8")
        sources = script_sources(html)
        require(status == 200, f"product index status {status}", failures)
        require("set-cookie" not in {k.lower() for k in headers}, "product set a cookie", failures)
        require("模拟水果店报价比较" in html, "product title missing", failures)
        require(sources == ["./compare.js", "./app.js"], f"script src {sources}", failures)
        for name in ("compare.js", "app.js"):
            code, file_headers, payload = fetch(f"{PRODUCT_ORIGIN}/{name}")
            require(code == 200, f"{name} status {code}", failures)
            require(
                "set-cookie" not in {k.lower() for k in file_headers},
                f"{name} set a cookie",
                failures,
            )
            require(b"QuoteCompare" in payload or b"quote" in payload.lower(), f"{name} empty", failures)
        for blocked in ("/health", "/api/v1/engagements", "/api/v1/auth/session"):
            code, _headers, _payload = fetch(PRODUCT_ORIGIN + blocked)
            require(code == 404, f"{blocked} status {code}", failures)
        for name in PAGE_FILES:
            text = (PRODUCT / name).read_text(encoding="utf-8")
            for token in FORBIDDEN:
                require(token not in text, f"{name} references {token}", failures)
        probes = probe_workbench()
        for probe in probes:
            if not probe["running"]:
                continue
            require(probe["origin"] != PRODUCT_ORIGIN, "origins collided", failures)
            require(not probe["root_is_product"], f"{probe['origin']} served the product", failures)
            require(
                not probe["health_body_is_product"],
                f"{probe['origin']} /health served the product",
                failures,
            )
        sample = product_check()
        require(sample["exit_code"] == 0, "node check.mjs failed", failures)
    except (URLError, TimeoutError, OSError) as error:
        failures.append(f"request failed: {type(error).__name__}")
    finally:
        server.shutdown()
        server.server_close()

    _write(failures, probes, sample)
    raise SystemExit(0 if not failures else 1)


def _write(failures, probes, sample):
    report = {
        "ok": not failures,
        "slice": "P4-product-origin",
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "product": "demo-supplier-quotes",
        "version": "v1.1",
        "product_origin": PRODUCT_ORIGIN,
        "bind": f"{HOST}:{PORT}",
        "workbench_origins": list(WORKBENCH_ORIGINS[:2]),
        "workbench_probes": probes,
        "sample_check": sample,
        "failures": failures,
        "model_called": False,
        "public_deployment": False,
        "notes": (
            "Loopback static origin only. HTML/JS are not served by the workbench API. "
            "Cloud HTTPS, demo video, and thin workbench pages are outside this check."
        ),
    }
    EVIDENCE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "evidence": str(EVIDENCE), "failures": failures}, ensure_ascii=False))


def serve():
    server = ThreadingHTTPServer((HOST, PORT), ProductHandler)
    print(PRODUCT_ORIGIN, flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true", help="keep the product origin listening")
    args = parser.parse_args()
    if args.serve:
        serve()
    else:
        main()
