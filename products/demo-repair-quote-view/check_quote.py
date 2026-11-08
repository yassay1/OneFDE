"""Verify authorization against the actual loopback server."""

import json
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from repair_quotes import make_server


class QuoteChecks(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.database = Path(folder.name) / "quotes.sqlite"
        self.server = make_server(self.database, 0)
        self.addCleanup(self.server.server_close)
        Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.a = self.login("customer-a", "demo-a")
        self.b = self.login("customer-b", "demo-b")
        self.shop = self.login("shop", "demo-shop")

    def call(self, path, cookie=None, body=None):
        headers = {"Origin": self.url, "Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        request = Request(
            self.url + path,
            headers=headers,
            data=json.dumps(body).encode() if body is not None else None,
        )
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response), response.headers

    def login(self, account, code):
        status, _, headers = self.call(
            "/api/session", body={"account": account, "code": code}
        )
        self.assertEqual(status, 200)
        return headers["Set-Cookie"].split(";", 1)[0]

    def test_customer_ownership(self):
        status, own, headers = self.call("/api/quotes/R101", self.a)
        self.assertEqual(
            (status, own["amount_minor"], headers["Cache-Control"]),
            (200, 12800, "no-store"),
        )
        self.assertEqual(self.call("/api/quotes/R202", self.b)[0], 200)
        unauthorized = self.call("/api/quotes/R101", self.b)
        missing = self.call("/api/quotes/R999", self.b)
        self.assertEqual(unauthorized[:2], missing[:2])
        self.assertEqual(unauthorized[0], 404)
        self.assertEqual(set(unauthorized[1]), {"message"})
        self.assertEqual(self.call("/api/quotes/R101")[0], 401)

    def test_shop_controls_and_old_url(self):
        path = "/api/quotes/R101"
        self.assertEqual(self.call(path + "/withdraw", self.b, {})[0], 403)
        self.assertEqual(self.call(path, self.a)[0], 200)
        self.assertEqual(self.call(path + "/withdraw", self.shop, {})[0], 200)
        blocked = self.call(path, self.a)
        self.assertEqual(blocked[0], 404)
        self.assertEqual(blocked[2]["Cache-Control"], "no-store")
        self.assertEqual(blocked[:2], self.call("/api/quotes/R999", self.a)[:2])
        self.assertEqual(self.call(path, self.shop)[1]["state"], "withdrawn")
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(
                db.execute("SELECT state FROM quote WHERE id='R101'").fetchone(),
                ("withdrawn",),
            )
        draft = "/api/quotes/R303"
        self.assertEqual(self.call(draft, self.a)[0], 404)
        self.assertEqual(self.call(draft + "/publish", self.a, {})[0], 403)
        self.assertEqual(self.call(draft + "/publish", self.shop, {})[0], 200)
        self.assertEqual(self.call(draft, self.a)[0], 200)
