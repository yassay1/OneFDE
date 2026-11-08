"""Loopback-only shared mixer booking demonstration."""

import argparse
import json
import re
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock

STAFF = {"baker-a": "demo-a", "baker-b": "demo-b"}
CLOCK = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")
KEY = re.compile(r"[a-zA-Z0-9-]{1,64}")


class BookingError(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


def minutes(value):
    if not isinstance(value, str) or not CLOCK.fullmatch(value):
        raise BookingError(400, "请填写有效的开始和结束时间。")
    hour, minute = map(int, value.split(":"))
    return 60 * hour + minute


def hhmm(value):
    return f"{value // 60:02}:{value % 60:02}"


class BookingStore:
    def __init__(self, path):
        self.path = path
        with closing(self.connect()) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS booking (
                  id INTEGER PRIMARY KEY, day TEXT NOT NULL, owner TEXT NOT NULL,
                  start INTEGER NOT NULL, end INTEGER NOT NULL, request_key TEXT NOT NULL,
                  cancelled INTEGER NOT NULL DEFAULT 0,
                  UNIQUE(day, owner, request_key)
                );
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def list(self, day, actor):
        with closing(self.connect()) as db:
            return [
                {
                    "id": row["id"],
                    "start": hhmm(row["start"]),
                    "end": hhmm(row["end"]),
                    "mine": row["owner"] == actor,
                }
                for row in db.execute(
                    "SELECT * FROM booking WHERE day=? AND cancelled=0 ORDER BY start,id",
                    (day,),
                )
            ]

    def reserve(self, day, actor, payload):
        start, end = minutes(payload.get("start")), minutes(payload.get("end"))
        key = payload.get("request_key")
        if start >= end:
            raise BookingError(400, "结束时间需要晚于开始时间。")
        if not isinstance(key, str) or not KEY.fullmatch(key):
            raise BookingError(400, "提交编号无效，请刷新后再试。")
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT id,start,end FROM booking WHERE day=? AND owner=? AND request_key=?",
                (day, actor, key),
            ).fetchone()
            if previous:
                if (previous["start"], previous["end"]) != (start, end):
                    raise BookingError(409, "这次提交的时段已变更，请重新确认。")
                return previous["id"], False
            if db.execute(
                "SELECT 1 FROM booking WHERE day=? AND cancelled=0 AND start<? AND end>?",
                (day, end, start),
            ).fetchone():
                raise BookingError(409, "这个时段已经被同事预约，请换一个时间。")
            row = db.execute(
                "INSERT INTO booking(day,owner,start,end,request_key) VALUES (?,?,?,?,?)",
                (day, actor, start, end, key),
            )
            return row.lastrowid, True

    def cancel(self, day, actor, booking_id):
        if type(booking_id) is not int:
            raise BookingError(400, "预约编号无效。")
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT owner FROM booking WHERE day=? AND id=?", (day, booking_id)
            ).fetchone()
            if row is None:
                raise BookingError(404, "没有找到这笔预约。")
            if row["owner"] != actor:
                raise BookingError(403, "只有预约人可以取消这笔预约。")
            db.execute("UPDATE booking SET cancelled=1 WHERE id=?", (booking_id,))


def make_server(database, port, day=None):
    store = BookingStore(database)
    sessions = {}
    lock = Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def body(self):
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 4096:
                    raise ValueError
                value = json.loads(self.rfile.read(size))
                if not isinstance(value, dict):
                    raise TypeError
                return value
            except (ValueError, TypeError, UnicodeError):
                raise BookingError(400, "提交内容无效，请刷新后再试。") from None

        def send_json(self, status, value, cookie=None):
            data = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(data)

        def actor(self):
            cookies = SimpleCookie()
            try:
                cookies.load(self.headers.get("Cookie", ""))
            except CookieError:
                raise BookingError(401, "请先登录。") from None
            token = cookies.get("booking_session")
            with lock:
                actor = sessions.get(token.value) if token else None
            if actor is None:
                raise BookingError(401, "请先登录。")
            return actor

        def day(self):
            return day or datetime.now(timezone(timedelta(hours=8))).date().isoformat()

        def do_GET(self):
            if self.path == "/":
                data = Path(__file__).with_name("index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                return
            try:
                if self.path != "/api/bookings":
                    raise BookingError(404, "找不到这个页面。")
                actor = self.actor()
                today = self.day()
                self.send_json(200, {"day": today, "items": store.list(today, actor)})
            except BookingError as error:
                self.send_json(error.status, {"message": str(error)})

        def do_POST(self):
            try:
                if (
                    self.headers.get("Origin")
                    != f"http://127.0.0.1:{self.server.server_port}"
                ):
                    raise BookingError(403, "请从预约页面提交。")
                if self.headers.get_content_type() != "application/json":
                    raise BookingError(415, "请从预约页面提交。")
                payload = self.body()
                if self.path == "/api/session":
                    actor = payload.get("staff")
                    if (
                        not isinstance(actor, str)
                        or actor not in STAFF
                        or STAFF[actor] != payload.get("code")
                    ):
                        raise BookingError(401, "账号或试用码不正确。")
                    token = secrets.token_urlsafe(24)
                    with lock:
                        sessions[token] = actor
                    self.send_json(
                        200,
                        {"message": "已登录。"},
                        f"booking_session={token}; Path=/; HttpOnly; SameSite=Strict",
                    )
                    return
                actor = self.actor()
                today = self.day()
                if self.path == "/api/bookings":
                    booking_id, created = store.reserve(today, actor, payload)
                    self.send_json(
                        201 if created else 200,
                        {"id": booking_id, "message": "预约已保存。"},
                    )
                elif self.path == "/api/cancel":
                    store.cancel(today, actor, payload.get("id"))
                    self.send_json(
                        200, {"message": "已取消，其他同事现在可以预约这个时段。"}
                    )
                else:
                    raise BookingError(HTTPStatus.NOT_FOUND, "找不到这个页面。")
            except BookingError as error:
                self.send_json(error.status, {"message": str(error)})
            except sqlite3.OperationalError:
                self.send_json(503, {"message": "预约暂时无法保存，请重试。"})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--port", type=int, default=8796)
    parser.add_argument("--day")
    args = parser.parse_args()
    with make_server(args.database, args.port, args.day) as server:
        server.serve_forever()
