#!/usr/bin/env bash
# Run as root in the new OneFDE Ubuntu distribution only.
set -euo pipefail
test "$(id -u)" = 0
grep -qi microsoft /proc/sys/kernel/osrelease
. /etc/os-release
test "$VERSION_ID" = 24.04
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git python3-venv iptables docker.io docker-compose-v2
# Ubuntu-maintained Engine packages; exact installed versions go in evidence.
python3 -m venv /opt/onefde-tools
if test -n "${ONEFDE_UV_WHEEL:-}"; then
    /opt/onefde-tools/bin/pip install --no-index "$ONEFDE_UV_WHEEL"
else
    /opt/onefde-tools/bin/pip install 'uv==0.12.5'
fi
ln -sf /opt/onefde-tools/bin/uv /usr/local/bin/uv
id onefde >/dev/null 2>&1 || useradd --uid 10001 --create-home --shell /bin/bash onefde
test "$(id -u onefde)" = 10001
usermod -aG docker onefde
chmod 700 /home/onefde
install -d -m 700 -o onefde -g onefde /home/onefde/runtime /home/onefde/private
systemctl enable --now docker
cat > /etc/wsl.conf <<'EOF'
[boot]
systemd=true
[automount]
enabled=false
mountFsTab=false
[interop]
enabled=false
appendWindowsPath=false
[user]
default=onefde
EOF
# Applied on the next start of this distribution; no global WSL shutdown.
