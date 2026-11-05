"""Real SDK checks inside the trusted bridge Worker; NO Agent/LLM is created."""

import json
import logging
import secrets
import shlex
import socket
import subprocess
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, text

from onefde.infrastructure.artifacts import PrivateArtifactStore
from onefde.infrastructure.runtime.openhands import (
    archive_workspace,
    confirm_stopped,
    shared_workspace,
)
from onefde.worker.config import WorkerSettings
from onefde.worker.controller import Worker

logging.getLogger("openhands").setLevel(logging.CRITICAL)
settings = WorkerSettings()
assert settings.execution_mode == "ecs_shared" and not settings.model_execution_enabled
assert not settings.capacity_blockers()
for limits in ({"min_free_disk_bytes": 4 * 1024**3}, {"min_free_memory_mb": 1024**2}):
    bounded = settings.model_copy(update=limits)
    assert bounded.capacity_blockers()
    assert Worker(None, bounded, None).run_once() is False
inputs = json.loads((settings.root / "evidence/inputs.json").read_text())
report = {
    "scope": "ecs_shared_environment_only",
    "model_called": False,
    "checked_at_utc": datetime.now(UTC).isoformat(),
    "checks": [],
}
report["checks"].append("real capacity refusal for low disk/memory before any DB claim")


def passed(name):
    report["checks"].append(name)


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True, timeout=90)


engine = create_engine(settings.database_url.get_secret_value())
with engine.connect() as db:
    assert db.execute(text("SELECT count(*) FROM tasks")).scalar_one() >= 0
    assert not db.execute(
        text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")
    ).scalar_one()
    for table in ("auth_sessions", "login_attempts"):
        assert not db.execute(
            text("SELECT has_table_privilege(current_user,:t,'SELECT')"), {"t": table}
        ).scalar_one()
    assert not db.execute(
        text("SELECT has_schema_privilege(current_user,'public','CREATE')")
    ).scalar_one()
engine.dispose()
passed("restricted Worker DB identity; no auth-table or DDL access")
listener = socket.socket()
listener.bind(("172.29.241.2", 0))
listener.listen(2)
worker_probe = listener.getsockname()[1]
with socket.create_connection(("172.29.241.2", worker_probe), timeout=2):
    pass
with socket.create_connection(("172.29.241.1", inputs["host_probe_port"]), timeout=2):
    pass
targets = [
    ("172.29.241.2", worker_probe),
    ("172.29.241.1", inputs["host_probe_port"]),
    ("172.29.240.3", 5432),
    ("100.100.100.200", 80),
    ("169.254.169.254", 80),
    ("1.1.1.1", 443),
]
report["network_targets"] = targets
identifier = str(uuid4())
workspace_path = settings.root / "tasks" / identifier / "workspace"
session_path = settings.root / "sessions" / identifier
for path in (workspace_path, session_path):
    path.mkdir(parents=True, mode=0o700)
allocated = []
workspace = None
try:
    workspace = shared_workspace(
        settings,
        workspace_path,
        session_path,
        secrets.token_urlsafe(32),
        lambda ref: allocated.append(ref["container_id"]),
    )
    inspected = json.loads(docker("inspect", allocated[0]))[0]
    limits = inspected["HostConfig"]
    assert limits["ReadonlyRootfs"] and not limits["Privileged"]
    assert (
        limits["CapDrop"] == ["ALL"]
        and "no-new-privileges:true" in limits["SecurityOpt"]
    )
    assert inspected["Config"]["User"] == "10001:10001"
    assert (
        limits["NanoCpus"] == 1000000000
        and limits["Memory"] == limits["MemorySwap"] == 2147483648
    )
    assert limits["PidsLimit"] == 256 and not limits["PortBindings"]
    assert {m["Destination"] for m in inspected["Mounts"]} == {"/workspace", "/session"}
    assert set(inspected["NetworkSettings"]["Networks"]) == {settings.network}
    assert not any(v.startswith("ONEFDE_") for v in inspected["Config"]["Env"])
    report["container_id"] = allocated[0]
    report["image"] = inspected["Image"]
    report["create_time_limits"] = {
        k: limits[k]
        for k in (
            "NanoCpus",
            "Memory",
            "MemorySwap",
            "PidsLimit",
            "ReadonlyRootfs",
            "CapDrop",
            "SecurityOpt",
        )
    }
    response = httpx.post(
        workspace.host + workspace.api_prefix + "/bash/start_bash_command",
        json={"command": "true", "timeout": 1},
        headers={"X-Session-API-Key": "wrong-key"},
        timeout=5,
        trust_env=False,
    )
    assert response.status_code in (401, 403)
    report["wrong_key_status"] = response.status_code
    passed(
        "bridge Worker -> real pinned SDK authenticated; wrong key rejected; no host port"
    )
    passed(
        "create-time CPU/memory/PID/read-only/NNP/cap-drop and minimal mounts verified"
    )
    script = """import os,pathlib,socket,subprocess,json,errno
assert os.getuid()==10001
status=pathlib.Path('/proc/self/status').read_text()
assert 'NoNewPrivs:\\t1' in status and 'CapEff:\\t0000000000000000' in status and 'Seccomp:\\t2' in status
for p in ['/var/run/docker.sock','/run/secrets/worker_url','/srv/onefde-local/private','/srv/onefde-local/worker/tasks']:
 assert not pathlib.Path(p).exists(),p
try: pathlib.Path('/etc/onefde-forbidden').write_text('bad')
except OSError as e: assert e.errno in (errno.EACCES,errno.EROFS)
else: raise AssertionError('root writable')
sudo=subprocess.run(['sudo','-n','id','-u'],capture_output=True,timeout=3)
assert sudo.returncode!=0
pathlib.Path('/workspace/environment.txt').write_text('shared SDK command persisted\\n')
pathlib.Path('/session/environment.txt').write_text('private session persisted\\n')
for host,port in TARGETS:
 try: s=socket.create_connection((host,port),timeout=1)
 except OSError: continue
 else: s.close();raise AssertionError('forbidden connection succeeded')
try: s=socket.create_connection(('2001:4860:4860::8888',443),timeout=1)
except OSError: pass
else: s.close();raise AssertionError('IPv6 bypass')
def tunnel(host):
 with socket.create_connection(('172.29.241.3',3128),timeout=5) as s:
  s.sendall(('CONNECT '+host+':443 HTTP/1.1\\r\\nHost: '+host+':443\\r\\n\\r\\n').encode())
  data=s.recv(4096)
  if b' 200 ' in data.split(b'\\r\\n')[0]:
   if b'onefde-offline-probe' not in data:data+=s.recv(4096)
   assert b'onefde-offline-probe' in data
   return 200
  assert b' 403 ' in data.split(b'\\r\\n')[0],data[:100]
  return 403
assert tunnel('onefde-probe.test')==200
assert tunnel('example.com')==403
assert tunnel('100.100.100.200')==403
print(json.dumps({'uid':os.getuid(),'no_new_privileges':True,'sudo_denied':True,'tcp_denials':len(TARGETS),'proxy_fixture':200,'proxy_denied':403}))
""".replace("TARGETS", repr(targets))
    command = "python -c " + shlex.quote(script)
    result = workspace.execute_command(command, cwd="/workspace", timeout=40)
    report["command_result"] = result.model_dump(mode="json")
    assert result.exit_code == 0
    passed(
        "actual SDK file/session writes; UID, sudo denial and forbidden filesystem checks"
    )
    passed(
        "active host/Worker listeners, PG, metadata, internet and IPv6 denied; offline allowlist CONNECT succeeds, others 403"
    )
    docker("restart", allocated[0])
    workspace._wait_for_health(timeout=60)
    restarted = workspace.execute_command(
        "cat /workspace/environment.txt /session/environment.txt", timeout=15
    )
    assert restarted.exit_code == 0
    report["sandbox_restart_result"] = restarted.model_dump(mode="json")
    passed(
        "Sandbox restarted; workspace/session files survived (no Conversation resume claim)"
    )
    disk_script = """import os,errno,json
p='/workspace/quota-fill'
total=0
try:
 with open(p,'wb',buffering=0) as f:
  while True: total+=f.write(b'x'*(1024*1024))
except OSError as e:
 assert e.errno==errno.ENOSPC
 print(json.dumps({'errno':e.errno,'bytes_written':total,'hard_bound':True}))
finally:
 os.unlink(p)
"""
    result = workspace.execute_command(
        "python -c " + shlex.quote(disk_script), timeout=90
    )
    assert result.exit_code == 0
    report["disk_limit_result"] = result.model_dump(mode="json")
    passed("bounded persistent filesystem returned actual ENOSPC; test file removed")
finally:
    listener.close()
    stopped = confirm_stopped(allocated[0] if allocated else None)
    if workspace is not None and stopped:
        workspace.cleanup()
    elif allocated and stopped:
        docker("rm", allocated[0])
    report["stopped"] = stopped
assert stopped
assert (
    workspace_path.joinpath("environment.txt").read_text()
    == "shared SDK command persisted\n"
)
assert session_path.joinpath("environment.txt").is_file()
data, count = archive_workspace(workspace_path, settings.max_artifact_bytes)
store = PrivateArtifactStore(settings.root / "artifacts")
key = f"shared-environment/{identifier}/workspace.tar.gz"
artifact = store.put(key, data)
store.verify(key, artifact)
report["artifact"] = {**artifact, "file_count": count, "key": key}
passed(
    "stopped proof, persistent workspace/session and immutable archive digest verified"
)
(settings.root / "evidence/environment.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n"
)
print(json.dumps({"passed": len(report["checks"]), "model_called": False}))
