"""Dedicated trusted Linux Worker process; never part of the API process."""

import argparse
import json
import logging
import signal
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from sqlalchemy.orm import Session

from onefde.infrastructure.db.session import make_engine
from onefde.worker.config import SDK_VERSION, WorkerSettings


def inspect_environment(settings):
    blockers, versions = settings.blockers(), {}
    for package in ("openhands-sdk", "openhands-workspace", "openhands-tools"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = None
        if versions[package] != SDK_VERSION:
            blockers.append(f"{package}版本缺失或不匹配，请安装worker extra")
    from onefde.infrastructure.runtime.openhands import docker

    try:
        result = docker("info", "--format", "{{.OSType}}")
        if result.returncode or result.stdout.strip() != "linux":
            blockers.append("Docker Linux Engine不可用")
    except Exception:
        blockers.append("Docker Engine检查失败")
    return {
        "sdk_versions": versions,
        "blockers": blockers,
        "model_credentials": "按Run冻结的secret_ref解析；环境检查不调用模型",
    }


def main():
    logging.getLogger("openhands").setLevel(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "once", "run", "import-profile"))
    parser.add_argument("--file", type=Path, help="Non-secret model configuration JSON")
    args = parser.parse_args()
    settings = WorkerSettings()
    if args.command == "import-profile":
        if not settings.database_url or not args.file:
            parser.error("import-profile requires Worker database URL and --file")
        from onefde.modules.tasks.configuration import (
            ModelConfiguration,
            provision_model,
        )

        # Validate before opening a transaction; never print file contents/secrets.
        config = ModelConfiguration.model_validate_json(
            args.file.read_text(encoding="utf-8")
        )
        engine = make_engine(settings.database_url.get_secret_value())
        try:
            with Session(engine) as db, db.begin():
                identifier = provision_model(db, config)
            print(
                json.dumps(
                    {"revision_id": str(identifier), "integration_status": "configured"}
                )
            )
        finally:
            engine.dispose()
        return
    report = inspect_environment(settings)
    if args.command == "check" or report["blockers"]:
        print(json.dumps(report, ensure_ascii=False))
        if report["blockers"]:
            sys.exit(2)
        return
    from onefde.infrastructure.runtime.openhands import OpenHandsAdapter
    from onefde.worker.controller import Worker

    settings.root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if settings.root.is_symlink() or settings.root.stat().st_mode & 0o077:
        parser.error("Worker root must be a private directory (chmod 700)")
    engine = make_engine(settings.database_url.get_secret_value())
    worker = Worker(engine, settings, OpenHandsAdapter(settings))
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: worker.shutdown.set())
    try:
        if args.command == "once":
            print(json.dumps({"processed": worker.run_once()}))
        else:
            while not worker.shutdown.is_set():
                if not worker.run_once():
                    worker.shutdown.wait(settings.poll_seconds)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
