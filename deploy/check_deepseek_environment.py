"""Native WSL check: secret loading, metadata, TLS/ACL. NO inference request."""

import json
import socket
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path

root = Path(__file__).resolve().parents[1]
compose = [
    "docker",
    "compose",
    "--env-file",
    "/srv/onefde-local/private/compose.env",
    "-f",
    str(root / "deploy/compose.yaml"),
]


def run(args):
    result = subprocess.run(
        args, capture_output=True, text=True, timeout=90, check=False
    )
    if result.returncode:
        # No private configuration/child tracebacks in environment evidence.
        raise RuntimeError("Environment check command failed; output withheld")
    return result.stdout


credential = json.loads(
    run(
        compose
        + ["exec", "-T", "worker", "python", "/app/ops/launch.py", "model-check"]
    )
)
preflight = json.loads(
    run(compose + ["exec", "-T", "worker", "python", "/app/ops/launch.py", "check"])
)
assert not preflight["blockers"] and not preflight["model_execution_enabled"]
listener = socket.socket()
listener.bind(("172.29.241.1", 0))
listener.listen(8)
listener.settimeout(0.5)
port = listener.getsockname()[1]
stop = threading.Event()


def accept():
    while not stop.is_set():
        try:
            connection, _ = listener.accept()
            connection.close()
        except TimeoutError:
            pass


thread = threading.Thread(target=accept)
thread.start()
with socket.create_connection(("172.29.241.1", port), timeout=2):
    pass
program = """import socket,ssl,json
def tunnel(host):
 s=socket.create_connection(('172.29.241.3',3128),timeout=15)
 s.sendall(('CONNECT '+host+':443 HTTP/1.1\\r\\nHost: '+host+':443\\r\\n\\r\\n').encode())
 data=b''
 while b'\\r\\n\\r\\n' not in data:
  chunk=s.recv(4096)
  if not chunk:raise AssertionError('Proxy closed before response')
  data+=chunk
 status=int(data.split(b' ')[1]);return s,status
protocols={}
for host in ['api.deepseek.com','api.xiaomimimo.com']:
 s,status=tunnel(host)
 assert status==200,(host,status)
 with ssl.create_default_context().wrap_socket(s,server_hostname=host) as tls:
  protocols[host]=tls.version()
# TLS handshake only: no Authorization, HTTP request or model payload sent.
denied=[]
for host in ['example.com','token-plan-cn.xiaomimimo.com','100.100.100.200','169.254.169.254']:
 s,status=tunnel(host);s.close();assert status==403;denied.append(host)
targets=[('172.29.241.1',HOST_PORT),('172.29.240.3',5432),('100.100.100.200',80),('169.254.169.254',80),('1.1.1.1',443)]
for host,port in targets:
 try:s=socket.create_connection((host,port),timeout=1)
 except OSError:continue
 else:s.close();raise AssertionError('Direct egress or lateral access succeeded')
print(json.dumps({'tls_versions':protocols,'tls_verified':True,'proxy_denied_hosts':denied,'direct_tcp_denials':len(targets),'host_positive_control':True,'authorization_header_sent':False,'http_request_sent_to_provider':False,'model_called':False}))
""".replace("HOST_PORT", str(port))
try:
    network = json.loads(
        run(
            [
                "docker",
                "run",
                "--rm",
                "--label",
                "onefde.managed=environment-check",
                "--network",
                "onefde-local-sandbox",
                "--user",
                "10001:10001",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--cpus",
                "0.2",
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
        )
    )
finally:
    stop.set()
    thread.join(2)
    listener.close()
report = {
    "checked_at_utc": datetime.now(UTC).isoformat(),
    "scope": "DeepSeek and MiMo environment only",
    "model_called": False,
    "credentials": credential,
    "preflight": preflight,
    "network": network,
    "task_or_run_created": False,
}
path = Path("/srv/onefde-local/worker/evidence/dual-model-environment.json")
path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(report, ensure_ascii=False))
