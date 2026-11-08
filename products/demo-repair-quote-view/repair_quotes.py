"""Local repair-shop quotation demo. Use synthetic accounts only."""

import argparse
import json
import re
import secrets
import sqlite3
from contextlib import closing
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

ACCOUNTS = {"customer-a": "demo-a", "customer-b": "demo-b", "shop": "demo-shop"}
QUOTE_PATH = re.compile(r"/api/quotes/(R[0-9]{3})(?:/(publish|withdraw))?")
UNAVAILABLE = "这份报价暂不可查看。请联系维修店。"
SEED = (
    ("R101", "customer-a", "A-配件与检测", 12800, "published"),
    ("R202", "customer-b", "B-更换配件", 23500, "published"),
    ("R303", "customer-a", "草稿零件", 9600, "draft"),
)


def make_server(database, port):
    def connect():
        return sqlite3.connect(database, timeout=5)

    with closing(connect()) as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS quote (
            id TEXT PRIMARY KEY, customer TEXT NOT NULL, detail TEXT NOT NULL,
            amount_minor INTEGER NOT NULL, state TEXT NOT NULL
        )""")
        db.executemany("INSERT OR IGNORE INTO quote VALUES (?,?,?,?,?)", SEED)
    sessions, lock = {}, Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send_bytes(self, status, body, content_type, cookie=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Length", str(len(body)))
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(body)

        def reply(self, status, payload, cookie=None):
            self.send_bytes(
                status,
                json.dumps(payload, ensure_ascii=False).encode(),
                "application/json; charset=utf-8",
                cookie,
            )

        def actor(self):
            cookies = SimpleCookie()
            try:
                cookies.load(self.headers.get("Cookie", ""))
            except CookieError:
                return None
            key = cookies.get("repair_quote_session")
            with lock:
                return sessions.get(key.value) if key else None

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/":
                self.send_bytes(
                    200,
                    Path(__file__).with_name("index.html").read_bytes(),
                    "text/html; charset=utf-8",
                )
                return
            route = QUOTE_PATH.fullmatch(path)
            if not route or route[2]:
                self.reply(404, {"message": UNAVAILABLE})
                return
            actor = self.actor()
            if not actor:
                self.reply(401, {"message": "请先使用你的试用账号登录。"})
                return
            with closing(connect()) as db:
                row = db.execute(
                    "SELECT customer,detail,amount_minor,state FROM quote WHERE id=?",
                    (route[1],),
                ).fetchone()
            if (
                not row
                or actor != "shop"
                and (row[0] != actor or row[3] != "published")
            ):
                self.reply(404, {"message": UNAVAILABLE})
                return
            self.reply(
                200,
                {
                    "id": route[1],
                    "detail": row[1],
                    "amount_minor": row[2],
                    "state": row[3],
                    "can_manage": actor == "shop",
                },
            )

        def do_POST(self):
            origin = f"http://127.0.0.1:{self.server.server_port}"
            if (
                self.headers.get("Origin") != origin
                or self.headers.get_content_type() != "application/json"
            ):
                self.reply(403, {"message": "请从报价页操作。"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 4096:
                    raise ValueError
                payload = json.loads(self.rfile.read(size))
            except (ValueError, UnicodeError):
                self.reply(400, {"message": "无法读取本次操作。"})
                return
            if not isinstance(payload, dict):
                self.reply(400, {"message": "无法读取本次操作。"})
                return
            if self.path == "/api/session":
                actor = payload.get("account")
                if (
                    not isinstance(actor, str)
                    or actor not in ACCOUNTS
                    or ACCOUNTS[actor] != payload.get("code")
                ):
                    self.reply(401, {"message": "试用账号或试用码有误。"})
                    return
                token = secrets.token_urlsafe(24)
                with lock:
                    sessions[token] = actor
                self.reply(
                    200,
                    {"message": "已登录。"},
                    f"repair_quote_session={token}; Path=/; HttpOnly; SameSite=Strict",
                )
                return
            route = QUOTE_PATH.fullmatch(self.path)
            if not route or not route[2]:
                self.reply(404, {"message": UNAVAILABLE})
                return
            if self.actor() != "shop":
                self.reply(403, {"message": "只有维修店员可以管理报价。"})
                return
            state = {"publish": "published", "withdraw": "withdrawn"}[route[2]]
            with closing(connect()) as db, db:
                updated = db.execute(
                    "UPDATE quote SET state=? WHERE id=?", (state, route[1])
                )
            if not updated.rowcount:
                self.reply(404, {"message": UNAVAILABLE})
                return
            self.reply(
                200,
                {
                    "state": state,
                    "message": "报价已撤回。"
                    if state == "withdrawn"
                    else "报价已发布。",
                },
            )

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--port", type=int, default=8806)
    args = parser.parse_args()
    with make_server(args.database, args.port) as server:
        server.serve_forever()
