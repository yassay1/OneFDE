#!/usr/bin/env bash
# Root, native OneFDE WSL daemon only. Never flush Docker's or other apps' rules.
set -euo pipefail
iptables -N ONEFDE-SHARED 2>/dev/null || true
iptables -F ONEFDE-SHARED
iptables -A ONEFDE-SHARED -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A ONEFDE-SHARED -s 172.29.241.2 -d 172.29.241.0/24 -p tcp --dport 8000 -j ACCEPT
iptables -A ONEFDE-SHARED -s 172.29.241.0/24 -d 172.29.241.3 -p tcp --dport 3128 -j ACCEPT
iptables -A ONEFDE-SHARED -s 172.29.241.2 -j RETURN
# Proxy's external interface: deny private/metadata/host routes, HTTPS only.
for denied in 0.0.0.0/8 10.0.0.0/8 127.0.0.0/8 169.254.0.0/16 172.16.0.0/12 192.168.0.0/16 100.64.0.0/10 224.0.0.0/4; do
  iptables -A ONEFDE-SHARED -s 172.29.242.3 -d "$denied" -j DROP
done
iptables -A ONEFDE-SHARED -s 172.29.242.3 -p tcp --dport 443 -j ACCEPT
iptables -A ONEFDE-SHARED -s 172.29.242.3 -j DROP
# Proxy may reach only the isolated offline fixture network in this phase.
iptables -A ONEFDE-SHARED -s 172.29.241.3 -d 203.0.113.0/24 -j ACCEPT
iptables -A ONEFDE-SHARED -s 172.29.241.0/24 -j DROP
iptables -A ONEFDE-SHARED -j RETURN
iptables -C DOCKER-USER -s 172.29.241.0/24 -j ONEFDE-SHARED 2>/dev/null || \
  iptables -I DOCKER-USER 1 -s 172.29.241.0/24 -j ONEFDE-SHARED
iptables -C DOCKER-USER -s 172.29.242.3 -j ONEFDE-SHARED 2>/dev/null || \
  iptables -I DOCKER-USER 1 -s 172.29.242.3 -j ONEFDE-SHARED
iptables -N ONEFDE-SHARED-INPUT 2>/dev/null || true
iptables -F ONEFDE-SHARED-INPUT
iptables -A ONEFDE-SHARED-INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A ONEFDE-SHARED-INPUT -s 172.29.241.2 -j RETURN
iptables -A ONEFDE-SHARED-INPUT -j DROP
iptables -C INPUT -i ofde-shared0 -j ONEFDE-SHARED-INPUT 2>/dev/null || \
  iptables -I INPUT 1 -i ofde-shared0 -j ONEFDE-SHARED-INPUT
iptables -C INPUT -i ofde-model0 -j ONEFDE-SHARED-INPUT 2>/dev/null || \
  iptables -I INPUT 1 -i ofde-model0 -j ONEFDE-SHARED-INPUT
