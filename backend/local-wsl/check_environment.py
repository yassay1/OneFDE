"""Real SDK/Docker environment checks. No Agent, LLM, Task or Run is created."""

import hashlib
import json
import logging
import os
import platform
import secrets
import shlex
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text

from onefde.infrastructure.artifacts import PrivateArtifactStore
from onefde.infrastructure.runtime.openhands import (
    archive_workspace,
    confirm_stopped,
    local_workspace_host,
    server_environment,
)
from onefde.worker.config import WorkerSettings

os.environ["OPENHANDS_SUPPRESS_BANNER"] = "1"
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
logging.getLogger("openhands").setLevel(logging.CRITICAL)
from openhands.workspace import DockerWorkspace  # noqa: E402

logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True, timeout=60)


settings = WorkerSettings()
assert settings.execution_mode == "local_wsl"
assert not settings.model_execution_enabled
assert settings.max_cost_usd is None
assert not any(k.startswith("ONEFDE_MODEL_") for k in os.environ)
assert os.getuid() == 10001  # Match the user of the reviewed Agent Server image.
assert not settings.blockers(environment_only=True)
identifier = str(uuid4())
directory = settings.root / "environment-checks" / identifier
workspace_path, session_path = directory / "workspace", directory / "session"
for path in (workspace_path, session_path):
    path.mkdir(parents=True, mode=0o700)
report = {
    "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    "scope": "environment_only_not_C2_engineering",
    "model_called": False,
    "task_run_created": False,
    "python": platform.python_version(),
    "kernel": platform.release(),
    "docker": docker("version", "--format", "{{.Server.Version}}").strip(),
    "checks": [],
}


def passed(name):
    report["checks"].append(name)


mounts = Path("/proc/mounts").read_text()
assert not any(f" /mnt/{drive} " in mounts for drive in ("c", "d"))
assert "enabled=false" in Path("/etc/wsl.conf").read_text()
passed("Windows disks not automounted; interop disabled in distro configuration")
network = json.loads(docker("network", "inspect", settings.network))[0]
assert network["Internal"] and not network["EnableIPv6"]
control = json.loads(docker("inspect", "onefde-wsl-postgres-1"))[0]
control_ip = next(iter(control["NetworkSettings"]["Networks"].values()))["IPAddress"]
gateway = network["IPAM"]["Config"][0]["Gateway"]
passed("Engineering internal IPv4 network separated from control database network")
engine = create_engine(settings.database_url.get_secret_value())
with engine.connect() as db:
    role = db.execute(
        text(
            "SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user"
        )
    ).one()
    assert not any(role)
    assert (
        db.execute(text("SELECT count(*) FROM model_profile_revisions")).scalar_one()
        == 0
    )
    assert not db.execute(
        text("SELECT has_table_privilege(current_user,'auth_sessions','SELECT')")
    ).scalar_one()
    assert not db.execute(
        text("SELECT has_schema_privilege(current_user,'public','CREATE')")
    ).scalar_one()
    assert not db.execute(
        text("SELECT has_database_privilege(current_user,'onefde_wsl_test','CONNECT')")
    ).scalar_one()
    assert db.execute(
        text("SELECT has_table_privilege(current_user,'dispatch_jobs','UPDATE')")
    ).scalar_one()
engine.dispose()
passed(
    "Restricted Worker DB role can read dispatch metadata but has no auth/DDL/test DB/admin privileges"
)
host_probe = socket.socket()
host_probe.bind((gateway, 0))
host_probe.listen(2)
probe_port = host_probe.getsockname()[1]
with socket.create_connection((gateway, probe_port), timeout=2):
    pass
report["network_targets"] = {
    "host_listener": [gateway, probe_port],
    "host_listener_reachable_from_worker": True,
    "control_database": [control_ip, 5432],
    "internet": ["1.1.1.1", 443],
}
container = []


class CheckedWorkspace(DockerWorkspace):
    def _wait_for_health(self, timeout):
        container.append(self._container_id)
        docker(
            "update",
            "--cpus",
            "1",
            "--memory",
            "2g",
            "--memory-swap",
            "2g",
            "--pids-limit",
            "256",
            container[0],
        )
        object.__setattr__(
            self, "host", local_workspace_host(container[0], settings.network)
        )
        return super()._wait_for_health(timeout=timeout)


workspace = None
try:
    with server_environment(secrets.token_urlsafe(32)) as forwarded:
        workspace = CheckedWorkspace(
            server_image=settings.server_image,
            working_dir="/workspace",
            volumes=[f"{workspace_path}:/workspace", f"{session_path}:/session"],
            forward_env=forwarded,
            network=settings.network,
            extra_ports=False,
            detach_logs=False,
            cleanup_image=False,
            health_check_timeout=90,
            read_timeout=20,
        )
    inspected = json.loads(docker("inspect", container[0]))[0]
    limits = inspected["HostConfig"]
    assert limits["NanoCpus"] == 1000000000
    assert limits["Memory"] == limits["MemorySwap"] == 2147483648
    assert limits["PidsLimit"] == 256 and not limits["Privileged"]
    assert {m["Destination"] for m in inspected["Mounts"]} == {"/workspace", "/session"}
    assert set(inspected["NetworkSettings"]["Networks"]) == {settings.network}
    assert not any(v.startswith("ONEFDE_") for v in inspected["Config"]["Env"])
    assert all(
        p["HostIp"] == "127.0.0.1"
        for ports in inspected["NetworkSettings"]["Ports"].values()
        if ports
        for p in ports
    )
    passed(
        "Real pinned Agent Server healthy; private mounts, no non-loopback published ports, credentials exclusion and CPU/memory/PID verified"
    )
    script = (
        "import pathlib,socket,json\n"
        "pathlib.Path('/workspace/environment.txt').write_text('real container command passed\\n')\n"
        "pathlib.Path('/session/environment.txt').write_text('session mount persisted\\n')\n"
        "assert not pathlib.Path('/var/run/docker.sock').exists()\n"
        f"targets={[(gateway, probe_port), (control_ip, 5432), ('1.1.1.1', 443)]!r}\n"
        "for host,port in targets:\n"
        " try:\n"
        "  connection=socket.create_connection((host,port),timeout=2)\n"
        " except OSError:\n"
        "  continue\n"
        " else:\n"
        "  connection.close(); raise AssertionError('unexpected network access')\n"
        "print(json.dumps({'file_write':True,'docker_socket_absent':True,'network_denials':len(targets)}))\n"
    )
    command = "python -c " + shlex.quote(script)
    result = workspace.execute_command(command, cwd="/workspace", timeout=25)
    assert result.exit_code == 0
    report["command"] = command
    report["command_result"] = result.model_dump(mode="json")
    passed(
        "SDK command executed: actual file/session writes and TCP denials for host/control DB/internet"
    )
finally:
    host_probe.close()
    stopped = confirm_stopped(container[0] if container else None)
    if workspace is not None:
        workspace.cleanup()
    report["stopped"] = stopped
assert stopped
assert (
    workspace_path.joinpath("environment.txt").read_text()
    == "real container command passed\n"
)
assert session_path.joinpath("environment.txt").is_file()
data, count = archive_workspace(workspace_path, settings.max_artifact_bytes)
store = PrivateArtifactStore(settings.root / "artifacts")
key = f"environment/{identifier}/workspace.tar.gz"
evidence = store.put(key, data)
store.verify(key, evidence)
report["artifact"] = {**evidence, "file_count": count, "local_key": key}
assert evidence["sha256"] == hashlib.sha256(data).hexdigest()
passed(
    "Daemon confirmed stopped; workspace/session survive; immutable archive SHA256 verified"
)
Path("work").mkdir(exist_ok=True)
Path("work/wsl-environment.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n"
)
print(
    json.dumps(
        {
            "passed": len(report["checks"]),
            "model_called": False,
            "evidence": "work/wsl-environment.json",
        }
    )
)
