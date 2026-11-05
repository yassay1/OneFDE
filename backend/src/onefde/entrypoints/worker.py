"""Dedicated trusted Linux Worker process; never part of the API process."""

import argparse
import json
import logging
import signal
import sys
import threading
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from sqlalchemy.orm import Session

from onefde.infrastructure.db.session import make_engine
from onefde.worker.config import SDK_VERSION, WorkerSettings


def inspect_environment(settings, *, environment_only=False):
    blockers, versions = settings.blockers(environment_only=environment_only), {}
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
    if settings.execution_mode in ("local_wsl", "ecs_shared"):
        if settings.root and (
            not settings.root.is_dir()
            or settings.root.is_symlink()
            or settings.root.stat().st_mode & 0o077
        ):
            blockers.append("本地Worker目录须存在且权限为700")
        if not settings.model_execution_enabled and settings.network:
            try:
                network = docker("network", "inspect", settings.network)
                if network.returncode or not json.loads(network.stdout)[0]["Internal"]:
                    blockers.append("无模型本地环境必须使用internal离线网络")
            except Exception:
                blockers.append("无法确认本地工程离线网络")
    blockers.extend(settings.capacity_blockers())
    return {
        "scope": "environment_only" if environment_only else "execution_preflight",
        "execution_mode": settings.execution_mode,
        "model_execution_enabled": settings.model_execution_enabled,
        "sdk_versions": versions,
        "blockers": blockers,
        "model_credentials": "按Run冻结的secret_ref解析；环境检查不调用模型",
    }


def main():
    logging.getLogger("openhands").setLevel(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("check", "once", "run", "standby", "import-profile")
    )
    parser.add_argument("--file", type=Path, help="Non-secret model configuration JSON")
    parser.add_argument(
        "--environment-only",
        action="store_true",
        help="Check environment without model budget; valid only with check",
    )
    args = parser.parse_args()
    if args.environment_only and args.command != "check":
        parser.error("--environment-only is valid only with check")
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
    report = inspect_environment(
        settings, environment_only=args.environment_only or args.command == "standby"
    )
    if args.command == "standby" and settings.model_execution_enabled:
        parser.error("standby requires model execution disabled")
    if args.command == "check" or report["blockers"]:
        print(json.dumps(report, ensure_ascii=False))
        if report["blockers"]:
            sys.exit(2)
        return
    if args.command == "standby":
        stopped = threading.Event()
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, lambda *_: stopped.set())
        print(json.dumps({"state": "standby", "claims_jobs": False}), flush=True)
        while not stopped.wait(1):
            pass
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
