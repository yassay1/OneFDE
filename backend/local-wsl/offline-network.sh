#!/usr/bin/env bash
# Root, inside OneFDE WSL. Applies only to this daemon and this bridge.
set -euo pipefail
if ! docker network inspect onefde-engineering-offline >/dev/null 2>&1; then
    docker network create --internal \
        --opt com.docker.network.bridge.name=ofde-eng0 \
        --opt com.docker.network.bridge.host_binding_ipv4=127.0.0.1 \
        onefde-engineering-offline
fi
test "$(docker network inspect -f '{{.Internal}}' onefde-engineering-offline)" = true
test "$(docker network inspect -f '{{index .Options "com.docker.network.bridge.name"}}' onefde-engineering-offline)" = ofde-eng0
iptables -N ONEFDE-LOCAL-INPUT 2>/dev/null || true
iptables -F ONEFDE-LOCAL-INPUT
iptables -A ONEFDE-LOCAL-INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A ONEFDE-LOCAL-INPUT -j DROP
iptables -C INPUT -i ofde-eng0 -j ONEFDE-LOCAL-INPUT 2>/dev/null || \
    iptables -I INPUT 1 -i ofde-eng0 -j ONEFDE-LOCAL-INPUT
# Internal bridge blocks routed egress; INPUT also denies new connections to host.
# IPv6 is disabled for this network. Do not add peers or additional networks.
