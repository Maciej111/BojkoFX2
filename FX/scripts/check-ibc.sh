#!/usr/bin/env bash
# final-fix.sh — run as: sudo bash /tmp/final-fix.sh
set -euo pipefail

BOJKOFX_DIR="/home/macie/bojkofx"
IBC_DIR="/opt/ibc"

echo "[1] Fix /root/Jts permanently"
mkdir -p /root/Jts
chmod 1777 /root/Jts
ls -la /root/Jts
echo "  OK"

echo "[2] Check IBC ibcstart.sh signature"
head -60 "${IBC_DIR}/scripts/ibcstart.sh" 2>/dev/null || head -60 "${IBC_DIR}/gatewaystart.sh" 2>/dev/null || true

echo "[3] Check IBC version file"
cat "${IBC_DIR}/version" 2>/dev/null || true

echo "[4] List /opt/ibc/"
ls -la "${IBC_DIR}/"

echo "[5] Check IBC gatewaystart.sh"
cat "${IBC_DIR}/gatewaystart.sh" 2>/dev/null | head -80 || true

