"""Root-only, idempotent preparation of the NEW OneFDE local Compose project.

Never formats a device or replaces existing credentials. The bounded filesystem
is a new regular file, independent of all existing Windows/WSL databases.
"""

import os
import platform
import secrets
import shutil
import subprocess
from pathlib import Path

from argon2 import PasswordHasher

if os.getuid() != 0 or "microsoft" not in platform.release().lower():
    raise SystemExit("Run as root only in the approved OneFDE WSL distribution")
base = Path("/srv/onefde-local")
if base.is_symlink():
    raise SystemExit("Unsafe local root")
base.mkdir(mode=0o755, exist_ok=True)
private = base / "private"
private.mkdir(mode=0o700, exist_ok=True)
os.chown(private, 10001, 10001)
os.umask(0o077)
if not (private / "admin_password").exists():
    if list(private.iterdir()):
        raise SystemExit("Partial configuration found; inspect before continuing")
    admin, api, worker, owner = (secrets.token_hex(24) for _ in range(4))
    values = {
        "admin_password": admin,
        "api_password": api,
        "worker_password": worker,
        "admin_url": f"postgresql+psycopg://onefde:{admin}@postgres:5432/onefde_compose_dev",
        "api_url": f"postgresql+psycopg://onefde_app:{api}@postgres:5432/onefde_compose_dev",
        "worker_url": f"postgresql+psycopg://onefde_worker:{worker}@postgres:5432/onefde_compose_dev",
        "owner_hash": PasswordHasher().hash(owner),
        "owner_password": owner,
    }
    for name, value in values.items():
        path = private / name
        path.write_text(value + "\n")
        path.chmod(0o600)
        os.chown(path, 10001, 10001)

image = base / "worker-disk.ext4"
mount = base / "worker"
mount.mkdir(mode=0o700, exist_ok=True)
if not image.exists():
    if any(mount.iterdir()):
        raise SystemExit("Nonempty worker directory; refuse hiding existing data")
    with image.open("xb") as target:
        target.truncate(2 * 1024**3)
    subprocess.run(["mkfs.ext4", "-q", "-F", str(image)], check=True)
elif not image.is_file() or image.is_symlink() or image.stat().st_size != 2 * 1024**3:
    raise SystemExit(
        "Unexpected bounded filesystem; do not resize or format automatically"
    )
storage_script = Path("/usr/local/sbin/onefde-shared-storage")
storage_script.write_text(
    "#!/bin/sh\nset -eu\n"
    "mountpoint -q /srv/onefde-local/worker || mount -o loop,nodev,nosuid "
    "/srv/onefde-local/worker-disk.ext4 /srv/onefde-local/worker\n"
)
storage_script.chmod(0o755)
Path("/etc/systemd/system/onefde-shared-storage.service").write_text(
    "[Unit]\nDescription=Bounded OneFDE local work disk\nBefore=docker.service\n"
    "[Service]\nType=oneshot\nExecStart=/usr/local/sbin/onefde-shared-storage\nRemainAfterExit=yes\n"
    "[Install]\nWantedBy=multi-user.target\n"
)
subprocess.run(["systemctl", "daemon-reload"], check=True)
subprocess.run(
    ["systemctl", "enable", "--now", "onefde-shared-storage.service"], check=True
)
network_script = Path("/usr/local/sbin/onefde-shared-network")
shutil.copyfile(Path(__file__).with_name("network-policy.sh"), network_script)
network_script.chmod(0o755)
dropin = Path("/etc/systemd/system/docker.service.d")
dropin.mkdir(exist_ok=True)
(dropin / "onefde-shared.conf").write_text(
    "[Unit]\nRequires=onefde-shared-storage.service\nAfter=onefde-shared-storage.service\n"
    "[Service]\nExecStartPost=/usr/local/sbin/onefde-shared-network\n"
)
subprocess.run(["systemctl", "daemon-reload"], check=True)
subprocess.run([str(network_script)], check=True)
os.chown(mount, 10001, 10001)
mount.chmod(0o700)
for name in ("tasks", "sessions", "private", "artifacts", "evidence"):
    path = mount / name
    path.mkdir(mode=0o700, exist_ok=True)
    os.chown(path, 10001, 10001)
tools = base / "build-tools"
tools.mkdir(mode=0o755, exist_ok=True)
tools.chmod(0o755)
for name, source in [("uv", "/opt/onefde-tools/bin/uv"), ("docker", "/usr/bin/docker")]:
    shutil.copyfile(source, tools / name)
    (tools / name).chmod(0o755)
env_file = private / "compose.env"
env_file.write_text(f"DOCKER_GID={Path('/var/run/docker.sock').stat().st_gid}\n")
os.chown(env_file, 10001, 10001)
print(
    "Prepared NEW onefde-local credentials and bounded persistent disk; no model configuration."
)
