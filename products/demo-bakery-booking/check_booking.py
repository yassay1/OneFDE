"""Run from the project root with python -m unittest -v check_booking."""

import json
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from booking import make_server


class BookingChecks(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "booking.sqlite"
        self.server = make_server(self.path, 0, "2026-11-06")
        self.addCleanup(self.server.server_close)
        worker = Thread(target=self.server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.a = self.login("baker-a", "demo-a")
        self.b = self.login("baker-b", "demo-b")

    def request(self, path, token=None, payload=None):
        headers = {"Origin": self.url, "Content-Type": "application/json"}
        if token:
            headers["Cookie"] = token
        request = Request(
            self.url + path,
            headers=headers,
            data=json.dumps(payload).encode() if payload is not None else None,
        )
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            return (
                response.status,
                json.load(response),
                response.headers.get("Set-Cookie"),
            )

    def login(self, staff, code):
        status, _, cookie = self.request(
            "/api/session", payload={"staff": staff, "code": code}
        )
        self.assertEqual(status, 200)
        return cookie.split(";", 1)[0]

    def reserve(self, token, start, end, key):
        return self.request(
            "/api/bookings", token, {"start": start, "end": end, "request_key": key}
        )

    def count(self):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute(
                "SELECT count(*) FROM booking WHERE cancelled=0"
            ).fetchone()[0]

    def test_refresh_and_boundaries(self):
        self.assertEqual(self.reserve(self.a, "10:00", "11:00", "r1")[0], 201)
        self.assertEqual(
            self.request("/api/bookings", self.a)[1]["items"][0]["start"], "10:00"
        )
        for start, end in [("10:30", "11:30"), ("09:00", "12:00"), ("10:00", "11:00")]:
            self.assertEqual(self.reserve(self.b, start, end, "conflict")[0], 409)
        self.assertEqual(self.reserve(self.b, "11:00", "12:00", "adjacent")[0], 201)
        for start, end in [("10:00", "10:00"), ("11:00", "10:00"), ("24:00", "10:00")]:
            self.assertEqual(self.reserve(self.a, start, end, "invalid")[0], 400)
        self.assertEqual(self.count(), 2)

    def test_competing_requests(self):
        barrier = Barrier(2)

        def compete(token):
            barrier.wait(timeout=5)
            return self.reserve(token, "10:00", "11:00", "compete")[0]

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(compete, (self.a, self.b)))
        self.assertEqual(sorted(results), [201, 409])
        self.assertEqual(self.count(), 1)

    def test_retry_permissions_and_release(self):
        created = self.reserve(self.a, "09:00", "10:00", "retry")
        self.assertEqual(created[0], 201)
        replayed = self.reserve(self.a, "09:00", "10:00", "retry")
        self.assertEqual((replayed[0], replayed[1]["id"]), (200, created[1]["id"]))
        self.assertEqual(self.reserve(self.a, "09:00", "11:00", "retry")[0], 409)
        booking = {"id": created[1]["id"]}
        self.assertEqual(self.request("/api/cancel", self.b, booking)[0], 403)
        self.assertEqual(self.request("/api/cancel", payload=booking)[0], 401)
        self.assertEqual(self.count(), 1)
        self.assertEqual(self.request("/api/cancel", self.a, booking)[0], 200)
        self.assertEqual(self.request("/api/cancel", self.a, booking)[0], 200)
        self.assertEqual(self.reserve(self.b, "09:00", "10:00", "freed")[0], 201)
        self.assertEqual(self.count(), 1)
