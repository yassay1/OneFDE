"""Run on the native OneFDE WSL host. Real containers; no Agent/model calls."""

import json
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = Path("/srv/onefde-local/worker/evidence")
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    "/srv/onefde-local/private/compose.env",
    "-f",
    str(ROOT / "deploy/compose.yaml"),
]


def run(args, *, timeout=180):
    result = subprocess.run(
        args, capture_output=True, text=True, timeout=timeout, check=False
    )
    if result.returncode:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {args[:6]}\n{result.stdout[-6000:]}\n{result.stderr[-3000:]}"
        )
    return result.stdout


def healthy():
    with urllib.request.urlopen("http://127.0.0.1:8002/health", timeout=4) as response:
        assert response.status == 200
    run(
        COMPOSE
        + [
            "exec",
            "-T",
            "postgres",
            "pg_isready",
            "-U",
            "onefde",
            "-d",
            "onefde_compose_dev",
        ]
    )


listener = socket.socket()
listener.bind(("172.29.241.1", 0))
listener.listen(16)
listener.settimeout(1)
stop = threading.Event()


def accept():
    while not stop.is_set():
        try:
            client, _ = listener.accept()
            client.close()
        except TimeoutError:
            pass


thread = threading.Thread(target=accept)
thread.start()
monitor_stop = threading.Event()
core_samples = []


def monitor():
    while not monitor_stop.is_set():
        try:
            healthy()
            core_samples.append(True)
        except Exception:
            core_samples.append(False)
        monitor_stop.wait(0.5)


monitor_thread = threading.Thread(target=monitor)
monitor_thread.start()
(EVIDENCE / "inputs.json").write_text(
    json.dumps({"host_probe_port": listener.getsockname()[1]})
)
try:
    healthy()
    print(
        run(
            COMPOSE
            + ["exec", "-T", "worker", "python", "/app/ops/launch.py", "verify"],
            timeout=240,
        )
    )
finally:
    monitor_stop.set()
    monitor_thread.join(12)
    stop.set()
    thread.join(3)
    listener.close()

assert core_samples and all(core_samples), "Core unhealthy during SDK/disk probe"
report = {
    "model_called": False,
    "sdk_disk_core_health_samples": len(core_samples),
    "resource_probes": [],
}
programs = {
    "cpu": "import time,pathlib,json;t=time.monotonic();x=0\nwhile time.monotonic()-t<4:x+=1\nprint(pathlib.Path('/sys/fs/cgroup/cpu.stat').read_text())",
    "memory": "a=[]\nwhile True:a.append(bytearray(1024*1024))",
    "pids": "import subprocess,errno,json\na=[]\ntry:\n for i in range(64):a.append(subprocess.Popen(['sleep','20']))\nexcept OSError as e:\n assert e.errno==errno.EAGAIN;print(json.dumps({'errno':e.errno,'started':len(a)}),flush=True)\nelse:raise AssertionError('PID limit missing')\nfinally:\n for p in a:p.terminate()\n for p in a:p.wait()",
}
for kind, program in programs.items():
    name = "onefde-resource-check-" + str(uuid4())
    identifier = run(
        [
            "docker",
            "create",
            "--name",
            name,
            "--label",
            "onefde.managed=verification",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--user",
            "10001:10001",
            "--init",
            "--cpus",
            "0.1",
            "--memory",
            "64m",
            "--memory-swap",
            "64m",
            "--pids-limit",
            "32",
            "--entrypoint",
            "python",
            "onefde-local-app:locked",
            "-c",
            program,
        ]
    ).strip()
    try:
        run(["docker", "start", identifier])
        deadline = time.monotonic() + 40
        while True:
            healthy()
            state = json.loads(
                run(["docker", "inspect", "--format", "{{json .State}}", identifier])
            )
            if not state["Running"]:
                break
            if time.monotonic() > deadline:
                raise TimeoutError(kind)
            time.sleep(0.3)
        logs = run(["docker", "logs", identifier])
        if kind == "memory":
            assert state["OOMKilled"] and state["ExitCode"] == 137
        else:
            assert state["ExitCode"] == 0
        if kind == "cpu":
            stats = dict(line.split() for line in logs.splitlines() if line.strip())
            assert int(stats["nr_throttled"]) > 0
        if kind == "pids":
            assert json.loads(logs)["errno"] == 11
        report["resource_probes"].append(
            {
                "kind": kind,
                "container_id": identifier,
                "state": state,
                "output": logs,
                "core_healthy_during_probe": True,
            }
        )
    finally:
        run(["docker", "rm", "-f", identifier])
healthy()
(EVIDENCE / "resources.json").write_text(json.dumps(report, indent=2) + "\n")
print(
    json.dumps(
        {
            "resource_probes_passed": len(report["resource_probes"]),
            "model_called": False,
        }
    )
)
