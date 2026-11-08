"""Isolated local demo: own PostgreSQL volume, credentials and application port.

Never resets an existing database or consumes model jobs. Run from backend.
"""

import argparse
import json
import os
import secrets
import subprocess
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from argon2 import PasswordHasher
from dotenv import dotenv_values
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "work" / "product-demo.env"
CONTAINER = "onefde-product-demo-db"
LABEL = "onefde.local-demo=product-v1"
IMAGE = "postgres:17.7-bookworm@sha256:86e0b703649d7a792bd9243ee28afc9d8f7c6b2b5638077c9d6882d4d472bbfd"


def docker_prefix():
    for prefix in (["docker"], ["wsl", "-d", "OneFDE", "--", "docker"]):
        try:
            check = subprocess.run(
                [*prefix, "info", "--format", "{{.ServerVersion}}"],
                capture_output=True,
                timeout=45,
            )
            if check.returncode == 0:
                return prefix
        except (OSError, subprocess.TimeoutExpired):
            continue
    raise SystemExit("Docker不可用。请启动Docker Desktop或专用OneFDE WSL的Docker。")


def setup():
    prefix = docker_prefix()
    existing = subprocess.run(
        [*prefix, "inspect", CONTAINER], capture_output=True, text=True
    )
    if not ENV.exists():
        if existing.returncode == 0:
            raise SystemExit(
                "演示容器已存在但私有配置丢失；请恢复配置，不覆盖卷或密码。"
            )
        ENV.parent.mkdir(exist_ok=True)
        db_password, password = secrets.token_hex(20), secrets.token_urlsafe(18)
        values = {
            "ONEFDE_ENVIRONMENT": "development",
            "ONEFDE_DATABASE_URL": f"postgresql+psycopg://onefde_demo:{db_password}@127.0.0.1:55434/onefde_product_demo",
            "ONEFDE_TEST_DATABASE_URL": f"postgresql+psycopg://onefde_demo:{db_password}@127.0.0.1:55434/onefde_product_acceptance_test",
            "ONEFDE_OWNER_USERNAME": "founder",
            "ONEFDE_OWNER_PASSWORD_HASH": PasswordHasher().hash(password),
            "ONEFDE_TRUSTED_ORIGIN": "http://localhost:8003",
            "ONEFDE_BUSINESS_CUSTOMER_ORIGIN": "http://127.0.0.1:8765",
            "ONEFDE_COOKIE_SECURE": "false",
            "POSTGRES_PASSWORD": db_password,
        }
        ENV.write_text(
            "\n".join(f"{k}='{v}'" for k, v in values.items()) + "\n",
            encoding="utf-8",
        )
        (ENV.parent / "product-demo-login.txt").write_text(
            f"仅本机独立演示环境 http://localhost:8003\n账号：founder\n密码：{password}\n",
            encoding="utf-8",
        )
    values = dotenv_values(ENV)
    if existing.returncode == 0:
        info = json.loads(existing.stdout)[0]
        if info["Config"]["Labels"].get("onefde.local-demo") != "product-v1":
            raise SystemExit("同名容器不属于本演示，停止以保护现有数据。")
        subprocess.run([*prefix, "start", CONTAINER], check=True, capture_output=True)
    else:
        db_environment = (
            "POSTGRES_USER=onefde_demo\nPOSTGRES_DB=onefde_product_demo\n"
            f"POSTGRES_PASSWORD={values['POSTGRES_PASSWORD']}\n"
        )
        if prefix[0] == "wsl":
            env_path = "/home/onefde/private/product-demo-postgres.env"
            subprocess.run(
                [
                    "wsl",
                    "-d",
                    "OneFDE",
                    "--",
                    "sh",
                    "-c",
                    "umask 077; mkdir -p /home/onefde/private; cat > /home/onefde/private/product-demo-postgres.env",
                ],
                input=db_environment,
                text=True,
                check=True,
            )
        else:
            db_env = ENV.parent / "product-demo-postgres.env"
            db_env.write_text(db_environment, encoding="utf-8")
            env_path = str(db_env)
        subprocess.run(
            [
                *prefix,
                "run",
                "-d",
                "--name",
                CONTAINER,
                "--label",
                LABEL,
                "--restart",
                "unless-stopped",
                "-p",
                "127.0.0.1:55434:5432",
                "--mount",
                "type=volume,source=onefde-product-demo-pg,target=/var/lib/postgresql/data",
                "--env-file",
                env_path,
                "--health-cmd",
                "pg_isready -U onefde_demo -d onefde_product_demo",
                "--health-interval",
                "2s",
                "--health-retries",
                "30",
                IMAGE,
            ],
            text=True,
            check=True,
            capture_output=True,
        )
    # pg_isready waits inside the dedicated container, no credentials in output.
    for _ in range(30):
        ready = subprocess.run(
            [
                *prefix,
                "exec",
                CONTAINER,
                "pg_isready",
                "-U",
                "onefde_demo",
                "-d",
                "onefde_product_demo",
            ],
            capture_output=True,
        )
        if ready.returncode == 0:
            break
        time.sleep(1)
    else:
        raise SystemExit("专用演示数据库未就绪，请检查容器日志。")
    exists = subprocess.run(
        [
            *prefix,
            "exec",
            "-i",
            CONTAINER,
            "psql",
            "-U",
            "onefde_demo",
            "-d",
            "postgres",
            "-At",
        ],
        input="SELECT 1 FROM pg_database WHERE datname='onefde_product_acceptance_test';\n",
        check=True,
        text=True,
        capture_output=True,
    )
    if not exists.stdout.strip():
        subprocess.run(
            [
                *prefix,
                "exec",
                CONTAINER,
                "createdb",
                "-U",
                "onefde_demo",
                "onefde_product_acceptance_test",
            ],
            check=True,
        )
    load()
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    engine = create_engine(os.environ["ONEFDE_DATABASE_URL"])
    with engine.connect() as db:
        version = db.scalar(text("SELECT version_num FROM alembic_version"))
    engine.dispose()
    print(f"演示库迁移完成：{version}；原开发库未修改。")
    print("登录信息：backend/work/product-demo-login.txt（私有，不提交）")
    print("启动：uv run --locked python -m scripts.local_demo serve")


def load():
    if not ENV.exists():
        raise SystemExit("先运行 python -m scripts.local_demo setup")
    for key, value in dotenv_values(ENV).items():
        if key.startswith("ONEFDE_") and value is not None:
            os.environ[key] = value


def product():
    """Serve the actual product with a response-only local API origin override."""
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    directory = ROOT.parent / "products" / "demo-supplier-quotes"

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def do_GET(self):
            if self.path.split("?", 1)[0] in ("/", "/index.html"):
                body = (
                    (directory / "index.html")
                    .read_bytes()
                    .replace(
                        b'data-api-origin="http://127.0.0.1:8000"',
                        b'data-api-origin="http://localhost:8003"',
                    )
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

    print("本地客户产品：http://127.0.0.1:8765（真实产品；不自动执行模型）", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("setup", "serve", "seed", "test", "product")
    )
    args = parser.parse_args()
    os.chdir(ROOT)
    if args.command == "setup":
        setup()
        return
    load()
    if args.command == "product":
        product()
        return
    if args.command == "seed":
        from scripts.seed_local_demo import main as seed

        seed()
        return
    if args.command == "test":
        # Only the dedicated disposable test database can be truncated by pytest.
        url = os.environ["ONEFDE_TEST_DATABASE_URL"]
        if not url.endswith("/onefde_product_acceptance_test"):
            raise SystemExit("拒绝测试：不是专用验收测试库。")
        raise SystemExit(
            subprocess.call(
                ["uv", "run", "--locked", "--extra", "worker", "pytest", "-q"]
            )
        )
    import uvicorn

    uvicorn.run(
        "onefde.entrypoints.api:create_app", factory=True, host="127.0.0.1", port=8003
    )


if __name__ == "__main__":
    main()
